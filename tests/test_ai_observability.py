"""AI 분석 관측 시스템 테스트.

서버 로그에만 남던 정보(요청/실제 모델, 전환 이유, 실패 원인, 단계 진행)가
클라이언트가 읽는 상태 객체로 정확히 옮겨오는지 검증한다.

실제 AI API 는 호출하지 않는다. Fake litellm 과 가짜 스캔 결과만 사용한다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from devfolio.core.ai_quality import QualityIssue, QualityReport
from devfolio.core.ai_reliability import ErrorKind, classify_error
from devfolio.core.ai_observability import (
    AnalysisRun,
    AnalysisRunRegistry,
    ErrorCode,
    error_code_for,
    model_display,
    provider_display,
    redact,
)
from devfolio.core.ai_service import AnalysisOutcome, AIService, StageResult
from devfolio.models.config import AIProviderConfig
from devfolio.web.routes import api as api_module
from tests.test_ai_reliability import _offline, _resp, make_config
from tests.test_web_api import client, web_store  # noqa: F401 — pytest fixture 재사용


def _run(**kwargs) -> AnalysisRun:
    return AnalysisRun(analysis_id=kwargs.pop("analysis_id", "run-1"), **kwargs)


def _ok(run: AnalysisRun, *, provider="groq", model="openai/gpt-oss-120b") -> None:
    run.apply_event({"type": "stage_start", "stage": "analysis"})
    run.apply_event(
        {"type": "attempt", "attempt": 1, "provider": provider, "model": model}
    )
    run.apply_event(
        {
            "type": "attempt_ok",
            "attempt": 1,
            "provider": provider,
            "model": model,
            "duration_ms": 1200,
        }
    )


# ---------------------------------------------------------------------------
# 1~3. 모델 식별 — 요청/선택/실제/유효 모델 구분
# ---------------------------------------------------------------------------


def test_requested_and_effective_models_are_distinct():
    run = _run(requested_provider="groq", requested_model="llama-3.3-70b-versatile")

    _ok(run)

    data = run.to_dict()
    assert data["requested_model"] == "llama-3.3-70b-versatile"
    assert data["requested_model_display"] == "Llama 3.3 70B Versatile"
    assert data["selected_model"] == "openai/gpt-oss-120b"
    assert data["effective_model_display"] == "GPT-OSS 120B"
    assert data["requested_provider_display"] == "Groq"
    # 요청 모델을 실제 사용 모델처럼 보여주지 않는다.
    assert data["effective_model"] != data["requested_model"]


def test_provider_and_model_are_not_confused():
    """`groq/openai/gpt-oss-120b` 는 Provider=Groq, Model=GPT-OSS 120B 로 표시된다."""
    assert provider_display("groq") == "Groq"
    assert model_display("openai/gpt-oss-120b") == "GPT-OSS 120B"
    assert model_display("qwen/qwen3.8-27b") == "Qwen3.8 27B"
    assert model_display("") == ""


def test_multiple_model_attempts_keep_order_and_fallback_history():
    run = _run(requested_provider="groq", requested_model="llama-3.3-70b-versatile")
    run.apply_event({"type": "stage_start", "stage": "analysis"})
    run.apply_event(
        {
            "type": "attempt",
            "attempt": 1,
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
        }
    )
    run.apply_event(
        {
            "type": "attempt_error",
            "attempt": 1,
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
            "error_code": ErrorCode.OUTPUT_TRUNCATED,
            "technical": "finish_reason=length",
        }
    )
    run.apply_event(
        {
            "type": "fallback",
            "from_provider": "groq",
            "from_model": "openai/gpt-oss-120b",
            "to_provider": "pollinations",
            "to_model": "openai-fast",
            "reason_code": ErrorCode.OUTPUT_TRUNCATED,
            "reason_text": "AI 응답이 출력 길이 제한에 도달했습니다.",
        }
    )
    run.apply_event(
        {
            "type": "attempt",
            "attempt": 1,
            "provider": "pollinations",
            "model": "openai-fast",
        }
    )
    run.apply_event(
        {
            "type": "attempt_ok",
            "attempt": 1,
            "provider": "pollinations",
            "model": "openai-fast",
            "duration_ms": 900,
        }
    )

    data = run.to_dict()
    stages = {stage["stage_id"]: stage for stage in data["stages"]}
    assert [call["provider"] for call in data["calls"]] == ["groq", "pollinations"]
    assert data["calls"][0]["status"] == "error"
    assert data["calls"][0]["error_code"] == ErrorCode.OUTPUT_TRUNCATED
    assert data["calls"][1]["status"] == "ok"
    assert data["fallback_occurred"] is True
    assert data["effective_provider"] == "pollinations"
    # 단계마다 실제 사용한 모델을 따로 보여줄 수 있어야 한다.
    assert stages["analysis"]["model_id"] == "openai-fast"


# ---------------------------------------------------------------------------
# 4~8. 오류 코드 표준화
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,message,expected",
    [
        (ErrorKind.MODEL_GONE, "model_decommissioned", "MODEL_DECOMMISSIONED"),
        (ErrorKind.MODEL_GONE, "does not exist", "MODEL_NOT_FOUND"),
        (ErrorKind.RATE_LIMIT, "429 too many requests", "RATE_LIMITED"),
        (ErrorKind.AUTH, "invalid api key", "AUTHENTICATION_FAILED"),
        (ErrorKind.AUTH, "403 permission denied", "PERMISSION_DENIED"),
        (ErrorKind.TIMEOUT, "timed out", "REQUEST_TIMEOUT"),
        (ErrorKind.SERVER, "500 internal", "PROVIDER_UNAVAILABLE"),
        (ErrorKind.CONTEXT, "maximum context length", "CONTEXT_LIMIT_EXCEEDED"),
        (ErrorKind.TRUNCATED, "finish_reason=length", "OUTPUT_TRUNCATED"),
        (ErrorKind.JSON_INVALID, "Expecting value: line 24", "INVALID_JSON"),
        (ErrorKind.UNKNOWN, "??", "UNKNOWN_ERROR"),
    ],
)
def test_error_kind_maps_to_client_code(kind, message, expected):
    exc = RuntimeError(message)
    assert error_code_for(kind, exc) == expected


def test_groq_rate_limit_error_exposes_retry_after():
    run = _run()
    run.apply_event({"type": "stage_start", "stage": "analysis"})
    run.apply_event(
        {
            "type": "attempt",
            "attempt": 1,
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
        }
    )
    run.apply_event(
        {
            "type": "attempt_error",
            "attempt": 1,
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
            "error_code": ErrorCode.RATE_LIMITED,
            "retry_after_seconds": 18,
            "technical": "Rate limit reached for model openai/gpt-oss-120b",
        }
    )

    error = run.to_dict()["errors"][0]
    assert error["error_code"] == "RATE_LIMITED"
    assert error["retry_after_seconds"] == 18.0
    assert error["retryable"] is True
    assert "요청 한도" in error["user_message"]
    assert "technical" not in error  # 상세는 공개 오류에 포함하지 않는다


def test_pollinations_free_limit_is_classified_as_rate_limit():
    exc = RuntimeError(
        "Free limit reached: 1 reply every 45 seconds per IP. Retry after 18s"
    )
    code = error_code_for(classify_error(exc), exc)
    assert code == ErrorCode.RATE_LIMITED


def test_output_truncation_and_json_failure_have_distinct_codes():
    assert error_code_for(ErrorKind.TRUNCATED, "length") == ErrorCode.OUTPUT_TRUNCATED
    assert (
        error_code_for(ErrorKind.JSON_INVALID, "Expecting value")
        == ErrorCode.INVALID_JSON
    )


# ---------------------------------------------------------------------------
# 9~11. 품질/부분 완료/전체 실패
# ---------------------------------------------------------------------------


def test_quality_gate_failure_is_not_completed():
    run = _run()
    _ok(run)
    run.finish("completed", quality_verdict="passed", payload={"a": 1})
    run.fail(
        ErrorCode.QUALITY_GATE_FAILED,
        stage_id="quality",
        message="품질 검증 실패(rejected_evidence): unverified_metric",
    )

    data = run.to_dict()
    assert data["status"] == "failed"
    assert data["quality_verdict"] == "passed"  # 원본 검증 결과는 보존
    assert data["errors"][-1]["error_code"] == "QUALITY_GATE_FAILED"
    assert data["errors"][-1]["retryable"] is False


def test_inc24_partial_status_is_reported_separately_from_completed():
    run = _run()
    run.apply_event({"type": "stage_start", "stage": "analysis"})
    run.apply_event({"type": "stage_end", "stage": "analysis", "status": "completed"})
    run.apply_event({"type": "stage_start", "stage": "cases"})
    run.apply_event(
        {
            "type": "stage_end",
            "stage": "cases",
            "status": "failed",
            "detail": "JSON 오류",
        }
    )
    run.finish("partial", quality_verdict="passed", payload={"a": 1})

    data = run.to_dict()
    stages = {stage["stage_id"]: stage for stage in data["stages"]}
    assert data["status"] == "partial"
    assert data["payload"] == {"a": 1}  # 초안은 유지
    assert stages["analysis"]["status"] == "completed"
    assert stages["cases"]["status"] == "failed"


def test_all_providers_failing_leaves_no_effective_model():
    run = _run(requested_provider="groq", requested_model="llama-3.3-70b-versatile")
    run.fail(ErrorCode.PROVIDER_UNAVAILABLE, stage_id="analysis")

    data = run.to_dict()
    assert data["status"] == "failed"
    assert data["effective_model"] == ""
    assert data["effective_model_display"] == ""
    assert data.get("payload", {}) == {}


# ---------------------------------------------------------------------------
# 12~15. 저장/복원/취소
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="POSIX 0600 is not enforced on Windows")
def test_registry_persists_and_restores_completed_run(tmp_path):
    path = tmp_path / "runs.json"
    registry = AnalysisRunRegistry(path=path)
    run = registry.create(repo_name="DevFolio", params={"repo_path": "/tmp/x"})
    _ok(run)
    run.finish("completed", quality_verdict="passed", payload={"summary": "s"})
    registry.save(run)

    restored = AnalysisRunRegistry(path=path).get(run.analysis_id)

    assert restored is not None
    assert restored.status == "completed"
    assert restored.effective_model == "openai/gpt-oss-120b"
    assert restored.payload == {"summary": "s"}
    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600


def test_interrupted_run_is_recovered_as_cancelled(tmp_path):
    """컨테이너 재시작으로 끝나지 못한 실행을 완료로 보이면 안 된다."""
    path = tmp_path / "runs.json"
    registry = AnalysisRunRegistry(path=path)
    run = registry.create(repo_name="DevFolio", params={"repo_path": "/tmp/x"})
    run.apply_event({"type": "stage_start", "stage": "analysis"})
    registry.save(run)

    restored = AnalysisRunRegistry(path=path).get(run.analysis_id)

    assert restored is not None
    assert restored.status == "cancelled"
    assert restored.errors[-1]["error_code"] == "ANALYSIS_CANCELLED"
    assert "중단" in restored.error_summary


def test_dev_details_are_never_persisted(tmp_path):
    path = tmp_path / "runs.json"
    registry = AnalysisRunRegistry(path=path)
    run = registry.create(repo_name="DevFolio", params={})
    run.apply_event({"type": "stage_start", "stage": "analysis"})
    run.apply_event(
        {
            "type": "attempt",
            "attempt": 1,
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
        }
    )
    run.apply_event(
        {
            "type": "attempt_error",
            "attempt": 1,
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
            "error_code": ErrorCode.AUTHENTICATION_FAILED,
            "technical": "invalid api key sk-secret-value",
        }
    )
    registry.save(run)

    raw = path.read_text(encoding="utf-8")
    assert "sk-secret-value" not in raw
    assert "technical_message" not in raw


def test_cancelled_run_ignores_late_result():
    run = _run()
    run.cancel()
    run.finish("completed", quality_verdict="passed", payload={"late": True})

    data = run.to_dict()
    assert data["status"] == "cancelled"
    assert data.get("payload", {}) == {}


def test_redact_removes_keys_and_paths():
    text = redact(
        "Bearer abcdef123456 failed at /Users/me/secret with key sk-1234567890abcdef"
    )

    assert "sk-1234567890abcdef" not in text
    assert "/Users/me/secret" not in text
    assert "[redacted]" in text


# ---------------------------------------------------------------------------
# 16. AIService 이벤트 통합 — 실제 호출 경로가 상태를 채우는가
# ---------------------------------------------------------------------------


def test_service_events_fill_run_state_on_fallback(monkeypatch):
    monkeypatch.setenv("DEVFOLIO_AI_MODEL_RETRIES", "0")
    config = make_config("groq")
    config.ai_providers = [
        AIProviderConfig(name="groq", model="openai/gpt-oss-120b", key_stored=True)
    ]
    service = AIService(config)
    run = AnalysisRun(analysis_id="svc")
    fake = MagicMock()
    fake.completion.side_effect = [
        type("RateLimitError", (Exception,), {})("Rate limit reached for model"),
        _resp(json.dumps({"ok": True})),
    ]

    with (
        _offline(fake),
        patch.object(
            service, "_runtime_model_candidates", side_effect=lambda p: [p.model]
        ),
        patch.object(
            service,
            "_provider_fallback_chain",
            return_value=[service._get_provider("groq"), _pollinations_provider()],
        ),
    ):
        service._call_messages(
            [{"role": "user", "content": "x"}],
            stage="analysis",
            event_hook=run.apply_event,
        )

    data = run.to_dict()
    assert len(data["calls"]) == 2
    assert data["calls"][0]["error_code"] == "RATE_LIMITED"
    assert data["calls"][1]["status"] == "ok"
    assert data["fallback_occurred"] is True
    assert data["effective_model"] == "openai-fast"
    assert data["effective_provider"] == "pollinations"


def _pollinations_provider() -> AIProviderConfig:
    return AIProviderConfig(
        name="pollinations",
        model="openai-fast",
        base_url="https://text.pollinations.ai/openai",
    )


# ---------------------------------------------------------------------------
# 17~18. API 계약 — 비동기 시작/중복 방지/재시도/개발자 상세 게이팅
# ---------------------------------------------------------------------------


def test_async_analysis_returns_id_without_running_ai(client, tmp_path):  # noqa: F811
    with patch.object(api_module._ANALYSIS_EXECUTOR, "submit"):
        response = client.post(
            "/api/scan/git/async",
            json={
                "repo_path": str(tmp_path),
                "author_email": "me@example.com",
                "analyze": True,
            },
        )

    assert response.status_code == 202
    body = response.json()
    assert body["analysis_id"]
    assert body["analysis"]["status"] == "pending"
    assert body["analysis"]["requested_provider"] == ""


def test_duplicate_request_reuses_running_analysis(client, tmp_path):  # noqa: F811
    payload = {
        "repo_path": str(tmp_path),
        "author_email": "me@example.com",
        "analyze": True,
    }
    with patch.object(api_module._ANALYSIS_EXECUTOR, "submit"):
        first = client.post("/api/scan/git/async", json=payload).json()
        second = client.post("/api/scan/git/async", json=payload).json()

    assert first["analysis_id"] == second["analysis_id"]
    assert second["reused"] is True


def test_retry_is_rejected_while_analysis_is_running(client, tmp_path):  # noqa: F811
    with patch.object(api_module._ANALYSIS_EXECUTOR, "submit"):
        started = client.post(
            "/api/scan/git/async",
            json={
                "repo_path": str(tmp_path),
                "author_email": "me@example.com",
                "analyze": True,
            },
        ).json()

    response = client.post(
        f"/api/analysis/{started['analysis_id']}/retry", json={"stage": "all"}
    )

    assert response.status_code == 409


def test_inc24_retry_starts_a_new_run_after_terminal_state(client, tmp_path):  # noqa: F811
    """실패/취소된 분석은 같은 실행을 덮어쓰지 않고 새 실행으로 재시도한다."""
    with patch.object(api_module._ANALYSIS_EXECUTOR, "submit"):
        started = client.post(
            "/api/scan/git/async",
            json={
                "repo_path": str(tmp_path),
                "author_email": "me@example.com",
                "analyze": True,
            },
        ).json()
    client.post(f"/api/analysis/{started['analysis_id']}/cancel")

    with patch.object(api_module._ANALYSIS_EXECUTOR, "submit"):
        response = client.post(
            f"/api/analysis/{started['analysis_id']}/retry", json={"stage": "all"}
        )

    assert response.status_code == 202
    body = response.json()
    assert body["analysis_id"] != started["analysis_id"]
    new_run = api_module.get_run_registry().get(body["analysis_id"])
    assert new_run is not None
    assert new_run.params["retried_from"] == started["analysis_id"]


def test_unknown_analysis_returns_404(client):  # noqa: F811
    assert client.get("/api/analysis/does-not-exist").status_code == 404


def test_dev_details_require_debug_mode(client, monkeypatch, tmp_path):  # noqa: F811
    with patch.object(api_module._ANALYSIS_EXECUTOR, "submit"):
        started = client.post(
            "/api/scan/git/async",
            json={
                "repo_path": str(tmp_path),
                "author_email": "me@example.com",
                "analyze": True,
            },
        ).json()

    monkeypatch.delenv("DEVFOLIO_DEBUG", raising=False)
    normal = client.get(
        f"/api/analysis/{started['analysis_id']}?include_dev=true"
    ).json()
    assert "dev" not in normal["analysis"]

    monkeypatch.setenv("DEVFOLIO_DEBUG", "1")
    debug = client.get(
        f"/api/analysis/{started['analysis_id']}?include_dev=true"
    ).json()
    assert "dev" in debug["analysis"]


def test_cancel_endpoint_marks_status_cancelled(client, tmp_path):  # noqa: F811
    with patch.object(api_module._ANALYSIS_EXECUTOR, "submit"):
        started = client.post(
            "/api/scan/git/async",
            json={
                "repo_path": str(tmp_path),
                "author_email": "me@example.com",
                "analyze": True,
            },
        ).json()

    response = client.post(f"/api/analysis/{started['analysis_id']}/cancel")

    assert response.status_code == 200
    assert response.json()["analysis"]["status"] == "cancelled"


def test_model_status_never_reports_untracked_model_as_available(client):  # noqa: F811
    body = client.get("/api/ai/models/status").json()

    assert body["status"] == "ok"
    statuses = {m["status"] for p in body["providers"] for m in p["models"]}
    assert "available" not in statuses
    assert statuses <= {"unknown", "cooldown", "unavailable"}


def test_inc24_client_snapshot_matches_server_status(client, tmp_path):  # noqa: F811
    payload = {
        "project_type": "CLI 도구",
        "purpose": "문서 생성",
        "key_features": ["a"],
        "problem": "p",
        "solution": "s",
        "tech_stack": ["typer"],
        "summary": "요약",
        "tasks": [
            {
                "name": "t",
                "problem": "p",
                "solution": "s",
                "result": "r",
                "tech_used": ["typer"],
            }
        ],
    }
    outcome = AnalysisOutcome(
        payload=payload,
        stages=[
            StageResult("scan", "completed"),
            StageResult("analysis", "completed"),
            StageResult("cases", "skipped"),
            StageResult("quality", "completed"),
        ],
        quality=QualityReport(),
        model_used="groq/openai/gpt-oss-120b",
        completed=True,
        status="completed",
    )
    scan_result = SimpleNamespace(
        commits=[1, 2],
        languages=Counter({"Python": 3}),
        project_context={"readme": "x", "dependencies": {}, "languages": {"Python": 3}},
    )

    def fake_report(**kwargs):
        hook = kwargs["event_hook"]
        for stage in ("analysis", "cases", "quality"):
            hook({"type": "stage_start", "stage": stage})
            hook({"type": "stage_end", "stage": stage, "status": "completed"})
        return outcome

    with (
        patch(
            "devfolio.web.routes.api._resolve_scan_repo_path",
            return_value=(tmp_path, None),
        ),
        patch("devfolio.core.git_scanner.scan_repo", return_value=scan_result),
        patch(
            "devfolio.core.git_scanner.build_project_payload",
            return_value={"name": "x"},
        ),
        patch(
            "devfolio.web.routes.api.AIService.analyze_project_with_report",
            side_effect=fake_report,
        ),
    ):
        response = client.post(
            "/api/scan/git",
            json={
                "repo_path": str(tmp_path),
                "author_email": "me@example.com",
                "analyze": True,
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["analyzed"] is True
    assert body["analysis_id"]
    # 화면과 서버 상태가 같은 값을 가리킨다.
    assert body["analysis"]["status"] == body["ai_report"]["status"] == "completed"
    assert body["analysis"]["progress_percent"] == 100
    assert body["ai_report"]["analysis_id"] == body["analysis_id"]


def test_sync_scan_marks_quality_failure_as_failed(client, tmp_path):  # noqa: F811
    quality = QualityReport(
        level2_ok=False,
        issues=[
            QualityIssue(
                level=2,
                code="unverified_metric",
                field="summary",
                message="8배 개선 수치의 근거를 찾지 못했습니다.",
                hard=True,
            )
        ],
    )
    outcome = AnalysisOutcome(
        payload={},
        stages=[StageResult("scan", "completed"), StageResult("quality", "failed")],
        quality=quality,
        completed=False,
        status="failed",
        error="품질 검증 실패(rejected_evidence)",
    )
    scan_result = SimpleNamespace(
        commits=[1], languages=Counter({"Python": 1}), project_context={"readme": "x"}
    )

    with (
        patch(
            "devfolio.web.routes.api._resolve_scan_repo_path",
            return_value=(tmp_path, None),
        ),
        patch("devfolio.core.git_scanner.scan_repo", return_value=scan_result),
        patch(
            "devfolio.core.git_scanner.build_project_payload",
            return_value={"name": "x"},
        ),
        patch(
            "devfolio.web.routes.api.AIService.analyze_project_with_report",
            return_value=outcome,
        ),
    ):
        body = client.post(
            "/api/scan/git",
            json={
                "repo_path": str(tmp_path),
                "author_email": "me@example.com",
                "analyze": True,
            },
        ).json()

    assert body["analyzed"] is False
    assert body["analysis"]["status"] == "failed"
    assert body["analysis"]["errors"][-1]["error_code"] == "QUALITY_GATE_FAILED"
    # 품질 실패의 "어느 필드가 왜" 문제인지가 실행 기록에 남아야 재시도가 의미 있다.
    quality = body["analysis"]["quality"]
    assert quality["issue_count"] == 1
    assert quality["issues"][0]["field"] == "summary"
    assert quality["issues"][0]["code"] == "unverified_metric"
    assert quality["issues"][0]["hard"] is True


def test_events_are_returned_after_cursor():
    run = _run()
    run.apply_event({"type": "stage_start", "stage": "analysis"})
    cursor = run.seq
    run.apply_event({"type": "stage_start", "stage": "cases"})

    events = run.events_since(cursor)

    assert [event["stage"] for event in events] == ["cases"]
    assert events[0]["seq"] > cursor


def test_run_elapsed_is_measured_not_estimated():
    run = _run()
    run.started_at = time.time() - 2
    run.finish("completed")

    assert 1900 <= run.to_dict()["elapsed_ms"] <= 2600


# ---------------------------------------------------------------------------
# INC-25. 품질 이슈 저장 · 분석 기준 커밋 · 폴링 재연결 계약
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _make_repo(tmp_path: Path) -> Path:
    """커밋 2개가 있는 실제 git 저장소 — 분석 기준 SHA 비교를 실제 git 으로 검증한다."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for name, message in (("a.txt", "first"), ("b.txt", "second")):
        (repo / name).write_text(message, encoding="utf-8")
        _git(repo, "add", name)
        _git(
            repo,
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-q",
            "-m",
            message,
        )
    return repo


