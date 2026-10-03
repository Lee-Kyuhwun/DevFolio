"""실서비스에서 발견된 장애의 회귀 테스트.

각 테스트 이름의 incNN은 docs/agent-incidents.md 의 INC-NN 항목과 1:1로 대응한다.
조치 코드를 되돌리면 해당 테스트가 실패하는지 확인한 결과도 기록부에 남긴다.
"""

import importlib
import pkgutil
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import devfolio
from devfolio.core import storage
from devfolio.core.ai_service import AIService, _strip_foreign_chars
from devfolio.exceptions import DevfolioAIError
from devfolio.models.config import AIProviderConfig
from tests.test_ai_service import make_config

# 모듈 import 시점의 실제 경로 (테스트 중에는 conftest가 임시 경로로 바꾼다)
_USER_AI_LOG_FILE = storage.AI_LOG_FILE


def _response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )


def _error(class_name: str, message: str) -> Exception:
    return type(class_name, (Exception,), {})(message)


# pyproject 선택 의존성(ai, pdf, docx, gui)의 최상위 모듈.
# `pip install -e ".[dev]"`만 설치한 환경에서는 없을 수 있으므로 import 실패가 아니라 건너뜀으로 본다.
_OPTIONAL_DEPENDENCIES = frozenset(
    {"litellm", "weasyprint", "markdown", "docx", "fastapi", "uvicorn"}
)


def _import_all_devfolio_modules() -> tuple[dict[str, str], dict[str, str]]:
    """devfolio 하위 모듈을 모두 import한다. (실패, 선택 의존성 때문에 건너뜀)을 반환한다."""
    failures: dict[str, str] = {}
    skipped: dict[str, str] = {}
    for module in pkgutil.walk_packages(devfolio.__path__, "devfolio."):
        try:
            importlib.import_module(module.name)
        except ModuleNotFoundError as e:
            if (e.name or "").split(".")[0] in _OPTIONAL_DEPENDENCIES:
                skipped[module.name] = e.name
            else:
                failures[module.name] = f"ModuleNotFoundError: {e}"
        except Exception as e:  # noqa: BLE001 — 문법 오류 등 모든 import 실패를 모아서 보여준다
            failures[module.name] = f"{type(e).__name__}: {e}"
    return failures, skipped


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


def test_ai_logs_during_tests_stay_out_of_user_data_dir():
    assert storage.AI_LOG_FILE != _USER_AI_LOG_FILE

    test_inc02_not_found_model_moves_to_next_candidate_without_wait()

    assert storage.AI_LOG_FILE.exists()


def test_inc06_missing_optional_dependency_is_skipped_not_failed():
    web_modules = [name for name in sys.modules if name.startswith("devfolio.web")]
    with patch.dict("sys.modules", {"fastapi": None}):
        for name in web_modules:
            sys.modules.pop(name)
        failures, skipped = _import_all_devfolio_modules()

    assert failures == {}
    assert "devfolio.web.routes.api" in skipped


def test_inc06_every_devfolio_module_imports():
    names = [m.name for m in pkgutil.walk_packages(devfolio.__path__, "devfolio.")]
    assert "devfolio.web.main" in names

    failures, _ = _import_all_devfolio_modules()

    assert failures == {}
