"""REST API 라우터 — Portfolio Studio + 설정 CRUD."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

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
    model: str = ""
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class GitScanRequest(BaseModel):
    repo_path: str
    author_email: Optional[str] = None
    refresh: bool = False
    analyze: bool = False
    lang: str = "ko"
    provider: Optional[str] = None


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


def _default_model_name(provider: str) -> str:
    mapping = {
        "anthropic": "claude-sonnet-4-20250514",
        "openai": "gpt-4o",
        "gemini": "gemini-1.5-flash",
        "ollama": "llama3.2",
    }
    return mapping.get(provider, "")


def _scan_repo_path_candidates(raw_path: str) -> list[Path]:
    raw = (raw_path or "").strip()
    if not raw:
        return []

    expanded = Path(raw).expanduser()
    candidates: list[Path] = [expanded.resolve(strict=False)]
    docker_repo_root = Path(os.environ.get("DEVFOLIO_DOCKER_REPO_ROOT", "/home/user"))
    parts = expanded.parts

    # Docker에서 호스트 홈 경로(/Users/<name>/..., /home/<name>/...)를 /home/user/...로 변환
    if len(parts) >= 4 and parts[1] in {"Users", "home"}:
        mapped = docker_repo_root.joinpath(*parts[3:]).resolve(strict=False)
        candidates.append(mapped)

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _directory_picker_roots() -> list[Path]:
    candidates: list[Path] = []

    docker_repo_root = (os.environ.get("DEVFOLIO_DOCKER_REPO_ROOT") or "").strip()
    if docker_repo_root:
        candidates.append(Path(docker_repo_root).resolve(strict=False))

    cwd = Path.cwd().resolve(strict=False)
    home = Path.home().resolve(strict=False)

    candidates.append(cwd)
    if str(home) != "/root" or not docker_repo_root:
        candidates.append(home)

    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_dir():
            continue
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        roots.append(candidate)
    return roots


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_directory_browser_path(raw_path: Optional[str]) -> tuple[Path, list[Path]]:
    roots = _directory_picker_roots()
    if not roots:
        raise DevfolioError("탐색 가능한 디렉터리가 없습니다.")

    if not raw_path:
        return roots[0], roots

    current = Path(raw_path).expanduser().resolve(strict=False)
    if not any(_is_within_root(current, root) or current == root for root in roots):
        raise DevfolioError(
            f"허용되지 않은 경로입니다: {raw_path}",
            hint="폴더 선택기는 접근 가능한 루트 디렉터리 안에서만 탐색할 수 있습니다.",
        )
    if not current.exists() or not current.is_dir():
        raise DevfolioError(
            f"디렉터리가 존재하지 않습니다: {raw_path}",
            hint="상위 폴더를 선택한 뒤 다시 탐색하세요.",
        )
    return current, roots


def _looks_like_remote_repo_url(raw_path: str) -> bool:
    raw = (raw_path or "").strip()
    if not raw:
        return False
    if raw.startswith("git@"):
        return True
    parsed = urlparse(raw)
    return parsed.scheme in {"http", "https", "ssh"} and bool(parsed.netloc)


def _resolve_scan_repo_path(raw_path: str) -> tuple[Path, Optional[str]]:
    if _looks_like_remote_repo_url(raw_path):
        raise DevfolioError(
            f"원격 Git URL은 바로 스캔할 수 없습니다: {raw_path}",
            hint="GitHub URL 대신 로컬에 clone된 저장소 폴더 경로를 입력하세요. 예: /Users/you/projects/my-app",
        )

    candidates = _scan_repo_path_candidates(raw_path)
    for index, candidate in enumerate(candidates):
        if candidate.is_dir():
            translated_from = raw_path if index > 0 else None
            return candidate, translated_from

    raise DevfolioError(
        f"경로가 존재하지 않습니다: {raw_path}",
        hint="Docker 사용 중이면 호스트 경로를 그대로 붙여넣어도 되지만, 해당 경로가 REPOS_DIR 아래에 마운트되어 있어야 합니다.",
    )


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
        model=(body.model or _default_model_name(body.name)).strip(),
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
# Directory Browser
# ---------------------------------------------------------------------------

@router.get("/fs/directories")
def list_directories(path: Optional[str] = None) -> dict[str, Any]:
    try:
        current, roots = _resolve_directory_browser_path(path)
        root_for_current = next((root for root in roots if current == root or _is_within_root(current, root)), roots[0])
        parent_path = None
        if current != root_for_current:
            parent_path = str(current.parent)

        entries: list[dict[str, Any]] = []
        try:
            children: list[Path] = []
            for child in current.iterdir():
                try:
                    if child.is_dir():
                        children.append(child)
                except OSError:
                    continue
            children = sorted(children, key=lambda child: child.name.lower())[:200]
        except OSError as exc:
            raise DevfolioError(
                f"디렉터리를 읽을 수 없습니다: {current}",
                hint=str(exc),
            ) from exc

        for child in children:
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "is_git_repo": (child / ".git").exists(),
                }
            )

        return {
            "status": "ok",
            "current_path": str(current),
            "parent_path": parent_path,
            "roots": [str(root) for root in roots],
            "entries": entries,
        }
    except DevfolioError as exc:
        _raise_from_devfolio(exc)


# ---------------------------------------------------------------------------
# Git Scan
# ---------------------------------------------------------------------------

@router.post("/scan/git")
def scan_git(body: GitScanRequest) -> dict[str, Any]:
    """Git 저장소를 스캔해 포트폴리오 payload를 반환한다. analyze=True 면 AI 딥 분석도 수행."""
    from devfolio.core.git_scanner import build_project_payload, scan_repo
    from devfolio.log import get_logger

    logger = get_logger(__name__)

    try:
        repo_path, translated_from = _resolve_scan_repo_path(body.repo_path)
        cfg = load_config()
        author_email = (body.author_email or cfg.user.email or "").strip()
        if not author_email:
            raise DevfolioError(
                "author_email 이 필요합니다.",
                hint="요청 body 또는 설정의 user.email을 확인하세요.",
            )

        logger.info(
            "Git scan API 요청: input=%s resolved=%s author=%s refresh=%s analyze=%s",
            body.repo_path,
            repo_path,
            author_email,
            body.refresh,
            body.analyze,
        )
        if translated_from:
            logger.info("Docker 경로 변환 적용: %s -> %s", translated_from, repo_path)

        # analyze=True 면 캐시를 건너뛰고 항상 재스캔
        if not body.analyze and not body.refresh:
            from devfolio.core.storage import list_projects
            for project in list_projects():
                if project.repo_url:
                    scan_check = scan_repo(repo_path, author_email=author_email, analyze=False)
                    if project.last_commit_sha == scan_check.head_sha:
                        payload = build_project_payload(scan_check)
                        logger.info("Git scan cache hit: repo=%s head=%s", repo_path, scan_check.head_sha[:8])
                        return {"status": "ok", "cached": True, "analyzed": False, "payload": payload}
                    break  # 같은 레포 다른 sha → 재스캔

        scan_result = scan_repo(repo_path, author_email=author_email, analyze=body.analyze)

        ai_analysis: Optional[dict] = None
        if body.analyze and scan_result.project_context:
            try:
                scan_metrics = {
                    "commits": scan_result.commit_count,
                    "period_months": 0,
                    "languages": {k: v for k, v in scan_result.languages.most_common(5)},
                }
                ai_analysis = AIService(cfg).analyze_project_from_code(
                    repo_name=repo_path.name,
                    project_context=scan_result.project_context,
                    scan_metrics=scan_metrics,
                    lang=body.lang,
                    provider_name=body.provider,
                )
            except Exception as exc:
                logger.warning("AI 딥 분석 실패 (기본 스캔 결과로 계속): %s", exc)

        payload = build_project_payload(scan_result, ai_analysis=ai_analysis)
        return {
            "status": "ok",
            "cached": False,
            "analyzed": ai_analysis is not None,
            "payload": payload,
        }
    except DevfolioError as exc:
        logger.warning("Git scan API 실패: input=%s reason=%s", body.repo_path, exc.message)
        _raise_from_devfolio(exc)


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
