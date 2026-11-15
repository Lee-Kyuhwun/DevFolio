"""Provider 단위 레이트 리밋 대응 회귀 테스트.

실제 API 를 호출하지 않는다. 로그에서 확인된 실패를 그대로 재현한다.

- Groq 429: 계정(조직) 단위 TPM/RPM 이므로 모델을 바꿔도 같은 한도를 두드리게 된다.
- pollinations 무료 한도: ``Free limit reached: 1 reply every 45 seconds per IP`` 가
  litellm 에서 ``APIError`` 로 올라와 ``kind=unknown`` 으로 분류됐다.
- 사례 추출 실패가 빈 배열로 삼켜져 ``verdict=passed`` 와 동시에 나타났다.
- ``languages`` 는 파일 개수인데 프롬프트에서 ``%`` 로 표시됐다 (Python(329%)).
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from devfolio.models.config import AIProviderConfig

from devfolio.core.ai_reliability import (
    ErrorKind,
    ModelHealthStore,
    ReliabilitySettings,
    classify_error,
    estimate_tokens,
    get_token_window,
    parse_retry_after,
    reset_token_windows,
)
from devfolio.core.ai_service import AIService, _builtin_provider
from devfolio.exceptions import DevfolioAIError
from tests.test_ai_reliability import (
    _CONTEXT,
    _GOOD_PAYLOAD,
    _offline,
    _resp,
    make_config,
)


def _err(class_name: str, message: str) -> Exception:
    return type(class_name, (Exception,), {})(message)


# ---------------------------------------------------------------------------
# 오류 B: pollinations 무료 한도 분류
# ---------------------------------------------------------------------------


def test_inc23_pollinations_free_limit_is_rate_limit():
    exc = _err(
        "APIError",
        "Free limit reached: 1 reply every 45 seconds per IP. Retry after 18s",
    )

    assert classify_error(exc) is ErrorKind.RATE_LIMIT


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Free limit reached: 1 reply every 45 seconds per IP. Retry after 18s", 18.0),
        ("Retry after 4.5s", 4.5),
        ("429 Too Many Requests", None),
    ],
)
def test_retry_after_is_read_from_message_body(message, expected):
    """pollinations 는 Retry-After 헤더 대신 본문 문구로 알린다."""
    assert parse_retry_after(_err("APIError", message)) == expected


# ---------------------------------------------------------------------------
# Provider 단위 Cooldown (오류 A·B 공통)
# ---------------------------------------------------------------------------


def test_provider_cooldown_uses_retry_after_and_expires(tmp_path):
    store = ModelHealthStore(cooldown_seconds=300, path=tmp_path / "health.json")
    store.block_provider("pollinations", 0.05, "Free limit reached")

    assert store.provider_cooldown_remaining("pollinations") > 0
    # 모델 키는 따로 관리된다 — Provider 차단이 모델 차단을 오염시키지 않는다.
    assert store.blocked(store.key("pollinations", "openai-fast")) is False

    time.sleep(0.06)
    assert store.provider_cooldown_remaining("pollinations") == 0


def test_provider_cooldown_falls_back_to_default_when_no_retry_after(tmp_path):
    store = ModelHealthStore(cooldown_seconds=42, path=tmp_path / "health.json")
    store.block_provider("groq", None, "rate limit reached")

    assert 41 < store.provider_cooldown_remaining("groq") <= 42


def test_inc23_provider_cooldown_is_shared_across_stages(tmp_path):
    """한 단계에서 429 를 받은 Provider 를 다음 단계가 다시 두드리지 않는다."""
    service = AIService(make_config("groq"))
    store = ModelHealthStore(path=tmp_path / "health.json")
    store.block_provider("groq", 60, "Rate limit reached for model openai/gpt-oss-120b")
    fake = MagicMock()
    fake.completion.return_value = _resp()

    with (
        _offline(fake),
        patch("devfolio.core.ai_service.get_health_store", return_value=store),
    ):
        service._call_messages([{"role": "user", "content": "x"}])

    models = [call.kwargs["model"] for call in fake.completion.call_args_list]
    assert models, "Cooldown 중인 Provider 를 건너뛰고 다른 후보로 시도해야 한다"
    assert all("gpt-oss" not in model for model in models)


def test_rate_limit_blocks_the_provider_for_the_next_stage(tmp_path):
    """429 를 받으면 그 Provider 가 Cooldown 에 기록되어 다음 호출에서 빠진다."""
    service = AIService(make_config("groq"))
    store = ModelHealthStore(path=tmp_path / "health.json")
    fake = MagicMock()
    fake.completion.side_effect = _err(
        "RateLimitError", "Rate limit reached for model openai/gpt-oss-120b (TPM)"
    )

    with (
        _offline(fake),
        patch("devfolio.core.ai_service.get_health_store", return_value=store),
        patch.object(
            service, "_runtime_model_candidates", side_effect=lambda p: [p.model]
        ),
        patch.object(
            service,
            "_provider_fallback_chain",
            return_value=[service._get_provider("groq")],
        ),
        pytest.raises((DevfolioAIError, Exception)),
    ):
        service._call_messages([{"role": "user", "content": "x"}])

    assert store.provider_cooldown_remaining("groq") > 0


# ---------------------------------------------------------------------------
# Provider 토큰 예산 (기본 비활성)
# ---------------------------------------------------------------------------


def test_estimate_tokens_reserves_output_budget():
    messages = [{"role": "user", "content": "x" * 300}]

    assert estimate_tokens(messages, 100) == 200
    assert estimate_tokens(messages, None) == 100


def test_token_window_is_disabled_by_default():
    reset_token_windows()
    window = get_token_window("unset", ReliabilitySettings())

    assert window.enabled is False
    window.reserve(10**9)
    assert window.wait_seconds(10**9) == 0.0


def test_token_window_waits_when_budget_is_consumed():
    reset_token_windows()
    window = get_token_window("configured", ReliabilitySettings(provider_tpm=100))

    assert window.enabled is True
    assert window.wait_seconds(100) == 0.0

    window.reserve(100)

    assert window.wait_seconds(50) > 0
    assert window.used() == 100


# ---------------------------------------------------------------------------
# 오류 D: 사례 추출 실패는 "완료"가 아니다
# ---------------------------------------------------------------------------


def test_cases_extraction_failure_is_recorded_in_telemetry():
    service = AIService(make_config("groq"))
    telemetry: dict = {"errors": []}

    with patch.object(service, "_call", side_effect=DevfolioAIError("JSON 깨짐")):
        cases = service._extract_problem_solving_cases(
            commit_history="- abc123 fix: 파서 교체",
            readme="",
            repo_name="DevFolio",
            telemetry=telemetry,
        )

    assert cases == []
    assert telemetry["cases_error"].startswith("DevfolioAIError")


def test_cases_extraction_without_json_array_is_also_an_error():
    service = AIService(make_config("groq"))
    telemetry: dict = {"errors": []}

    with patch.object(service, "_call", return_value="사례를 찾지 못했습니다"):
        cases = service._extract_problem_solving_cases(
            commit_history="- abc123 fix: 파서 교체",
            readme="",
            repo_name="DevFolio",
            telemetry=telemetry,
        )

    assert cases == []
    assert telemetry["cases_error"].startswith("CasesParseError")


def test_inc23_cases_failure_marks_result_partial():
    service = AIService(make_config("groq"))
    payload = json.loads(json.dumps(_GOOD_PAYLOAD))
    payload["problem_solving_cases"] = []

    def fake_analyze(**kwargs):
        kwargs["telemetry"]["cases_error"] = "CasesParseError: 배열 없음"
        return payload

    with patch.object(service, "analyze_project_from_code", side_effect=fake_analyze):
        outcome = service.analyze_project_with_report(
            "DevFolio", _CONTEXT, {"commits": 109, "languages": {"Python": 80}}
        )

    stages = {stage.name: stage.status for stage in outcome.stages}
    assert outcome.status == "partial"
    assert outcome.completed is False
    assert stages["cases"] == "failed"
    # 초안 자체는 유지한다 — 사용자가 이어서 편집할 수 있어야 한다.
    assert outcome.payload == payload
    assert outcome.quality.passed is True


def test_pipeline_status_is_completed_only_when_all_stages_pass():
    service = AIService(make_config("groq"))

    with patch.object(
        service, "analyze_project_from_code", return_value=dict(_GOOD_PAYLOAD)
    ):
        outcome = service.analyze_project_with_report(
            "DevFolio", _CONTEXT, {"commits": 109, "languages": {"Python": 80}}
        )

    assert outcome.status == "completed"
    assert outcome.completed is True


# ---------------------------------------------------------------------------
# 언어 비율 표시 (Python(329%) 이상치)
# ---------------------------------------------------------------------------


def test_inc23_gpt_oss_uses_json_mode_and_low_reasoning():
    """gpt-oss 는 추론 모델 — 기본(medium) 추론이 출력 예산을 먹어 JSON 이 잘렸다."""
    config = make_config("groq")
    config.ai_providers = [
        AIProviderConfig(name="groq", model="openai/gpt-oss-120b", key_stored=True)
    ]
    service = AIService(config)
    provider = service._get_provider("groq")
    fake = MagicMock()
    fake.completion.return_value = _resp(json.dumps(_GOOD_PAYLOAD))

    with (
        _offline(fake),
        patch.object(
            service, "_runtime_model_candidates", side_effect=lambda p: [p.model]
        ),
    ):
        service._call_single_provider(
            fake,
            provider,
            [{"role": "user", "content": "JSON 으로 답하세요"}],
            None,
            100,
            True,
        )

    kwargs = fake.completion.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["reasoning_effort"] == "low"


def test_json_mode_is_not_sent_to_unsupported_provider():
    """지원이 확인되지 않은 Provider 에 response_format 을 보내면 400 으로 후보를 날린다."""
    service = AIService(make_config("groq"))
    provider = _builtin_provider()
    fake = MagicMock()
    fake.completion.return_value = _resp(json.dumps(_GOOD_PAYLOAD))

    with (
        _offline(fake),
        patch.object(
            service, "_runtime_model_candidates", side_effect=lambda p: [p.model]
        ),
    ):
        service._call_single_provider(
            fake,
            provider,
            [{"role": "user", "content": "JSON 으로 답하세요"}],
            None,
            100,
            True,
        )

    kwargs = fake.completion.call_args.kwargs
    assert "response_format" not in kwargs
    assert "reasoning_effort" not in kwargs


def test_inc23_language_share_is_not_file_count():
    service = AIService(make_config("groq"))
    captured: dict = {}

    def fake_call(system, prompt, *args, **kwargs):
        captured["prompt"] = prompt
        return json.dumps(_GOOD_PAYLOAD)

    with (
        patch.object(service, "_call", side_effect=fake_call),
        patch.object(service, "_extract_problem_solving_cases", return_value=[]),
    ):
        service.analyze_project_from_code(
            "DevFolio",
            _CONTEXT,
            {"commits": 10, "languages": {"Python": 75, "Markdown": 25}},
        )

    assert "Python(75%, 75개 파일)" in captured["prompt"]
    assert "Markdown(25%, 25개 파일)" in captured["prompt"]
    # 개수를 %로 찍던 예전 표기 (329% 같은 값) 가 남아 있지 않다.
    assert "75%)" not in captured["prompt"]
