"""실서비스에서 발견된 장애의 회귀 테스트.

각 테스트 이름의 incNN은 docs/agent-incidents.md 의 INC-NN 항목과 1:1로 대응한다.
조치 코드를 되돌리면 해당 테스트가 실패하는지 확인한 결과도 기록부에 남긴다.
"""

import importlib
import pkgutil
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import devfolio
from devfolio.core.ai_service import AIService, _strip_foreign_chars
from devfolio.exceptions import DevfolioAIError
from devfolio.models.config import AIProviderConfig
from tests.test_ai_service import make_config


def _response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def _error(class_name: str, message: str) -> Exception:
    return type(class_name, (Exception,), {})(message)


@contextmanager
def _offline_litellm(fake_litellm: MagicMock):
    """실제 API·사용자 데이터 폴더·대기 없이 AIService 호출 경로를 실행한다."""
    with (
        patch("devfolio.core.ai_service.get_api_key", return_value="sk-test"),
        patch("devfolio.core.ai_service._write_ai_log"),
        patch("devfolio.core.ai_service.time.sleep") as sleep,
        patch.dict("sys.modules", {"litellm": fake_litellm}),
        patch.dict("os.environ", {}, clear=False),
    ):
        yield sleep


def test_inc01_quota_zero_fails_without_retry():
    service = AIService(make_config("gemini"))
    provider = service._get_provider("gemini")
    fake_litellm = MagicMock()
    fake_litellm.completion.side_effect = _error(
        "RateLimitError",
        "Quota exceeded for metric: generativelanguage.googleapis.com/"
        "generate_content_free_tier_requests, limit: 0",
    )

    with (
        _offline_litellm(fake_litellm) as sleep,
        patch.object(
            service, "_runtime_model_candidates", return_value=["gemini-2.5-flash"]
        ),
    ):
        with pytest.raises(DevfolioAIError) as exc:
            service._call_single_provider(
                fake_litellm,
                provider,
                [{"role": "user", "content": "x"}],
                None,
                None,
                False,
            )

    assert fake_litellm.completion.call_count == 1
    assert "결제" in exc.value.hint
    sleep.assert_not_called()


def test_inc02_not_found_model_moves_to_next_candidate_without_wait():
    service = AIService(make_config("gemini"))
    provider = service._get_provider("gemini")
    fake_litellm = MagicMock()
    fake_litellm.completion.side_effect = [
        _error("NotFoundError", "model not found"),
        _response("정상 응답"),
    ]

    with (
        _offline_litellm(fake_litellm) as sleep,
        patch.object(
            service,
            "_runtime_model_candidates",
            return_value=["retired-model", "current-model"],
        ),
    ):
        result = service._call_single_provider(
            fake_litellm,
            provider,
            [{"role": "user", "content": "x"}],
            None,
            None,
            False,
        )

    assert result == "정상 응답"
    assert "current-model" in fake_litellm.completion.call_args_list[1].kwargs["model"]
    sleep.assert_not_called()


def test_inc03_extracts_json_wrapped_in_fence_or_prose():
    fenced = '네, 아래와 같습니다.\n```json\n{"a": 1}\n```\n참고하세요.'
    prose = '요청하신 결과입니다: {"a": 1} 이상입니다.'

    assert AIService._extract_json(fenced) == {"a": 1}
    assert AIService._extract_json(prose) == {"a": 1}


def test_inc04_strips_japanese_and_chinese_but_keeps_korean():
    out = _strip_foreign_chars("Redis 캐시를 導入して 응답 시간을 단축했습니다")

    assert not any(
        0x3040 <= ord(c) <= 0x30FF or 0x4E00 <= ord(c) <= 0x9FFF for c in out
    )
    assert "Redis" in out
    assert "응답 시간을 단축했습니다" in out


def test_inc05_empty_response_falls_back_to_next_provider():
    config = make_config("anthropic")
    config.ai_providers.append(
        AIProviderConfig(name="openai", model="gpt-4o", key_stored=True)
    )
    service = AIService(config)
    fake_litellm = MagicMock()
    fake_litellm.completion.side_effect = [
        _response("   "),
        _response("다음 provider 응답"),
    ]

    with (
        _offline_litellm(fake_litellm),
        patch.object(
            service, "_runtime_model_candidates", side_effect=lambda p: [p.model]
        ),
    ):
        result = service._call_messages([{"role": "user", "content": "x"}])

    assert result == "다음 provider 응답"
    assert "gpt-4o" in fake_litellm.completion.call_args_list[1].kwargs["model"]


def test_inc06_every_devfolio_module_imports():
    names = [m.name for m in pkgutil.walk_packages(devfolio.__path__, "devfolio.")]
    assert "devfolio.web.main" in names

    failures = {}
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as e:  # noqa: BLE001 — 모든 import 실패를 모아서 보여준다
            failures[name] = f"{type(e).__name__}: {e}"

    assert failures == {}