def test_inc25_quality_issues_are_saved_per_field():
    report = QualityReport(
        level2_ok=False,
        issues=[
            QualityIssue(
                level=2,
                code="unverified_metric",
                field="summary",
                message="8배 개선 수치의 근거가 없습니다.",
                hard=True,
            ),
            QualityIssue(
                level=1,
                code="unsupported_tech",
                field="tech_stack",
                message="근거에서 확인되지 않은 기술입니다.",
            ),
        ],
    )
    run = _run()
    run.finish("failed", quality_verdict=report.verdict, quality=report)

    quality = run.to_dict()["quality"]
    assert quality["verdict"] == "rejected_evidence"
    assert quality["passed"] is False
    assert quality["issue_count"] == 2
    assert quality["truncated"] is False
    assert quality["issues"][0]["field"] == "summary"
    assert quality["issues"][0]["hard"] is True
    assert quality["issues"][1]["field"] == "tech_stack"
    assert quality["issues"][1]["level"] == 1


def test_inc25_quality_issue_list_is_capped_but_count_is_kept():
    report = QualityReport(
        issues=[
            QualityIssue(level=1, code="empty_field", field=f"f{index}", message="")
            for index in range(30)
        ]
    )
    run = _run()
    run.finish("failed", quality=report)

    quality = run.to_dict()["quality"]
    assert len(quality["issues"]) == 20
    assert quality["issue_count"] == 30
    assert quality["truncated"] is True


