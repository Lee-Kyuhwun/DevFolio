"""REST API 라우터 — Portfolio Studio + 설정 CRUD.

[Spring 비교]
  @RestController 클래스들의 집합 — JSON 을 주고받는 REST 엔드포인트 모음.
  FastAPI 의 APIRouter 가 Spring @RestController 역할을 한다.

  FastAPI 개념      ↔  Spring MVC 개념
  ──────────────────────────────────────────
  APIRouter         ↔  @RestController 클래스
  @router.get(...)  ↔  @GetMapping(...)
  @router.post(...) ↔  @PostMapping(...)
  @router.put(...)  ↔  @PutMapping(...)
  @router.delete(...)↔ @DeleteMapping(...)
  BaseModel (Request) ↔ @RequestBody DTO
  HTTPException     ↔  ResponseEntity + @ResponseStatus
  path parameter    ↔  @PathVariable
  body: SomeModel   ↔  @RequestBody SomeDto
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

# APIRouter : 라우트 그룹. [Spring] @RestController 클래스.
# HTTPException : HTTP 에러 응답 던지기. [Spring] ResponseStatusException / @ResponseStatus.
from fastapi import APIRouter, HTTPException

# BaseModel : Request/Response DTO 정의용.
# ValidationError : Pydantic 검증 실패 시 발생. [Spring] MethodArgumentNotValidException.
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

# APIRouter(tags=["studio"]) : 이 라우터의 모든 엔드포인트에 "studio" 태그를 붙인다.
# [Spring] @RequestMapping(value="/api", produces=APPLICATION_JSON) 클래스와 유사.
router = APIRouter(tags=["studio"])

# 모듈 레벨 싱글톤 — 앱 실행 중 하나의 인스턴스만 사용.
# [Spring] @Autowired ProjectManager pm; 또는 @Bean 으로 등록한 싱글톤 빈.
pm = ProjectManager()


# ---------------------------------------------------------------------------
# Request / Response 모델 (DTO)
# ---------------------------------------------------------------------------
# 아래 클래스들은 @RequestBody DTO 역할을 한다.
# FastAPI 가 요청 body JSON → Pydantic 모델로 자동 역직렬화 + 검증한다.
# [Spring] @RequestBody + @Valid 어노테이션과 동일한 효과.

class UserConfigUpdate(BaseModel):
    """사용자 프로필 업데이트 요청 DTO.

    [Spring] PUT /api/config/user 의 @RequestBody 에 해당.
    """
    name: str = ""
    email: str = ""
    github: str = ""
    blog: str = ""


class ExportConfigUpdate(BaseModel):
    """내보내기 설정 업데이트 요청 DTO."""
    default_format: str = "md"
    default_template: str = "default"
    output_dir: str = ""


class SyncConfigUpdate(BaseModel):
    """GitHub 동기화 설정 업데이트 요청 DTO."""
    enabled: bool = False
    repo_url: str = ""
    branch: str = "main"


class GeneralConfigUpdate(BaseModel):
    """일반 설정(언어, 타임존 등) 업데이트 요청 DTO."""
    default_language: str = "ko"
    timezone: str = "Asia/Seoul"
    default_ai_provider: str = ""


class AIProviderCreate(BaseModel):
    """AI Provider 생성/업데이트 요청 DTO."""
    name: str
    model: str
    # Optional[str] = None : 없어도 되는 필드. [Spring] @Nullable String apiKey.
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class GitScanRequest(BaseModel):
    """Git 저장소 스캔 요청 DTO.

    [Spring] POST /api/scan/git 의 @RequestBody.
    """
    repo_path: str
    author_email: Optional[str] = None
    # bool : 캐시를 무시하고 강제 재스캔.
    refresh: bool = False


class DraftIntakeRequest(BaseModel):
    """자유 텍스트에서 AI 초안 생성 요청 DTO."""
    raw_text: str
    lang: str = "ko"
    provider: Optional[str] = None


class DraftAIRequest(BaseModel):
    """Draft 기반 AI 문서 생성 요청 DTO."""
    # ProjectDraft : 웹 편집 중간 상태 모델.
    draft: ProjectDraft
    lang: str = "ko"
    provider: Optional[str] = None


class SavedAIRequest(BaseModel):
    """저장된 프로젝트에서 AI 문서 생성 요청 DTO."""
    lang: str = "ko"
    provider: Optional[str] = None


# ---------------------------------------------------------------------------
# 공용 헬퍼
# ---------------------------------------------------------------------------

def _format_error(exc: DevfolioError) -> str:
    """DevfolioError 를 HTTP 응답 detail 문자열로 변환한다."""
    if exc.hint:
        return f"{exc.message} ({exc.hint})"
    return exc.message


def _raise_from_devfolio(exc: DevfolioError, status_code: int = 400) -> None:
    """DevfolioError → HTTPException 으로 변환해 raise 한다.

    [Spring 비교]
      @ExceptionHandler(DevfolioError.class) 에서 ResponseEntity.badRequest() 로 변환.
    """
    # raise ... from exc : 원인 예외를 체이닝. [Spring] new RuntimeException(message, cause).
    raise HTTPException(status_code=status_code, detail=_format_error(exc)) from exc


def _build_provider_list(cfg) -> list[dict[str, Any]]:
    """AI Provider 목록을 API 응답용 dict 리스트로 변환한다 (API 키는 마스킹)."""
    result = []
    for provider in cfg.ai_providers:
        # get_api_key() : keyring → 환경변수 순서로 API 키 조회 (security.py).
        key = get_api_key(provider.name)
        if key:
            # mask_api_key() : "sk-abcd..." → "sk-ab***cd" 형태로 마스킹.
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
                # 기본 Provider 여부.
                "is_default": provider.name == cfg.default_ai_provider,
            }
        )
    return result


def _env_var_name(provider: str) -> str:
    """Provider 이름 → 환경변수 이름 매핑."""
    mapping = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "cohere": "COHERE_API_KEY",
    }
    # dict.get(key, default) : 없으면 default 반환. [Spring] Map.getOrDefault(key, default).
    return mapping.get(provider, f"{provider.upper()}_API_KEY")


def _draft_payload(project) -> dict[str, Any]:
    """Project 를 웹 편집용 draft dict 로 변환한다."""
    # pm.draft_from_project() : Project → ProjectDraft 변환 (DTO 변환).
    # .model_dump(exclude_none=False) : None 포함해서 dict 로 직렬화.
    return pm.draft_from_project(project).model_dump(exclude_none=False)


def _resolve_projects(request: DraftPreviewRequest):
    """DraftPreviewRequest 에서 실제 Project 목록을 결정한다.

    source="draft" 이면 미저장 draft 를 사용하고,
    project_ids 가 있으면 해당 ID 목록만, 없으면 전체 프로젝트를 사용한다.
    """
    if request.source == "draft":
        # transient=True : 저장 없이 미리보기 전용 Project 생성.
        return [pm.project_from_draft(request.draft_project, transient=True)]

    if request.project_ids:
        try:
            # list comprehension : project_ids 의 각 ID 에 대해 get_project_or_raise() 호출.
            # [Spring] projectIds.stream().map(pm::getProjectOrThrow).collect(toList()).
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
    """DraftPreviewRequest 로부터 Markdown 문서를 렌더링한다.

    반환값: (markdown 문자열, project 목록, template 이름)
    tuple[A, B, C] : 세 값을 하나로 묶어 반환. [Spring] Triple / custom VO.
    """
    cfg = load_config()
    template_name = request.template or cfg.export.default_template or "default"
    projects = _resolve_projects(request)
    # TemplateEngine().render() : Jinja2 로 Markdown 렌더링.
    markdown = TemplateEngine().render(
        projects=projects,
        config=cfg,
        template_name=template_name,
        doc_type=request.doc_type,
    )
    return markdown, projects, template_name


def _preview_response(request: DraftPreviewRequest) -> dict[str, Any]:
    """Markdown + HTML 미리보기 응답을 생성한다."""
    markdown, projects, template_name = _render_document(request)
    engine = ExportEngine()
    # _md_to_html_body() : Markdown → HTML body 변환.
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
    """문서를 지정한 포맷(md/html/pdf/docx/json/csv)으로 내보낸다."""
    cfg = load_config()
    # (A or B or C).lower() : 우선순위대로 폴백.
    fmt = (request.format or cfg.export.default_format or "html").lower()
    markdown, projects, template_name = _render_document(request)
    engine = ExportEngine()

    # dict : 지원 포맷 화이트리스트.
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
            # list comprehension 으로 Project 목록을 dict 리스트로 직렬화.
            # [Spring] ObjectMapper.writeValueAsString(projects.stream().map(Project::toDto).collect(toList())).
            json.dumps([project.model_dump() for project in projects], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    elif fmt == "csv":
        output_path = engine.export_csv(projects, filename)
    else:
        # dict 로 포맷 → 내보내기 함수 매핑. [Spring] switch(fmt) { ... }.
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

# @router.get("/config") : GET /api/config 요청 → 이 함수 실행.
# [Spring] @GetMapping("/config") public ResponseEntity<Map<...>> getConfig().
@router.get("/config")
def get_config() -> dict[str, Any]:
    """전체 설정을 반환한다 (API 키는 마스킹)."""
    cfg = load_config()
    return {
        # .model_dump() : Pydantic 모델 → dict. [Spring] ObjectMapper.convertValue(cfg.getUser(), Map.class).
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

# @router.put("/config/user") : PUT /api/config/user 요청.
# body: UserConfigUpdate : request body 를 자동으로 UserConfigUpdate 모델로 역직렬화.
# [Spring] @PutMapping("/config/user") public ResponseEntity<?> update(@RequestBody UserConfigUpdate body).
@router.put("/config/user")
def update_user(body: UserConfigUpdate) -> dict[str, str]:
    cfg = load_config()
    try:
        # body.model_dump() : DTO → dict. model_validate() : dict → Config 모델.
        # [Spring] BeanUtils.copyProperties(body, cfg.getUser()).
        cfg.user = UserConfig.model_validate(body.model_dump())
    except ValidationError as exc:
        # 422 Unprocessable Entity : 요청 형식은 맞지만 값이 유효하지 않을 때.
        # [Spring] @ResponseStatus(HttpStatus.UNPROCESSABLE_ENTITY) 와 동일.
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
    """AI Provider 를 등록하거나 갱신한다."""
    cfg = load_config()

    key_stored = False
    if body.api_key:
        # store_api_key() : keyring 또는 환경변수에 API 키 저장. 성공이면 True.
        key_stored = store_api_key(body.name, body.api_key)

    provider = AIProviderConfig(
        name=body.name,
        model=body.model,
        key_stored=key_stored,
        # body.base_url or None : 빈 문자열이면 None 으로 처리.
        base_url=body.base_url or None,
    )
    # upsert_provider() : 있으면 교체, 없으면 추가. [Spring] JpaRepository.save().
    cfg.upsert_provider(provider)
    # 기본 Provider 가 없으면 방금 추가한 것을 기본으로 설정.
    if not cfg.default_ai_provider:
        cfg.default_ai_provider = body.name
    save_config(cfg)
    return {"status": "ok", "key_stored": str(key_stored)}


# @router.delete("/config/ai/{name}") : DELETE /api/config/ai/anthropic 등.
# name: str : URL 경로 변수. [Spring] @PathVariable String name.
@router.delete("/config/ai/{name}")
def remove_ai_provider(name: str) -> dict[str, str]:
    """AI Provider 를 삭제한다."""
    cfg = load_config()
    before = len(cfg.ai_providers)
    # list comprehension 으로 해당 provider 만 제외.
    cfg.ai_providers = [provider for provider in cfg.ai_providers if provider.name != name]
    if len(cfg.ai_providers) == before:
        # 삭제할 대상이 없으면 404. [Spring] ResponseEntity.notFound().
        raise HTTPException(status_code=404, detail=f"Provider '{name}'를 찾을 수 없습니다.")

    # delete_api_key() : keyring 에서 API 키 삭제.
    delete_api_key(name)
    if cfg.default_ai_provider == name:
        # 삭제된 Provider 가 기본값이었으면 첫 번째 Provider 로 변경.
        cfg.default_ai_provider = cfg.ai_providers[0].name if cfg.ai_providers else ""
    save_config(cfg)
    return {"status": "ok"}


@router.post("/config/ai/{name}/test")
def test_ai_provider(name: str) -> dict[str, Any]:
    """AI Provider 연결을 테스트한다."""
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
    """모든 프로젝트를 draft 형태로 반환한다."""
    # list comprehension : 프로젝트 목록 → draft dict 목록.
    projects = [_draft_payload(project) for project in pm.list_projects()]
    return {"status": "ok", "projects": projects}


@router.post("/projects")
def create_project(body: ProjectDraft) -> dict[str, Any]:
    """새 프로젝트를 생성한다."""
    try:
        project = pm.save_project_draft(body)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)
    return {"status": "ok", "project": _draft_payload(project)}


# {project_id} : URL 경로 변수. [Spring] @PathVariable String projectId.
@router.put("/projects/{project_id}")
def update_project(project_id: str, body: ProjectDraft) -> dict[str, Any]:
    """기존 프로젝트를 수정한다."""
    try:
        project = pm.save_project_draft(body, project_id=project_id)
    except DevfolioProjectNotFoundError as exc:
        _raise_from_devfolio(exc, status_code=404)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)
    return {"status": "ok", "project": _draft_payload(project)}


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, str]:
    """프로젝트를 삭제한다."""
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
    """자유 텍스트(이력서, 메모 등)에서 AI 로 프로젝트 초안을 생성한다."""
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
    """Draft 기반으로 AI 프로젝트 요약을 생성한다."""
    try:
        summary = AIService(load_config()).generate_draft_project_summary(
            draft=body.draft,
            lang=body.lang,
            provider_name=body.provider,
        )
    except DevfolioError as exc:
        _raise_from_devfolio(exc)
    # model_copy(update={"summary": summary}) : 기존 draft 를 복사하면서 summary 만 교체.
    # [Spring] BeanUtils.copyProperties(body.draft, updated); updated.setSummary(summary).
    updated = body.draft.model_copy(update={"summary": summary})
    return {"status": "ok", "draft": updated.model_dump(exclude_none=False)}


@router.post("/draft/generate-task-bullets")
def generate_draft_task_bullets(body: DraftAIRequest) -> dict[str, Any]:
    """Draft 의 각 Task 에 AI 문구를 생성한다."""
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
    """저장된 프로젝트에 AI 요약을 생성하고 저장한다."""
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
    """저장된 프로젝트의 각 Task 에 AI 문구를 생성하고 저장한다."""
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
    """이력서(resume) 미리보기 HTML/Markdown 을 반환한다."""
    # model_copy(update={"doc_type": "resume"}) : doc_type 만 강제로 "resume" 로 설정.
    request = body.model_copy(update={"doc_type": "resume"})
    try:
        return _preview_response(request)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)


@router.post("/preview/portfolio")
def preview_portfolio(body: DraftPreviewRequest) -> dict[str, Any]:
    """포트폴리오(portfolio) 미리보기 HTML/Markdown 을 반환한다."""
    request = body.model_copy(update={"doc_type": "portfolio"})
    try:
        return _preview_response(request)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)


@router.post("/export/resume")
def export_resume(body: DraftPreviewRequest) -> dict[str, Any]:
    """이력서를 지정 포맷으로 내보낸다."""
    request = body.model_copy(update={"doc_type": "resume"})
    try:
        return _export_document(request)
    except DevfolioError as exc:
        _raise_from_devfolio(exc)


@router.post("/export/portfolio")
def export_portfolio(body: DraftPreviewRequest) -> dict[str, Any]:
    """포트폴리오를 지정 포맷으로 내보낸다."""
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
    """Git 저장소를 스캔해 본인 커밋 기반 포트폴리오를 자동 생성한다.

    [Spring 비교]
      POST /api/scan/git — @RequestBody GitScanRequest, 비즈니스 로직이 많은 핸들러.
      캐시 체크 → 스캔 → Project 생성/갱신의 3단계로 구성.
    """
    # 함수 안에서 import : lazy import 패턴. 무거운 모듈을 실제 호출 시에만 로드.
    from pathlib import Path as _Path
    from devfolio.core.git_scanner import build_project_payload, scan_repo
    from devfolio.core.storage import list_projects, save_project

    cfg = load_config()
    # body.author_email or cfg.user.email or "" : 우선순위대로 폴백.
    author_email = (body.author_email or cfg.user.email or "").strip()
    if not author_email:
        raise HTTPException(
            status_code=400,
            detail="author email이 설정되지 않았습니다. Settings > 사용자 프로필에서 이메일을 먼저 등록하세요.",
        )

    # _Path(body.repo_path.strip()) : 요청 경로를 Path 객체로 변환.
    repo_path = _Path(body.repo_path.strip())
    if not repo_path.exists():
        raise HTTPException(status_code=400, detail=f"경로를 찾을 수 없습니다: {repo_path}")

    try:
        # 캐시 체크: refresh=False 이고 같은 repo_url + HEAD SHA 가 있으면 재분석 불필요.
        if not body.refresh:
            from devfolio.core.git_scanner import _run_git, _detect_repo_url, _is_git_repo
            if _is_git_repo(repo_path):
                head_sha = _run_git(repo_path, ["rev-parse", "HEAD"]).strip()
                repo_url = _detect_repo_url(repo_path)
                # next(generator, None) : 첫 번째 매칭 프로젝트, 없으면 None.
                for p in list_projects():
                    if (
                        p.repo_url
                        and p.repo_url == repo_url
                        and p.last_commit_sha == head_sha
                    ):
                        # 캐시 히트 — 이미 최신이므로 즉시 반환.
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

    # build_project_payload() : ScanResult → Project 생성 dict.
    payload = build_project_payload(scan_result)

    # 같은 repo_url 을 가진 기존 프로젝트가 있으면 갱신, 없으면 신규 등록.
    # next(generator, None) 으로 첫 매칭 항목 찾기.
    existing = next(
        (p for p in list_projects() if p.repo_url and p.repo_url == payload["repo_url"]),
        None,
    )

    from devfolio.models.project import Period, Project, Task

    def _make_project(pid: str) -> Project:
        """payload dict 에서 Project 객체를 생성하는 내부 헬퍼."""
        tasks = []
        # enumerate(iterable) : (인덱스, 값) 쌍으로 순회.
        # [Spring] IntStream.range(0, tasks.size()).forEach(i -> ...).
        for i, t in enumerate(payload["tasks"]):
            tasks.append(Task(
                # f"task_{i+1:03d}" : 3자리 숫자 패딩. task_001, task_002, ...
                id=f"task_{i+1:03d}",
                name=t["name"],
                # dict.get(key, default) : 키 없으면 default. [Spring] Map.getOrDefault(key, default).
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
        # 기존 프로젝트 갱신 (ID 유지).
        project = _make_project(existing.id)
        save_project(project)
        status = "updated"
    else:
        # 신규 프로젝트 등록.
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
        # list comprehension : Task 요약 목록. [Spring] tasks.stream().map(t -> Map.of(...)).collect(toList()).
        "tasks": [{"name": t.name, "result": t.result} for t in project.tasks],
    }
