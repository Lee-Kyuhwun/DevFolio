"""REST API 라우터 — Portfolio Studio + 설정 CRUD."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from devfolio.core.ai_service import AIService
from devfolio.core.export_engine import ExportEngine
from devfolio.core.project_manager import ProjectManager
from devfolio.core.storage import EXPORTS_DIR, load_config, save_config
from devfolio.core.template_engine import TemplateEngine
from devfolio.exceptions import DevfolioError, DevfolioProjectNotFoundError
from devfolio.models.config import AIProviderConfig, ExportConfig, SyncConfig, UserConfig
from devfolio.models.draft import DraftPreviewRequest, ProjectDraft
from devfolio.utils.security import (
    delete_api_key,
    get_api_key,
    mask_api_key,
    store_api_key,
)

router = APIRouter(tags=["studio"])
pm = ProjectManager()


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
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class GitScanRequest(BaseModel):
    repo_path: str
    author_email: Optional[str] = None
    refresh: bool = False


class DraftIntakeRequest(BaseModel):
    raw_text: str
    lang: str = "ko"
    provider: Optional[str] = None


class DraftAIRequest(BaseModel):
    draft: ProjectDraft
    lang: str = "ko"
    provider: Optional[str] = None


class SavedAIRequest(BaseModel):
    lang: str = "ko"
    provider: Optional[str] = None


# ---------------------------------------------------------------------------
# 공용 헬퍼
# ---------------------------------------------------------------------------

def _format_error(exc: DevfolioError) -> str:
    if exc.hint:
        return f"{exc.message} ({exc.hint})"
    return exc.message


def _raise_from_devfolio(exc: DevfolioError, status_code: int = 400) -> None:
    raise HTTPException(status_code=status_code, detail=_format_error(exc)) from exc


def _build_provider_list(cfg) -> list[dict[str, Any]]:
    result = []
    for provider in cfg.ai_providers:
        key = get_api_key(provider.name)
        if key:
            masked = mask_api_key(key)
            env_var = _env_var_name(provider.name)
            if os.environ.get(env_var):
                masked = f"(환경변수 {env_var})"
        else:
            masked = "(없음)"
        result.append(
            {
                "name": provider.name,
                "model": provider.model,
                "key_stored": provider.key_stored,
                "key_masked": masked,
                "base_url": provider.base_url,
                "is_default": provider.name == cfg.default_ai_provider,
            }
        )
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


def _draft_payload(project) -> dict[str, Any]:
    return pm.draft_from_project(project).model_dump(exclude_none=False)


def _resolve_projects(request: DraftPreviewRequest):
    if request.source == "draft":
        return [pm.project_from_draft(request.draft_project, transient=True)]

    if request.project_ids:
        try:
            projects = [pm.get_project_or_raise(project_id) for project_id in request.project_ids]
        except DevfolioProjectNotFoundError as exc:
            _raise_from_devfolio(exc, status_code=404)
    else:
        projects = pm.list_projects()

    if not projects:
        _raise_from_devfolio(
            DevfolioError(
                "미리보기할 프로젝트가 없습니다.",
                hint="Intake 탭에서 초안을 저장하거나 Projects 탭에서 기존 프로젝트를 선택하세요.",
            )
        )
    return projects


def _render_document(request: DraftPreviewRequest) -> tuple[str, list[Any], str]:
    cfg = load_config()
    template_name = request.template or cfg.export.default_template or "default"
    projects = _resolve_projects(request)
    markdown = TemplateEngine().render(
        projects=projects,
        config=cfg,
        template_name=template_name,
        doc_type=request.doc_type,
    )
    return markdown, projects, template_name


def _preview_response(request: DraftPreviewRequest) -> dict[str, Any]:
    markdown, projects, template_name = _render_document(request)
    engine = ExportEngine()
    html_body = engine._md_to_html_body(markdown)
    title = f"DevFolio {request.doc_type.title()} Preview"
    return {
        "status": "ok",
        "doc_type": request.doc_type,
        "source": request.source,
        "template": template_name,
        "project_count": len(projects),
        "markdown": markdown,
        "html": html_body,
        "full_html": engine.build_html_document(html_body, title=title),
    }


def _export_document(request: DraftPreviewRequest) -> dict[str, Any]:
    cfg = load_config()
    fmt = (request.format or cfg.export.default_format or "html").lower()
    markdown, projects, template_name = _render_document(request)
    engine = ExportEngine()

    supported_formats = {
        "resume": {"md", "html", "pdf", "docx", "json", "csv"},
        "portfolio": {"md", "html", "pdf", "csv"},
    }
    if fmt not in supported_formats[request.doc_type]:
        _raise_from_devfolio(
            DevfolioError(
                f"{request.doc_type} 문서는 `{fmt}` 포맷을 지원하지 않습니다.",
                hint=f"지원 포맷: {', '.join(sorted(supported_formats[request.doc_type]))}",
            )
        )

    filename = f"{request.doc_type}_{template_name}"
    if fmt == "json":
        output_path = EXPORTS_DIR / f"{filename}.json"
        output_path.write_text(
            json.dumps([project.model_dump() for project in projects], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    elif fmt == "csv":
        output_path = engine.export_csv(projects, filename)
    else:
        exporters = {
            "md": engine.export_markdown,
            "html": engine.export_html,
            "pdf": engine.export_pdf,
            "docx": engine.export_docx,
        }
        output_path = exporters[fmt](markdown, filename)

    return {
        "status": "ok",
        "doc_type": request.doc_type,
        "format": fmt,
        "path": str(output_path),
        "project_count": len(projects),
    }


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


# ---------------------------------------------------------------------------
# 사용자 프로필 / 일반 설정 / Export / Sync
# ---------------------------------------------------------------------------

@router.put("/config/user")
def update_user(body: UserConfigUpdate) -> dict[str, str]:
    cfg = load_config()
    try:
        cfg.user = UserConfig.model_validate(body.model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_config(cfg)
    return {"status": "ok"}


@router.put("/config/export")
def update_export(body: ExportConfigUpdate) -> dict[str, str]:
    cfg = load_config()
    try:
        cfg.export = ExportConfig.model_validate(body.model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_config(cfg)
    return {"status": "ok"}


@router.put("/config/sync")
def update_sync(body: SyncConfigUpdate) -> dict[str, str]:
    cfg = load_config()
    try:
        cfg.sync = SyncConfig.model_validate(body.model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_config(cfg)
    return {"status": "ok"}


@router.put("/config/general")
def update_general(body: GeneralConfigUpdate) -> dict[str, str]:
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
    cfg = load_config()
    return _build_provider_list(cfg)


@router.post("/config/ai")
def upsert_ai_provider(body: AIProviderCreate) -> dict[str, str]:
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
    if not cfg.default_ai_provider:
        cfg.default_ai_provider = body.name
    save_config(cfg)
    return {"status": "ok", "key_stored": str(key_stored)}


@router.delete("/config/ai/{name}")
def remove_ai_provider(name: str) -> dict[str, str]:
    cfg = load_config()
    before = len(cfg.ai_providers)
    cfg.ai_providers = [provider for provider in cfg.ai_providers if provider.name != name]
    if len(cfg.ai_providers) == before:
        raise HTTPException(status_code=404, detail=f"Provider '{name}'를 찾을 수 없습니다.")

    delete_api_key(name)
    if cfg.default_ai_provider == name:
        cfg.default_ai_provider = cfg.ai_providers[0].name if cfg.ai_providers else ""
    save_config(cfg)
    return {"status": "ok"}


@router.post("/config/ai/{name}/test")
def test_ai_provider(name: str) -> dict[str, Any]:
    cfg = load_config()
    provider = cfg.get_provider(name)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{name}'를 찾을 수 없습니다.")

    key = get_api_key(name)
    if not key and name != "ollama":
        return {"status": "error", "message": "API 키가 설정되지 않았습니다."}

    try:
        service = AIService(cfg)
        service._call(
            system_prompt="You are a test assistant. Reply briefly.",
            user_prompt="Reply with exactly: ok",
            provider_name=name,
        )
        return {"status": "ok", "message": "연결 성공"}
    except Exception as exc:  # pragma: no cover - UI safety
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------

@router.get("/projects")
def list_project_drafts() -> dict[str, Any]:
    projects = [_draft_payload(project) for project in pm.list_projects()]
    return {"status": "ok", "projects": projects}


@router.post("/projects")
def create_project(body: ProjectDraft) -> dict[str, Any]:
    try:
        project = pm.save_project_draft(body)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)
    return {"status": "ok", "project": _draft_payload(project)}


@router.put("/projects/{project_id}")
def update_project(project_id: str, body: ProjectDraft) -> dict[str, Any]:
    try:
        project = pm.save_project_draft(body, project_id=project_id)
    except DevfolioProjectNotFoundError as exc:
        _raise_from_devfolio(exc, status_code=404)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)
    return {"status": "ok", "project": _draft_payload(project)}


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, str]:
    try:
        pm.delete_project(project_id)
    except DevfolioProjectNotFoundError as exc:
        _raise_from_devfolio(exc, status_code=404)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# AI Intake / Draft / Saved project augmentation
# ---------------------------------------------------------------------------

@router.post("/intake/project-draft")
def intake_project_draft(body: DraftIntakeRequest) -> dict[str, Any]:
    try:
        draft = AIService(load_config()).generate_project_draft(
            raw_text=body.raw_text,
            lang=body.lang,
            provider_name=body.provider,
        )
    except DevfolioError as exc:
        _raise_from_devfolio(exc)
    return {"status": "ok", "draft": draft.model_dump(exclude_none=False)}


@router.post("/draft/generate-summary")
def generate_draft_summary(body: DraftAIRequest) -> dict[str, Any]:
    try:
        summary = AIService(load_config()).generate_draft_project_summary(
            draft=body.draft,
            lang=body.lang,
            provider_name=body.provider,
        )
    except DevfolioError as exc:
        _raise_from_devfolio(exc)
    updated = body.draft.model_copy(update={"summary": summary})
    return {"status": "ok", "draft": updated.model_dump(exclude_none=False)}


@router.post("/draft/generate-task-bullets")
def generate_draft_task_bullets(body: DraftAIRequest) -> dict[str, Any]:
    try:
        draft = AIService(load_config()).generate_draft_task_texts(
            draft=body.draft,
            lang=body.lang,
            provider_name=body.provider,
        )
    except DevfolioError as exc:
        _raise_from_devfolio(exc)
    return {"status": "ok", "draft": draft.model_dump(exclude_none=False)}


@router.post("/projects/{project_id}/generate-summary")
def generate_project_summary(project_id: str, body: SavedAIRequest) -> dict[str, Any]:
    try:
        project = pm.get_project_or_raise(project_id)
        summary = AIService(load_config()).generate_project_summary(
            project=project,
            lang=body.lang,
            provider_name=body.provider,
        )
        updated = pm.save_project_summary(project.id, summary)
    except DevfolioProjectNotFoundError as exc:
        _raise_from_devfolio(exc, status_code=404)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)
    return {"status": "ok", "project": _draft_payload(updated)}


@router.post("/projects/{project_id}/generate-task-bullets")
def generate_project_task_bullets(project_id: str, body: SavedAIRequest) -> dict[str, Any]:
    try:
        project = pm.get_project_or_raise(project_id)
        draft = pm.draft_from_project(project)
        updated_draft = AIService(load_config()).generate_draft_task_texts(
            draft=draft,
            lang=body.lang,
            provider_name=body.provider,
        )
        updated_project = pm.save_project_draft(updated_draft, project_id=project.id)
    except DevfolioProjectNotFoundError as exc:
        _raise_from_devfolio(exc, status_code=404)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)
    return {"status": "ok", "project": _draft_payload(updated_project)}


# ---------------------------------------------------------------------------
# Preview / Export
# ---------------------------------------------------------------------------

@router.post("/preview/resume")
def preview_resume(body: DraftPreviewRequest) -> dict[str, Any]:
    request = body.model_copy(update={"doc_type": "resume"})
    try:
        return _preview_response(request)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)


@router.post("/preview/portfolio")
def preview_portfolio(body: DraftPreviewRequest) -> dict[str, Any]:
    request = body.model_copy(update={"doc_type": "portfolio"})
    try:
        return _preview_response(request)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)


@router.post("/export/resume")
def export_resume(body: DraftPreviewRequest) -> dict[str, Any]:
    request = body.model_copy(update={"doc_type": "resume"})
    try:
        return _export_document(request)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)


@router.post("/export/portfolio")
def export_portfolio(body: DraftPreviewRequest) -> dict[str, Any]:
    request = body.model_copy(update={"doc_type": "portfolio"})
    try:
        return _export_document(request)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)


# ---------------------------------------------------------------------------
# Git Scan
# ---------------------------------------------------------------------------

@router.post("/scan/git")
def scan_git(body: GitScanRequest) -> dict[str, Any]:
    """Git 저장소를 스캔해 본인 커밋 기반 포트폴리오를 자동 생성한다."""
    from pathlib import Path as _Path
    from devfolio.core.git_scanner import build_project_payload, scan_repo
    from devfolio.core.storage import list_projects, save_project

    cfg = load_config()
    author_email = (body.author_email or cfg.user.email or "").strip()
    if not author_email:
        raise HTTPException(
            status_code=400,
            detail="author email이 설정되지 않았습니다. Settings > 사용자 프로필에서 이메일을 먼저 등록하세요.",
        )

    repo_path = _Path(body.repo_path.strip())
    if not repo_path.exists():
        raise HTTPException(status_code=400, detail=f"경로를 찾을 수 없습니다: {repo_path}")

    try:
        # 캐시 체크: 같은 repo_url + HEAD SHA 이면 즉시 반환
        if not body.refresh:
            from devfolio.core.git_scanner import _run_git, _detect_repo_url, _is_git_repo
            if _is_git_repo(repo_path):
                head_sha = _run_git(repo_path, ["rev-parse", "HEAD"]).strip()
                repo_url = _detect_repo_url(repo_path)
                for p in list_projects():
                    if (
                        p.repo_url
                        and p.repo_url == repo_url
                        and p.last_commit_sha == head_sha
                    ):
                        return {
                            "status": "cached",
                            "message": f"이미 최신 상태입니다 (sha={head_sha[:8]})",
                            "project_id": p.id,
                            "project_name": p.name,
                            "metrics": p.scan_metrics,
                        }

        scan_result = scan_repo(repo_path, author_email=author_email)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)

    payload = build_project_payload(scan_result)

    # 기존 프로젝트 갱신 vs 신규 등록
    existing = next(
        (p for p in list_projects() if p.repo_url and p.repo_url == payload["repo_url"]),
        None,
    )

    from devfolio.models.project import Period, Project, Task

    def _make_project(pid: str) -> Project:
        tasks = []
        for i, t in enumerate(payload["tasks"]):
            tasks.append(Task(
                id=f"task_{i+1:03d}",
                name=t["name"],
                period=Period(start=t.get("period_start"), end=t.get("period_end")),
                problem=t.get("problem", ""),
                solution=t.get("solution", ""),
                result=t.get("result", ""),
                keywords=t.get("keywords", []),
            ))
        return Project(
            id=pid,
            name=payload["name"],
            type=payload["type"],
            status=payload["status"],
            period=Period(start=payload.get("period_start"), end=payload.get("period_end")),
            role=payload.get("role", ""),
            team_size=payload.get("team_size", 1),
            tech_stack=payload.get("tech_stack", []),
            summary=payload.get("summary", ""),
            tags=payload.get("tags", []),
            tasks=tasks,
            repo_url=payload.get("repo_url", ""),
            last_commit_sha=payload.get("last_commit_sha", ""),
            scan_metrics=payload.get("scan_metrics", {}),
        )

    if existing:
        project = _make_project(existing.id)
        save_project(project)
        status = "updated"
    else:
        project_id = pm._next_project_id(payload["name"])
        project = _make_project(project_id)
        save_project(project)
        status = "created"

    metrics = payload.get("scan_metrics", {})
    return {
        "status": status,
        "project_id": project.id,
        "project_name": project.name,
        "metrics": metrics,
        "summary": payload.get("summary", ""),
        "tasks": [{"name": t.name, "result": t.result} for t in project.tasks],
    }
