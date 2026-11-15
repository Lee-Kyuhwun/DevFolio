"""AI Reliability 계층 테스트 (Phase 9).

실제 API 를 호출하지 않는다. Fake litellm 으로 실패 경로를 강제 재현해
정책(재시도·차단·전환·예산)과 품질 하한선만 검증한다.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from devfolio.core.ai_quality import build_evidence_index, validate_analysis
from devfolio.core.ai_reliability import (
    Budget,
    ErrorKind,
    ModelHealthStore,
    ReliabilitySettings,
    backoff_delay,
    classify_error,
    filter_candidates,
    is_permanent,
    is_retryable,
)
from devfolio.core.ai_service import AIService
from devfolio.exceptions import (
    DevfolioAIAuthError,
    DevfolioAIError,
    DevfolioAIRateLimitError,
)
from devfolio.models.config import AIProviderConfig
from tests.test_ai_service import make_config


def _resp(text: str = "정상 응답", finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text), finish_reason=finish_reason
            )
        ]
    )


def _err(class_name: str, message: str) -> Exception:
    return type(class_name, (Exception,), {})(message)


@contextmanager
def _offline(fake_litellm: MagicMock):
    with (
        patch("devfolio.core.ai_service.get_api_key", return_value="sk-test"),
        patch("devfolio.core.ai_service._write_ai_log"),
        patch("devfolio.core.ai_service.time.sleep") as sleep,
        patch.dict("sys.modules", {"litellm": fake_litellm}),
    ):
        yield sleep


def _two_provider_service() -> AIService:
    config = make_config("anthropic")
    config.ai_providers.append(
        AIProviderConfig(name="openai", model="gpt-4o", key_stored=True)
    )
    return AIService(config)


def _call(service: AIService, fake_litellm: MagicMock, provider_name=None):
    provider = service._get_provider(provider_name)
    return service._call_single_provider(
        fake_litellm, provider, [{"role": "user", "content": "x"}], None, None, False
    )


# ---------------------------------------------------------------------------
# 오류 분류 (정책의 기반)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "class_name,message,expected",
    [
        ("BadRequestError", 'code":"model_decommissioned"', ErrorKind.MODEL_GONE),
        ("NotFoundError", "The model x does not exist", ErrorKind.MODEL_GONE),
        ("AuthenticationError", "invalid api key", ErrorKind.AUTH),
        ("RateLimitError", "429 too many requests", ErrorKind.RATE_LIMIT),
        ("Timeout", "request timed out", ErrorKind.TIMEOUT),
        ("InternalServerError", "500 internal", ErrorKind.SERVER),
        (
            "BadRequestError",
            "invalid_request_error unsupported parameter",
            ErrorKind.BAD_REQUEST,
        ),
        ("ContextWindowExceededError", "maximum context length", ErrorKind.CONTEXT),
        ("ValueError", "응답이 출력 토큰 한도에서 잘렸습니다", ErrorKind.TRUNCATED),
    ],
)
def test_error_classification(class_name, message, expected):
    assert classify_error(_err(class_name, message)) is expected


def test_retry_policy_matches_litellm_semantics():
    """4xx·not-found·검증 실패는 재시도하지 않고, 429·타임아웃·5xx 만 재시도한다."""
    assert is_retryable(ErrorKind.RATE_LIMIT)
    assert is_retryable(ErrorKind.TIMEOUT)
    assert is_retryable(ErrorKind.SERVER)
    for kind in (
        ErrorKind.MODEL_GONE,
        ErrorKind.AUTH,
        ErrorKind.BAD_REQUEST,
        ErrorKind.CONTEXT,
        ErrorKind.TRUNCATED,
        ErrorKind.JSON_INVALID,
        ErrorKind.UNKNOWN,
    ):
        assert not is_retryable(kind)


def test_permanent_kinds_are_blocked_after_cooldown():
    assert is_permanent(ErrorKind.MODEL_GONE)
    assert is_permanent(ErrorKind.AUTH)
    assert not is_permanent(ErrorKind.RATE_LIMIT)


def test_backoff_respects_retry_after_and_cap():
    assert backoff_delay(1, retry_after=3.0) == 3.0
    assert 0 < backoff_delay(5, cap=8.0) <= 8.0
    assert backoff_delay(1, retry_after=99.0, cap=8.0) == 8.0


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_permanent_block_survives_new_instance(tmp_path):
    path = tmp_path / "health.json"
    store = ModelHealthStore(path=path)
    store.block("groq::gemma2-9b-it", ErrorKind.MODEL_GONE, "decommissioned")

    reopened = ModelHealthStore(path=path)
    assert reopened.blocked("groq::gemma2-9b-it") is True
    assert "groq::gemma2-9b-it" in reopened.snapshot()


def test_transient_block_expires_after_cooldown(tmp_path):
    store = ModelHealthStore(cooldown_seconds=0.01, path=tmp_path / "h.json")
    store.block("groq::m", ErrorKind.RATE_LIMIT, "429")
    assert store.blocked("groq::m") is True

    import time as _time

    _time.sleep(0.02)
    # Cooldown 이 지나면 다시 시도할 수 있다 (HALF_OPEN).
    assert store.blocked("groq::m") is False


def test_filter_candidates_skips_blocked_and_keeps_order(tmp_path):
    store = ModelHealthStore(path=tmp_path / "h.json")
    store.block("groq::dead", ErrorKind.MODEL_GONE, "gone")
    assert filter_candidates("groq", ["dead", "alive"], store=store) == ["alive"]
    assert filter_candidates("groq", ["a", "b", "c"], store=store, limit=2) == [
        "a",
        "b",
    ]


# ---------------------------------------------------------------------------
# 재시도 / 전환 (Phase 3)
# ---------------------------------------------------------------------------


def test_healthy_response_passes_without_extra_calls():
    service = AIService(make_config("anthropic"))
    fake = MagicMock()
    fake.completion.return_value = _resp("좋은 결과")

    with (
        _offline(fake),
        patch.object(service, "_runtime_model_candidates", return_value=["m1"]),
    ):
        result = _call(service, fake)

    assert result == "좋은 결과"
    assert fake.completion.call_count == 1


def test_decommissioned_model_is_not_retried_and_moves_on():
    service = AIService(make_config("groq"))
    fake = MagicMock()
    fake.completion.side_effect = [
        _err("BadRequestError", 'code":"model_decommissioned"'),
        _resp("두 번째 모델"),
    ]

    with (
        _offline(fake) as sleep,
        patch.object(
            service, "_runtime_model_candidates", return_value=["dead", "alive"]
        ),
    ):
        result = _call(service, fake, "groq")

    assert result == "두 번째 모델"
    assert fake.completion.call_count == 2
    sleep.assert_not_called()


def test_missing_model_switches_to_next_candidate():
    service = AIService(make_config("groq"))
    fake = MagicMock()
    fake.completion.side_effect = [
        _err("NotFoundError", "The model x does not exist"),
        _resp("ok"),
    ]

    with (
        _offline(fake),
        patch.object(service, "_runtime_model_candidates", return_value=["x", "y"]),
    ):
        assert _call(service, fake, "groq") == "ok"


def test_all_models_failing_moves_to_next_provider():
    service = _two_provider_service()
    fake = MagicMock()
    fake.completion.side_effect = [
        _err("BadRequestError", 'code":"model_decommissioned"'),
        _resp("openai 응답"),
    ]

    with (
        _offline(fake),
        patch.object(
            service, "_runtime_model_candidates", side_effect=lambda p: [p.model]
        ),
    ):
        result = service._call_messages([{"role": "user", "content": "x"}])

    assert result == "openai 응답"
    assert "gpt-4o" in fake.completion.call_args_list[1].kwargs["model"]


def test_rate_limit_retries_once_then_recovers():
    service = AIService(make_config("anthropic"))
    fake = MagicMock()
    fake.completion.side_effect = [_err("RateLimitError", "429 rpm"), _resp("회복")]

    with (
        _offline(fake) as sleep,
        patch.object(service, "_runtime_model_candidates", return_value=["m1"]),
    ):
        assert _call(service, fake) == "회복"

    assert fake.completion.call_count == 2
    sleep.assert_called_once()


def test_timeout_retries_then_succeeds():
    service = AIService(make_config("anthropic"))
    fake = MagicMock()
    fake.completion.side_effect = [_err("Timeout", "request timed out"), _resp("ok")]

    with (
        _offline(fake),
        patch.object(service, "_runtime_model_candidates", return_value=["m1"]),
    ):
        assert _call(service, fake) == "ok"


def test_auth_error_switches_provider_without_retry():
    service = _two_provider_service()
    fake = MagicMock()
    fake.completion.side_effect = [
        _err("AuthenticationError", "invalid api key"),
        _resp("다른 provider"),
    ]

    with (
        _offline(fake) as sleep,
        patch.object(
            service, "_runtime_model_candidates", side_effect=lambda p: [p.model]
        ),
    ):
        result = service._call_messages([{"role": "user", "content": "x"}])

    assert result == "다른 provider"
    assert fake.completion.call_count == 2
    sleep.assert_not_called()


def test_invalid_json_response_switches_model():
    """JSON 검증 실패는 재시도가 아니라 다음 모델 후보로 넘어간다."""
    service = AIService(make_config("groq"))
    fake = MagicMock()
    fake.completion.side_effect = [
        _resp("이건 JSON 이 아닙니다"),
        _resp('{"project_type": "CLI 도구"}'),
    ]

    with (
        _offline(fake),
        patch.object(service, "_runtime_model_candidates", return_value=["m1", "m2"]),
    ):
        raw = service._call_messages(
            [{"role": "user", "content": "x"}],
            provider_name="groq",
            validator=AIService._extract_json,
        )

    assert json.loads(raw)["project_type"] == "CLI 도구"
    assert fake.completion.call_count == 2


def test_truncated_response_switches_model():
    service = AIService(make_config("groq"))
    fake = MagicMock()
    fake.completion.side_effect = [
        _resp('{"tasks": [{"name": "깡', finish_reason="length"),
        _resp('{"ok": true}'),
    ]

    with (
        _offline(fake),
        patch.object(service, "_runtime_model_candidates", return_value=["m1", "m2"]),
    ):
        assert _call(service, fake, "groq") == '{"ok": true}'


def test_budget_exhaustion_stops_before_next_attempt():
    service = AIService(make_config("anthropic"))
    provider = service._get_provider("anthropic")
    fake = MagicMock()
    fake.completion.return_value = _resp("ok")

    with (
        _offline(fake),
        patch.object(service, "_runtime_model_candidates", return_value=["m1"]),
        pytest.raises(DevfolioAIError) as exc,
    ):
        service._call_single_provider(
            fake,
            provider,
            [{"role": "user", "content": "x"}],
            None,
            None,
            False,
            budget=Budget(seconds=0.0),
        )

    assert "시간 예산" in str(exc.value)
    fake.completion.assert_not_called()


def test_provider_fallback_can_be_disabled(monkeypatch):
    service = _two_provider_service()
    monkeypatch.setenv("DEVFOLIO_AI_PROVIDER_FALLBACK", "0")
    fake = MagicMock()
    fake.completion.side_effect = _err("AuthenticationError", "invalid api key")

    with (
        _offline(fake),
        patch.object(
            service, "_runtime_model_candidates", side_effect=lambda p: [p.model]
        ),
        pytest.raises((DevfolioAIAuthError, DevfolioAIError)),
    ):
        service._call_messages([{"role": "user", "content": "x"}])

    assert fake.completion.call_count == 1


def test_auto_model_switch_can_be_limited_to_single_model(monkeypatch):
    service = AIService(make_config("groq"))
    monkeypatch.setenv("DEVFOLIO_AI_MAX_MODELS", "1")
    monkeypatch.setenv("DEVFOLIO_AI_MODEL_RETRIES", "0")
    fake = MagicMock()
    fake.completion.side_effect = _err(
        "BadRequestError", 'code":"model_decommissioned"'
    )

    with (
        _offline(fake),
        pytest.raises(DevfolioAIError),
    ):
        _call(service, fake, "groq")

    assert fake.completion.call_count == 1


def test_litellm_internal_retries_are_disabled():
    """재시도 제어 지점은 애플리케이션 하나뿐이어야 한다 (중첩 재시도 방지)."""
    service = AIService(make_config("anthropic"))
    fake = MagicMock()
    fake.completion.return_value = _resp("ok")

    with (
        _offline(fake),
        patch.object(service, "_runtime_model_candidates", return_value=["m1"]),
    ):
        _call(service, fake)

    assert fake.completion.call_args.kwargs["max_retries"] == 0
    assert fake.completion.call_args.kwargs["timeout"] > 0


def test_rate_limit_exhausted_moves_to_next_provider(monkeypatch):
    service = AIService(make_config("anthropic"))
    monkeypatch.setenv("DEVFOLIO_AI_MODEL_RETRIES", "0")
    fake = MagicMock()
    fake.completion.side_effect = _err("RateLimitError", "429 rpm")

    with (
        _offline(fake),
        patch.object(service, "_runtime_model_candidates", return_value=["m1"]),
        pytest.raises(DevfolioAIRateLimitError),
    ):
        _call(service, fake)


# ---------------------------------------------------------------------------
# 품질 하한선 (Phase 4)
# ---------------------------------------------------------------------------

_EVIDENCE = build_evidence_index(
    {
        "readme": "DevFolio uses typer and jinja2 to render documents.",
        "dependencies": {"pyproject.toml": ["typer", "jinja2", "pydantic"]},
    },
    {"commits": 109, "languages": {"Python": 80}},
)

_GOOD_PAYLOAD = {
    "project_type": "CLI 도구",
    "purpose": "구조화된 경험 데이터로 문서를 만든다",
    "key_features": ["YAML 저장", "다중 포맷 렌더링"],
    "problem": "포맷마다 문서를 다시 작성해야 한다",
    "solution": "데이터를 한 번 저장하고 템플릿으로 렌더링한다",
    "tech_stack": ["typer", "jinja2"],
    "summary": "로컬 우선 포트폴리오 스튜디오",
    "tasks": [
        {
            "name": "템플릿 렌더링",
            "problem": "포맷별 중복 작성",
            "solution": "jinja2 템플릿으로 분리",
            "result": "문서 생성이 단순해졌다",
            "tech_used": ["jinja2"],
        }
    ],
}


def test_quality_passes_for_grounded_payload():
    report = validate_analysis(_GOOD_PAYLOAD, _EVIDENCE)
    assert report.passed is True
    assert report.verdict == "passed"
    assert report.techs_supported == 2


def test_quality_rejects_missing_required_field():
    payload = dict(_GOOD_PAYLOAD)
    payload["solution"] = ""
    report = validate_analysis(payload, _EVIDENCE)

    assert report.passed is False
    assert report.verdict == "rejected_schema"
    assert any(issue.code == "missing_field" for issue in report.issues)


def test_quality_rejects_fabricated_metric():
    payload = json.loads(json.dumps(_GOOD_PAYLOAD))
    payload["tasks"][0]["result"] = "응답 시간을 42% 단축했다"
    report = validate_analysis(payload, _EVIDENCE)

    assert report.passed is False
    assert report.verdict == "rejected_evidence"
    assert any(issue.code == "unverified_metric" for issue in report.issues)


def test_quality_flags_unsupported_tech_but_tolerates_minority():
    payload = json.loads(json.dumps(_GOOD_PAYLOAD))
    payload["tech_stack"] = ["typer", "jinja2", "rust-actix"]
    report = validate_analysis(payload, _EVIDENCE)

    assert report.passed is True  # 소수는 경고만
    assert any(issue.code == "unsupported_tech" for issue in report.issues)


def test_quality_rejects_majority_unsupported_tech():
    payload = json.loads(json.dumps(_GOOD_PAYLOAD))
    payload["tech_stack"] = ["rust-actix", "kotlin-ktor", "typer"]
    report = validate_analysis(payload, _EVIDENCE)

    assert report.passed is False
    assert any(issue.code == "unsupported_tech_majority" for issue in report.issues)


def test_quality_flags_duplicate_task_names():
    payload = json.loads(json.dumps(_GOOD_PAYLOAD))
    payload["tasks"].append(dict(payload["tasks"][0]))
    report = validate_analysis(payload, _EVIDENCE)

    assert any(issue.code == "duplicate_task" for issue in report.issues)


# ---------------------------------------------------------------------------
# 단계별 복구 / Graceful Degradation (Phase 5·6)
# ---------------------------------------------------------------------------

_SCAN_METRICS = {"commits": 109, "languages": {"Python": 80}}
_CONTEXT = {
    "readme": "DevFolio uses typer and jinja2.",
    "dependencies": {"pyproject.toml": ["typer", "jinja2"]},
    "languages": {"Python": 80},
}


def test_pipeline_marks_completed_only_when_quality_passes():
    service = AIService(make_config("groq"))
    with patch.object(
        service, "analyze_project_from_code", return_value=dict(_GOOD_PAYLOAD)
    ):
        outcome = service.analyze_project_with_report(
            "DevFolio", _CONTEXT, _SCAN_METRICS
        )

    stages = {stage.name: stage.status for stage in outcome.stages}
    assert outcome.completed is True
    assert stages["scan"] == "completed"
    assert stages["quality"] == "completed"


def test_pipeline_returns_partial_result_when_ai_fails():
    service = AIService(make_config("groq"))
    with patch.object(
        service, "analyze_project_from_code", side_effect=DevfolioAIError("전부 실패")
    ):
        outcome = service.analyze_project_with_report(
            "DevFolio", _CONTEXT, _SCAN_METRICS
        )

    stages = {stage.name: stage.status for stage in outcome.stages}
    assert outcome.completed is False
    assert outcome.payload == {}  # AI 가 하지 않은 판단을 꾸며내지 않는다
    assert stages["scan"] == "completed"  # 결정론적 결과는 유지
    assert stages["analysis"] == "failed"
    assert stages["quality"] == "skipped"
    assert outcome.quality.hard_failures


def test_pipeline_keeps_analysis_when_cases_extraction_fails():
    service = AIService(make_config("groq"))
    payload = dict(_GOOD_PAYLOAD)
    payload["problem_solving_cases"] = []

    with patch.object(service, "analyze_project_from_code", return_value=payload):
        outcome = service.analyze_project_with_report(
            "DevFolio", _CONTEXT, _SCAN_METRICS
        )

    stages = {stage.name: stage.status for stage in outcome.stages}
    assert outcome.completed is True
    assert stages["cases"] == "skipped"  # 사례 없음은 분석 실패가 아니다


def test_pipeline_rejects_payload_that_fails_quality():
    service = AIService(make_config("groq"))
    payload = json.loads(json.dumps(_GOOD_PAYLOAD))
    payload["tech_stack"] = ["rust-actix", "kotlin-ktor"]

    with patch.object(service, "analyze_project_from_code", return_value=payload):
        outcome = service.analyze_project_with_report(
            "DevFolio", _CONTEXT, _SCAN_METRICS
        )

    assert outcome.completed is False
    assert outcome.quality.verdict == "rejected_evidence"


def test_settings_can_be_overridden_by_environment(monkeypatch):
    monkeypatch.setenv("DEVFOLIO_AI_TIME_BUDGET", "30")
    monkeypatch.setenv("DEVFOLIO_AI_MODEL_RETRIES", "0")
    monkeypatch.setenv("DEVFOLIO_AI_COOLDOWN", "10")
    monkeypatch.setenv("DEVFOLIO_AI_ALLOW_THIRD_PARTY", "0")

    settings = ReliabilitySettings.from_env()
    assert settings.time_budget_seconds == 30
    assert settings.model_retries == 0
    assert settings.cooldown_seconds == 10
    assert settings.allow_third_party_fallback is False


def test_third_party_provider_can_be_blocked(monkeypatch):
    """키 없는 외부 무료 서비스로 데이터가 나가는 것을 막을 수 있어야 한다."""
    service = AIService(make_config("anthropic"))
    monkeypatch.setenv("DEVFOLIO_AI_ALLOW_THIRD_PARTY", "0")
    fake = MagicMock()
    fake.completion.side_effect = _err("AuthenticationError", "invalid api key")

    with (
        _offline(fake),
        patch.object(
            service, "_runtime_model_candidates", side_effect=lambda p: [p.model]
        ),
        pytest.raises((DevfolioAIAuthError, DevfolioAIError)),
    ):
        service._call_messages([{"role": "user", "content": "x"}])

    models = [call.kwargs["model"] for call in fake.completion.call_args_list]
    assert all("openai-fast" not in model for model in models)