def test_inc25_quality_messages_are_redacted():
    report = QualityReport(
        issues=[
            QualityIssue(
                level=1,
                code="unverified_metric",
                field="summary",
                message="key sk-abcdef123456 at /Users/alice/secret.md",
            )
        ]
    )
    run = _run()
    run.finish("failed", quality=report)

    message = run.to_dict()["quality"]["issues"][0]["message"]
    assert "sk-abcdef123456" not in message
    assert "/Users/alice" not in message


def test_inc25_quality_and_repo_state_survive_restart(tmp_path):
    registry = AnalysisRunRegistry(path=tmp_path / "runs.json")
    run = registry.create(
        repo_name="DevFolio",
        params={"repo_path": str(tmp_path)},
        repo_state={
            "head_sha": "a" * 40,
            "branch": "main",
            "dirty": True,
            "dirty_files": 2,
        },
    )
    run.finish(
        "failed",
        quality=QualityReport(
            level2_ok=False,
            issues=[
                QualityIssue(
                    level=2,
                    code="unverified_metric",
                    field="summary",
                    message="근거 없음",
                    hard=True,
                )
            ],
        ),
    )
    registry.save(run)

    reloaded = AnalysisRunRegistry(path=tmp_path / "runs.json").get(run.analysis_id)
    assert reloaded is not None
    data = reloaded.to_dict()
    assert data["quality"]["issues"][0]["field"] == "summary"
    assert data["repo_state"]["head_sha"] == "a" * 40
    assert data["repo_state"]["branch"] == "main"
    assert data["repo_state"]["dirty"] is True
    assert data["repo_state"]["dirty_files"] == 2


