"""성과노트 REST API.

기존 DevFolio API(`/api/scan/git` 등)는 별도 앱에서 그대로 유지되고,
이 라우터는 새 제품의 화면·CLI 가 쓰는 계약이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from impactnote import APP_NAME, APP_NAME_EN, __version__
from impactnote.core import report as report_engine
from impactnote.core.ai import ConsentRequired, analyze_activity, suggest_from_git
from impactnote.core.intel.discovery import validate_project_path
from impactnote.core.migrate import legacy_available, run_migration
from impactnote.core.models import (
    ACTIVITY_TYPES,
    ACHIEVEMENT_STATUSES,
    EVIDENCE_TYPES,
    IMPACT_CATEGORIES,
    REPORT_TEMPLATES,
    Report,
)
from impactnote.core.service import ImpactService, NotFound
from impactnote.core.store import data_dir

router = APIRouter(tags=["impactnote"])


def _service() -> ImpactService:
    return ImpactService()


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _model_payload(item: Any) -> dict:
    return item.model_dump(mode="json")


# ---------------------------------------------------------------------------
# 메타·대시보드
# ---------------------------------------------------------------------------


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app": APP_NAME,
        "app_en": APP_NAME_EN,
        "version": __version__,
        "storage": "local",
    }


@router.get("/meta")
def meta() -> dict[str, Any]:
    service = _service()
    settings = service.settings()
    return {
        "app": APP_NAME,
        "app_en": APP_NAME_EN,
        "version": __version__,
        "activity_types": list(ACTIVITY_TYPES),
        "impact_categories": list(IMPACT_CATEGORIES),
        "evidence_types": list(EVIDENCE_TYPES),
        "achievement_statuses": list(ACHIEVEMENT_STATUSES),
        "templates": REPORT_TEMPLATES,
        "sections": report_engine.SECTIONS,
        "activity_type_labels": report_engine.ACTIVITY_TYPE_LABELS,
        "impact_labels": report_engine.IMPACT_LABELS,
        "status_labels": report_engine.STATUS_LABELS,
        "settings": _model_payload(settings),
        "legacy_available": legacy_available(),
        "external_ai_enabled": settings.external_ai_consent,
        "intel_quality_labels": {
            "VERIFIED": "검증됨",
            "SUPPORTED_INFERENCE": "근거 기반 추론",
            "HYPOTHESIS": "가설",
            "INSUFFICIENT_EVIDENCE": "근거 부족",
        },
        "intel_doc_kinds": {
            "requirements": "요구사항·기획",
            "design": "설계·의사결정",
            "technical_review": "기술 검토",
            "implementation": "구현 설명",
            "incident": "장애 분석",
            "test": "테스트·검증",
            "performance": "성능 측정",
            "deployment": "배포·운영",
            "report": "업무 결과·보고",
            "reference": "참고 자료",
        },
    }


@router.get("/dashboard")
def dashboard() -> dict[str, Any]:
    service = _service()
    data = service.dashboard()
    return {
        "counts": data["counts"],
        "week": _period_brief(data["week"]),
        "month": _period_brief(data["month"]),
        "quarter": _period_brief(data["quarter"]),
        "in_progress": [_model_payload(item) for item in data["in_progress"]],
        "recent_reports": [_model_payload(item) for item in data["recent_reports"]],
        "has_data": bool(service.activities() or service.achievements()),
    }


def _period_brief(bundle: dict) -> dict[str, Any]:
    activities = bundle["activities"]
    achievements = bundle["achievements"]
    return {
        "start": bundle["start"],
        "end": bundle["end"],
        "activity_count": len(activities),
        "achievement_count": len(achievements),
        "verified_count": sum(1 for item in achievements if item.status == "verified"),
        "needs_review_count": sum(
            1 for item in achievements if item.status in {"needs_review", "user_input"}
        ),
        "titles": [item.title for item in achievements[:3]],
    }


# ---------------------------------------------------------------------------
# 업무 기록
# ---------------------------------------------------------------------------


@router.get("/activities")
def list_activities(
    start: Optional[str] = None,
    end: Optional[str] = None,
    status: Optional[str] = None,
) -> dict[str, Any]:
    items = _service().activities()
    if start and end:
        from impactnote.core.periods import select_activities

        items = select_activities(items, start, end)
    if status:
        items = [item for item in items if item.status == status]
    return {"status": "ok", "activities": [_model_payload(item) for item in items]}


@router.post("/activities", status_code=201)
def create_activity(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        activity = _service().create_activity(payload)
    except Exception as exc:  # noqa: BLE001 — 검증 실패는 400 으로 돌려준다
        raise _fail(exc) from exc
    return {"status": "ok", "activity": _model_payload(activity)}


@router.get("/activities/{activity_id}")
def get_activity(activity_id: str) -> dict[str, Any]:
    try:
        return {
            "status": "ok",
            "activity": _model_payload(_service().activity(activity_id)),
        }
    except Exception as exc:
        raise _fail(exc) from exc


@router.patch("/activities/{activity_id}")
def update_activity(activity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return {
            "status": "ok",
            "activity": _model_payload(
                _service().update_activity(activity_id, payload)
            ),
        }
    except Exception as exc:
        raise _fail(exc) from exc


@router.delete("/activities/{activity_id}")
def delete_activity(activity_id: str) -> dict[str, Any]:
    deleted = _service().delete_activity(activity_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="업무 기록을 찾을 수 없습니다.")
    return {"status": "ok", "deleted": activity_id}


# ---------------------------------------------------------------------------
# 성과
# ---------------------------------------------------------------------------


@router.get("/achievements")
def list_achievements(status: Optional[str] = None) -> dict[str, Any]:
    items = _service().achievements()
    if status:
        items = [item for item in items if item.status == status]
    return {"status": "ok", "achievements": [_model_payload(item) for item in items]}


@router.post("/achievements", status_code=201)
def create_achievement(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        achievement = _service().create_achievement(payload)
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "achievement": _model_payload(achievement)}


@router.post("/achievements/from-activities", status_code=201)
def achievements_from_activities(payload: dict[str, Any]) -> dict[str, Any]:
    activity_ids = payload.get("activity_ids") or []
    if not isinstance(activity_ids, list) or not activity_ids:
        raise HTTPException(status_code=400, detail="activity_ids 가 필요합니다.")
    try:
        achievement = _service().create_achievement_from_activities(
            [str(item) for item in activity_ids], title=str(payload.get("title") or "")
        )
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "achievement": _model_payload(achievement)}


@router.patch("/achievements/{achievement_id}")
def update_achievement(achievement_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return {
            "status": "ok",
            "achievement": _model_payload(
                _service().update_achievement(achievement_id, payload)
            ),
        }
    except Exception as exc:
        raise _fail(exc) from exc


@router.delete("/achievements/{achievement_id}")
def delete_achievement(achievement_id: str) -> dict[str, Any]:
    if not _service().delete_achievement(achievement_id):
        raise HTTPException(status_code=404, detail="성과를 찾을 수 없습니다.")
    return {"status": "ok", "deleted": achievement_id}


@router.post("/achievements/{achievement_id}/evidence")
def link_evidence(achievement_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    evidence_ids = [str(item) for item in (payload.get("evidence_ids") or [])]
    if not evidence_ids:
        raise HTTPException(status_code=400, detail="evidence_ids 가 필요합니다.")
    try:
        achievement = _service().link_evidence(achievement_id, evidence_ids)
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "achievement": _model_payload(achievement)}


@router.post("/achievements/{achievement_id}/metrics", status_code=201)
def add_metric(achievement_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        metric = _service().add_metric(achievement_id, payload)
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "metric": _model_payload(metric)}


@router.delete("/metrics/{metric_id}")
def delete_metric(metric_id: str) -> dict[str, Any]:
    if not _service().delete_metric(metric_id):
        raise HTTPException(status_code=404, detail="지표를 찾을 수 없습니다.")
    return {"status": "ok", "deleted": metric_id}


# ---------------------------------------------------------------------------
# 근거
# ---------------------------------------------------------------------------


@router.get("/evidence")
def list_evidence() -> dict[str, Any]:
    return {
        "status": "ok",
        "evidence": [_model_payload(item) for item in _service().evidence()],
    }


@router.post("/evidence", status_code=201)
def create_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        evidence = _service().create_evidence(payload)
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "evidence": _model_payload(evidence)}


@router.patch("/evidence/{evidence_id}")
def update_evidence(evidence_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return {
            "status": "ok",
            "evidence": _model_payload(
                _service().update_evidence(evidence_id, payload)
            ),
        }
    except Exception as exc:
        raise _fail(exc) from exc


@router.delete("/evidence/{evidence_id}")
def delete_evidence(evidence_id: str) -> dict[str, Any]:
    if not _service().delete_evidence(evidence_id):
        raise HTTPException(status_code=404, detail="근거를 찾을 수 없습니다.")
    return {"status": "ok", "deleted": evidence_id}


# ---------------------------------------------------------------------------
# AI 성과 분석
# ---------------------------------------------------------------------------


@router.get("/analyses")
def list_analyses(activity_id: Optional[str] = None) -> dict[str, Any]:
    items = _service().analyses()
    if activity_id:
        items = [item for item in items if item.activity_id == activity_id]
    return {"status": "ok", "analyses": [_model_payload(item) for item in items]}


@router.post("/ai/analyze")
def ai_analyze(payload: dict[str, Any]) -> dict[str, Any]:
    activity_id = str(payload.get("activity_id") or "")
    if not activity_id:
        raise HTTPException(status_code=400, detail="activity_id 가 필요합니다.")
    try:
        analysis = analyze_activity(
            _service(), activity_id, provider=payload.get("provider") or None
        )
    except ConsentRequired as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "analysis": _model_payload(analysis)}


@router.post("/ai/analyses/{analysis_id}/apply", status_code=201)
def apply_analysis(analysis_id: str) -> dict[str, Any]:
    try:
        achievement = _service().apply_analysis(analysis_id)
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "achievement": _model_payload(achievement)}


@router.post("/git/import")
def git_import(payload: dict[str, Any]) -> dict[str, Any]:
    repo_path = str(payload.get("repo_path") or "").strip()
    author_email = str(payload.get("author_email") or "").strip()
    if not repo_path or not author_email:
        raise HTTPException(
            status_code=400, detail="repo_path 와 author_email 이 필요합니다."
        )
    if not Path(repo_path).exists():
        raise HTTPException(status_code=400, detail="저장소 경로를 찾을 수 없습니다.")
    try:
        summary = suggest_from_git(
            _service(),
            repo_path=repo_path,
            author_email=author_email,
            limit=int(payload.get("limit") or 20),
        )
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", **summary}


# ---------------------------------------------------------------------------
# 보고서·제출 이력
# ---------------------------------------------------------------------------


@router.post("/reports", status_code=201)
def create_report(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        report = report_engine.create_report(
            _service(),
            template=str(payload.get("template") or "monthly"),
            period_kind=str(payload.get("period_kind") or "month"),
            reference=payload.get("reference") or None,
            start=payload.get("start") or None,
            end=payload.get("end") or None,
            title=str(payload.get("title") or ""),
            custom_sections=payload.get("custom_sections") or None,
            char_limit=int(payload.get("char_limit") or 0),
            fmt=str(payload.get("format") or "md"),
        )
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "report": _model_payload(report)}


@router.get("/reports")
def list_reports(status: Optional[str] = None) -> dict[str, Any]:
    items = _service().reports()
    if status:
        items = [item for item in items if item.status == status]
    return {"status": "ok", "reports": [_model_payload(item) for item in items]}


@router.get("/reports/{report_id}")
def get_report(report_id: str) -> dict[str, Any]:
    try:
        return {"status": "ok", "report": _model_payload(_service().report(report_id))}
    except Exception as exc:
        raise _fail(exc) from exc


@router.patch("/reports/{report_id}")
def update_report(report_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    service = _service()
    try:
        report = service.report(report_id)
        if "status" in payload:
            report.status = str(payload["status"])
        if "note" in payload:
            report.note = str(payload["note"])[:1000]
        from impactnote.core.models import utc_now

        report.updated_at = utc_now()
        service.save_report(report)
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "report": _model_payload(report)}


@router.get("/reports/{report_id}/download")
def download_report(report_id: str, format: str = "md") -> FileResponse:
    service = _service()
    try:
        report = service.report(report_id)
    except Exception as exc:
        raise _fail(exc) from exc
    try:
        path = report_engine.export_report(service, report, format)
    except Exception as exc:
        raise _fail(exc) from exc
    exports = (data_dir() / "exports").resolve()
    if not path.resolve().is_relative_to(exports):
        raise HTTPException(
            status_code=400, detail="내보내기 경로가 올바르지 않습니다."
        )
    media = {
        "md": "text/markdown",
        "txt": "text/plain",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
        "csv": "text/csv",
    }.get(format, "application/octet-stream")
    report.format = format
    report.file_name = path.name
    service.save_report(report)
    return FileResponse(path, media_type=media, filename=path.name)


# ---------------------------------------------------------------------------
# 설정·마이그레이션
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 프로젝트 인텔리전스
# ---------------------------------------------------------------------------


@router.post("/projects/analyze")
def analyze_project_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    project_path = str(payload.get("project_path") or payload.get("path") or "").strip()
    if not project_path:
        raise HTTPException(status_code=400, detail="project_path 가 필요합니다.")
    try:
        target = validate_project_path(project_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        analysis = _service().analyze_project(
            str(target),
            author_email=str(payload.get("author_email") or ""),
            use_ai=bool(payload.get("use_ai", True)),
            provider=payload.get("provider") or None,
            force=bool(payload.get("force")),
        )
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "analysis": _model_payload(analysis)}


@router.get("/projects/analyses")
def list_project_analyses() -> dict[str, Any]:
    items = []
    for analysis in _service().project_analyses():
        items.append(
            {
                "id": analysis.id,
                "project_name": analysis.project_name,
                "project_path": analysis.project_path,
                "created_at": analysis.created_at,
                "status": analysis.status,
                "head_sha": analysis.head_sha,
                "incremental": analysis.incremental,
                "stats": analysis.stats,
                "quality_summary": analysis.quality_summary,
                "candidate_count": len(analysis.candidates),
                "ai_status": analysis.ai.status,
            }
        )
    return {"status": "ok", "analyses": items}


@router.get("/projects/analyses/{analysis_id}")
def get_project_analysis(analysis_id: str) -> dict[str, Any]:
    try:
        analysis = _service().project_analysis(analysis_id)
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "analysis": _model_payload(analysis)}


@router.patch("/projects/analyses/{analysis_id}/candidates/{candidate_id}")
def update_project_candidate(
    analysis_id: str, candidate_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    try:
        analysis = _service().update_project_candidate(
            analysis_id, candidate_id, payload
        )
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "analysis": _model_payload(analysis)}


@router.post("/projects/analyses/{analysis_id}/candidates/{candidate_id}/merge")
def merge_project_candidate(
    analysis_id: str, candidate_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    target_id = str(payload.get("target_id") or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="target_id 가 필요합니다.")
    try:
        analysis = _service().merge_project_candidates(
            analysis_id, candidate_id, target_id
        )
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "analysis": _model_payload(analysis)}


@router.post(
    "/projects/analyses/{analysis_id}/candidates/{candidate_id}/apply",
    status_code=201,
)
def apply_project_candidate(
    analysis_id: str, candidate_id: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    body = payload or {}
    try:
        achievement = _service().apply_project_candidate(
            analysis_id,
            candidate_id,
            activity_id=str(body.get("activity_id") or ""),
        )
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "achievement": _model_payload(achievement)}


@router.post("/projects/analyses/{analysis_id}/candidates/{candidate_id}/dismiss")
def dismiss_project_candidate(analysis_id: str, candidate_id: str) -> dict[str, Any]:
    try:
        analysis = _service().dismiss_project_candidate(analysis_id, candidate_id)
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "analysis": _model_payload(analysis)}


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    return {"status": "ok", "settings": _model_payload(_service().settings())}


@router.put("/settings")
def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "user_name",
        "organization",
        "external_ai_consent",
        "allowed_providers",
        "default_provider",
    }
    try:
        settings = _service().save_settings(
            {key: value for key, value in payload.items() if key in allowed}
        )
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "settings": _model_payload(settings)}


@router.post("/migrate")
def migrate(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    force = bool((payload or {}).get("force"))
    try:
        summary = run_migration(_service(), force=force)
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "migration": summary}


@router.get("/reports/{report_id}/content")
def report_content(report_id: str) -> dict[str, Any]:
    try:
        report: Report = _service().report(report_id)
    except Exception as exc:
        raise _fail(exc) from exc
    return {"status": "ok", "content": report.content}
