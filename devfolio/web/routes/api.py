"""REST API 라우터 — 설정 CRUD."""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from devfolio.core.storage import load_config, save_config
from devfolio.models.config import AIProviderConfig, ExportConfig, SyncConfig, UserConfig
from devfolio.utils.security import (
    delete_api_key,
    get_api_key,
    mask_api_key,
    store_api_key,
)

router = APIRouter(tags=["config"])


# ---------------------------------------------------------------------------
# Request / Response 모델
# ---------------------------------------------------------------------------

class UserConfigUpdate(BaseModel):
    name: str = ""
    email: str = ""
    github: str = ""
    blog: str = ""


class ExportConfigUpdate(BaseModel):
    default_format: str = "md"
    default_template: str = "default"
    output_dir: str = ""


class SyncConfigUpdate(BaseModel):
    enabled: bool = False
    repo_url: str = ""
    branch: str = "main"


class GeneralConfigUpdate(BaseModel):
    default_language: str = "ko"
    timezone: str = "Asia/Seoul"
    default_ai_provider: str = ""


class AIProviderCreate(BaseModel):
    name: str
    model: str
    api_key: Optional[str] = None   # 저장 후 마스킹; Docker에서는 환경변수 사용
    base_url: Optional[str] = None


class AIProviderResponse(BaseModel):
    name: str
    model: str
    key_stored: bool
    key_masked: str        # 마스킹된 키 또는 "(환경변수)" / "(없음)"
    base_url: Optional[str] = None
    is_default: bool = False


# ---------------------------------------------------------------------------
# 전체 Config 조회
# ---------------------------------------------------------------------------

@router.get("/config")
def get_config() -> dict[str, Any]:
    """전체 설정을 반환합니다 (API 키는 마스킹)."""
    cfg = load_config()
    return {
        "user": cfg.user.model_dump(),
        "export": cfg.export.model_dump(),
        "sync": cfg.sync.model_dump(),
        "general": {
            "default_language": cfg.default_language,
            "timezone": cfg.timezone,
            "default_ai_provider": cfg.default_ai_provider,
        },
        "ai_providers": _build_provider_list(cfg),
        "initialized": True,
    }


def _build_provider_list(cfg) -> list[dict[str, Any]]:
    result = []
    for p in cfg.ai_providers:
        key = get_api_key(p.name)
        if key:
            masked = mask_api_key(key)
            # 환경변수에서 온 경우 구분
            env_var = _env_var_name(p.name)
            if os.environ.get(env_var):
                masked = f"(환경변수 {env_var})"
        else:
            masked = "(없음)"
        result.append({
            "name": p.name,
            "model": p.model,
            "key_stored": p.key_stored,
            "key_masked": masked,
            "base_url": p.base_url,
            "is_default": p.name == cfg.default_ai_provider,
        })
    return result


def _env_var_name(provider: str) -> str:
    mapping = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "cohere": "COHERE_API_KEY",
    }
    return mapping.get(provider, f"{provider.upper()}_API_KEY")


# ---------------------------------------------------------------------------
# 사용자 프로필
# ---------------------------------------------------------------------------

@router.put("/config/user")
def update_user(body: UserConfigUpdate) -> dict[str, str]:
    """사용자 프로필을 저장합니다."""
    cfg = load_config()
    try:
        cfg.user = UserConfig.model_validate(body.model_dump())
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    save_config(cfg)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 내보내기 기본값
# ---------------------------------------------------------------------------

@router.put("/config/export")
def update_export(body: ExportConfigUpdate) -> dict[str, str]:
    """내보내기 기본값을 저장합니다."""
    cfg = load_config()
    try:
        cfg.export = ExportConfig.model_validate(body.model_dump())
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    save_config(cfg)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# GitHub 동기화
# ---------------------------------------------------------------------------

@router.put("/config/sync")
def update_sync(body: SyncConfigUpdate) -> dict[str, str]:
    """GitHub 동기화 설정을 저장합니다."""
    cfg = load_config()
    try:
        cfg.sync = SyncConfig.model_validate(body.model_dump())
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    save_config(cfg)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 일반 설정 (언어·타임존·기본 Provider)
# ---------------------------------------------------------------------------

@router.put("/config/general")
def update_general(body: GeneralConfigUpdate) -> dict[str, str]:
    """언어, 타임존, 기본 AI Provider를 저장합니다."""
    cfg = load_config()
    if body.default_language not in ("ko", "en", "both"):
        raise HTTPException(status_code=422, detail="언어는 ko, en, both 중 하나여야 합니다.")
    cfg.default_language = body.default_language
    cfg.timezone = body.timezone
    cfg.default_ai_provider = body.default_ai_provider
    save_config(cfg)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# AI Provider CRUD
# ---------------------------------------------------------------------------

@router.get("/config/ai")
def list_ai_providers() -> list[dict[str, Any]]:
    """등록된 AI Provider 목록을 반환합니다."""
    cfg = load_config()
    return _build_provider_list(cfg)


@router.post("/config/ai")
def upsert_ai_provider(body: AIProviderCreate) -> dict[str, str]:
    """AI Provider를 추가하거나 갱신합니다."""
    cfg = load_config()

    key_stored = False
    if body.api_key:
        key_stored = store_api_key(body.name, body.api_key)

    provider = AIProviderConfig(
        name=body.name,
        model=body.model,
        key_stored=key_stored,
        base_url=body.base_url or None,
    )
    cfg.upsert_provider(provider)

    # 첫 Provider이면 기본으로 설정
    if not cfg.default_ai_provider:
        cfg.default_ai_provider = body.name

    save_config(cfg)
    return {"status": "ok", "key_stored": str(key_stored)}


@router.delete("/config/ai/{name}")
def remove_ai_provider(name: str) -> dict[str, str]:
    """AI Provider를 삭제합니다."""
    cfg = load_config()
    before = len(cfg.ai_providers)
    cfg.ai_providers = [p for p in cfg.ai_providers if p.name != name]
    if len(cfg.ai_providers) == before:
        raise HTTPException(status_code=404, detail=f"Provider '{name}'를 찾을 수 없습니다.")

    delete_api_key(name)

    if cfg.default_ai_provider == name:
        cfg.default_ai_provider = cfg.ai_providers[0].name if cfg.ai_providers else ""

    save_config(cfg)
    return {"status": "ok"}


@router.post("/config/ai/{name}/test")
def test_ai_provider(name: str) -> dict[str, Any]:
    """AI Provider 연결을 테스트합니다."""
    cfg = load_config()
    provider = cfg.get_provider(name)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{name}'를 찾을 수 없습니다.")

    key = get_api_key(name)
    if not key and name != "ollama":
        return {"status": "error", "message": "API 키가 설정되지 않았습니다."}

    try:
        from devfolio.core.ai_service import AIService
        service = AIService(cfg)
        service._call(
            system_prompt="You are a test assistant. Reply briefly.",
            user_prompt="Reply with exactly: ok",
            provider_name=name,
        )
        return {"status": "ok", "message": "연결 성공"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