def test_inc25_repo_state_is_recorded_once_at_start():
    run = _run()
    run.set_repo_state(head_sha="a" * 40, branch="main", dirty=True, dirty_files=3)
    # 분석 중 스캔이 다른 SHA 를 보고해도 시작 시점 기록을 덮어쓰지 않는다.
    run.set_repo_state(head_sha="b" * 40, branch="dev")

    state = run.to_dict()["repo_state"]
    assert state["head_sha"] == "a" * 40
    assert state["head_sha_short"] == "a" * 8
    assert state["branch"] == "main"
    assert state["dirty"] is True
    assert state["dirty_files"] == 3
    assert state["recorded"] is True


@pytest.mark.skipif(shutil.which("git") is None, reason="git 실행 파일이 없습니다.")
def test_inc25_repo_state_endpoint_counts_commits_behind(
    client,  # noqa: F811
    tmp_path,
    _isolate_analysis_runs,
):
    from devfolio.core.git_scanner import read_repo_state

    repo = _make_repo(tmp_path)
    run = _isolate_analysis_runs.create(
        repo_name="demo",
        params={"repo_path": str(repo)},
        repo_state=read_repo_state(repo).to_dict(),
    )
    _isolate_analysis_runs.save(run)
    (repo / "c.txt").write_text("third", encoding="utf-8")
    _git(repo, "add", "c.txt")
    _git(
        repo,
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-q",
        "-m",
        "third",
    )

    body = client.get(f"/api/analysis/{run.analysis_id}/repo-state").json()

    assert body["available"] is True
    assert body["stale"] is True
    assert body["behind_commits"] == 1
    assert body["current"]["head_sha"] != body["recorded"]["head_sha"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git 실행 파일이 없습니다.")
def test_inc25_repo_state_endpoint_is_fresh_right_after_scan(
    client,  # noqa: F811
    tmp_path,
    _isolate_analysis_runs,
):
    from devfolio.core.git_scanner import read_repo_state

    repo = _make_repo(tmp_path)
    run = _isolate_analysis_runs.create(
        repo_name="demo",
        params={"repo_path": str(repo)},
        repo_state=read_repo_state(repo).to_dict(),
    )
    _isolate_analysis_runs.save(run)

    body = client.get(f"/api/analysis/{run.analysis_id}/repo-state").json()

    assert body["available"] is True
    assert body["stale"] is False
    assert body["behind_commits"] == 0


def test_inc25_repo_state_endpoint_does_not_guess_without_git(
    client,  # noqa: F811
    tmp_path,
    _isolate_analysis_runs,
):
    run = _isolate_analysis_runs.create(
        repo_name="plain", params={"repo_path": str(tmp_path)}
    )
    _isolate_analysis_runs.save(run)

    body = client.get(f"/api/analysis/{run.analysis_id}/repo-state").json()

    assert body["stale"] is False
    assert body["behind_commits"] == 0
    assert body["recorded"]["head_sha"] == ""  # 모르는 값을 최신으로 단정하지 않는다


def test_inc25_repo_state_endpoint_reports_missing_repo(
    client,  # noqa: F811
    tmp_path,
    _isolate_analysis_runs,
):
    run = _isolate_analysis_runs.create(
        repo_name="gone", params={"repo_path": str(tmp_path / "missing")}
    )
    _isolate_analysis_runs.save(run)

    body = client.get(f"/api/analysis/{run.analysis_id}/repo-state").json()

    assert body["available"] is False
    assert body["stale"] is False
    assert body["behind_commits"] is None
    assert body["reason"]


def test_inc25_repo_state_endpoint_unknown_analysis_returns_404(client):  # noqa: F811
    response = client.get("/api/analysis/does-not-exist/repo-state")
    assert response.status_code == 404


def test_inc25_snapshot_adds_fields_without_breaking_contract(client, tmp_path):  # noqa: F811
    with patch.object(api_module._ANALYSIS_EXECUTOR, "submit"):
        body = client.post(
            "/api/scan/git/async",
            json={
                "repo_path": str(tmp_path),
                "author_email": "me@example.com",
                "analyze": True,
            },
        ).json()

    analysis = body["analysis"]
    for key in (
        "analysis_id",
        "status",
        "progress_percent",
        "stages",
        "calls",
        "errors",
        "requested_model",
        "effective_model",
        "seq",
    ):
        assert key in analysis
    assert analysis["quality"] == {}
    assert "repo_state" in analysis
