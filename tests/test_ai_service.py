"""AI 서비스 단위 테스트 (litellm 모킹)."""

from unittest.mock import MagicMock, patch

import pytest

from devfolio.core.ai_service import AIService
from devfolio.exceptions import (
    DevfolioAIAuthError,
    DevfolioAIError,
    DevfolioAINotConfiguredError,
    DevfolioAIRateLimitError,
)
from devfolio.models.config import AIProviderConfig, Config
from devfolio.models.draft import ProjectDraft, TaskDraft
from devfolio.models.project import Period, Project, Task


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def make_config(provider_name: str = "anthropic") -> Config:
    config = Config()
    config.default_ai_provider = provider_name
    config.ai_providers = [
        AIProviderConfig(
            name=provider_name,
            model="claude-sonnet-4-20250514" if provider_name == "anthropic" else "gpt-4o",
            key_stored=True,
        )
    ]
    config.user.name = "테스트 유저"
    return config


def make_task() -> Task:
    return Task(
        id="task_001",
        name="블루그린 배포 구축",
        period=Period(start="2024-02", end="2024-03"),
        problem="배포 시 5분 다운타임 발생",
        solution="Jenkins + AWS ECS 블루그린 배포 도입",
        result="다운타임 0, 배포 시간 40% 단축",
        tech_used=["Jenkins", "Docker", "AWS ECS"],
    )


def make_project() -> Project:
    return Project(
        id="test_project",
        name="테스트 프로젝트",
        type="company",
        status="done",
        organization="테스트 회사",
        period=Period(start="2024-01", end="2024-06"),
        role="백엔드 개발자",
        team_size=5,
        tech_stack=["Spring Boot", "Java"],
        summary="테스트 프로젝트 요약",
        tags=["backend"],
        tasks=[make_task()],
    )


# ---------------------------------------------------------------------------
# Provider 설정 테스트
# ---------------------------------------------------------------------------

class TestProviderConfig:
    def test_get_provider_found(self):
        service = AIService(make_config("anthropic"))
        provider = service._get_provider("anthropic")
        assert provider.name == "anthropic"

    def test_get_provider_not_found(self):
        service = AIService(make_config("anthropic"))
        with pytest.raises(DevfolioAIError):
            service._get_provider("openai")

    def test_no_default_provider_raises(self):
        service = AIService(Config())
        with pytest.raises(DevfolioAINotConfiguredError):
            service._get_provider(None)

    def test_model_string_anthropic(self):
        service = AIService(make_config("anthropic"))
        provider = service.config.get_provider("anthropic")
        assert service._model_string(provider) == "anthropic/claude-sonnet-4-20250514"

    def test_model_string_openai(self):
        service = AIService(make_config("openai"))
        provider = service.config.get_provider("openai")
        assert service._model_string(provider) == "gpt-4o"

    def test_model_string_ollama(self):
        config = Config()
        config.default_ai_provider = "ollama"
        config.ai_providers = [
            AIProviderConfig(
                name="ollama", model="llama3.2", base_url="http://localhost:11434"
            )
        ]
        service = AIService(config)
        provider = service.config.get_provider("ollama")
        assert service._model_string(provider) == "ollama/llama3.2"


# ---------------------------------------------------------------------------
# API 키 처리
# ---------------------------------------------------------------------------

class TestAPIKey:
    def test_missing_api_key_raises_auth_error(self):
        service = AIService(make_config())
        provider = service._get_provider("anthropic")
        with patch("devfolio.core.ai_service.get_api_key", return_value=None):
            with pytest.raises(DevfolioAIAuthError):
                service._set_env_key(provider)

    def test_ollama_skips_key_check(self):
        config = Config()
        config.default_ai_provider = "ollama"
        config.ai_providers = [
            AIProviderConfig(name="ollama", model="llama3.2", base_url="http://localhost:11434")
        ]
        service = AIService(config)
        provider = service._get_provider("ollama")
        # Ollama는 API 키 없이도 통과해야 함
        with patch("devfolio.core.ai_service.get_api_key", return_value=None):
            service._set_env_key(provider)  # 예외 없이 통과


# ---------------------------------------------------------------------------
# 작업 내역 문구 생성
# ---------------------------------------------------------------------------

class TestGenerateTaskText:
    def test_calls_ai_for_new_task(self):
        service = AIService(make_config())
        service._call = MagicMock(return_value="- 블루그린 배포로 다운타임 0 달성")
        task = make_task()

        result = service.generate_task_text(task, lang="ko")
        assert "블루그린" in result
        service._call.assert_called_once()

    def test_returns_cache_when_present(self):
        service = AIService(make_config())
        service._call = MagicMock()
        task = make_task()
        task = task.model_copy(update={"ai_generated_text": "캐시된 문구"})

        result = service.generate_task_text(task, force_refresh=False)
        assert result == "캐시된 문구"
        service._call.assert_not_called()

    def test_force_refresh_ignores_cache(self):
        service = AIService(make_config())
        service._call = MagicMock(return_value="새로 생성된 문구")
        task = make_task()
        task = task.model_copy(update={"ai_generated_text": "캐시된 문구"})

        result = service.generate_task_text(task, force_refresh=True)
        assert result == "새로 생성된 문구"
        service._call.assert_called_once()

    def test_prompt_contains_task_fields(self):
        service = AIService(make_config())
        captured: dict = {}

        def capture(system, user, provider=None):
            captured["user"] = user
            return "결과"

        service._call = capture
        task = make_task()
        service.generate_task_text(task, lang="ko")

        assert task.problem in captured["user"]
        assert task.solution in captured["user"]
        assert task.result in captured["user"]


# ---------------------------------------------------------------------------
# 프로젝트 요약 생성
# ---------------------------------------------------------------------------

class TestGenerateProjectSummary:
    def test_returns_ai_result(self):
        service = AIService(make_config())
        service._call = MagicMock(return_value="프로젝트 요약 문단")
        result = service.generate_project_summary(make_project(), lang="ko")
        assert result == "프로젝트 요약 문단"

    def test_includes_tasks_in_prompt(self):
        service = AIService(make_config())
        captured: dict = {}

        def capture(system, user, provider=None):
            captured["user"] = user
            return "ok"

        service._call = capture
        service.generate_project_summary(make_project(), lang="ko")
        assert "블루그린 배포 구축" in captured["user"]


class TestGenerateProjectDraft:
    def test_parses_json_into_project_draft(self):
        service = AIService(make_config())
        service._call = MagicMock(
            return_value="""
{
  "name": "AI 초안 프로젝트",
  "type": "company",
  "status": "done",
  "organization": "테스트 회사",
  "period": {"start": "2024-01", "end": "2024-06"},
  "role": "백엔드 개발자",
  "team_size": 3,
  "tech_stack": ["Python", "FastAPI"],
  "summary": "초안 요약",
  "tags": ["api"],
  "tasks": [
    {
      "name": "API 구축",
      "period": {"start": "2024-02", "end": "2024-05"},
      "problem": "분산된 API",
      "solution": "단일 게이트웨이 구축",
      "result": "응답 속도 개선",
      "tech_used": ["FastAPI"],
      "keywords": ["gateway"],
      "ai_generated_text": ""
    }
  ]
}
"""
        )

        draft = service.generate_project_draft("원본 텍스트", lang="ko")

        assert draft.name == "AI 초안 프로젝트"
        assert draft.raw_text == "원본 텍스트"
        assert draft.tasks[0].name == "API 구축"

    def test_invalid_json_raises_user_friendly_error(self):
        service = AIService(make_config())
        service._call = MagicMock(return_value="not-json")

        with pytest.raises(DevfolioAIError, match="JSON"):
            service.generate_project_draft("원본 텍스트")


class TestDraftAugmentation:
    def test_generate_draft_summary_uses_existing_project_summary_flow(self):
        service = AIService(make_config())
        draft = ProjectDraft(
            name="초안 프로젝트",
            tech_stack=["Python"],
            tasks=[TaskDraft(name="작업", result="성과")],
        )
        service._call = MagicMock(return_value="생성된 요약")

        result = service.generate_draft_project_summary(draft, lang="ko")

        assert result == "생성된 요약"
        service._call.assert_called_once()

    def test_generate_draft_task_texts_updates_each_task(self):
        service = AIService(make_config())
        draft = ProjectDraft(
            name="초안 프로젝트",
            tasks=[
                TaskDraft(name="작업 1", problem="문제", solution="해결", result="성과", tech_used=["Python"]),
                TaskDraft(name="작업 2", problem="문제", solution="해결", result="성과", tech_used=["Docker"]),
            ],
        )
        service.generate_task_text = MagicMock(side_effect=["bullet 1", "bullet 2"])

        updated = service.generate_draft_task_texts(draft, lang="ko")

        assert updated.tasks[0].ai_generated_text == "bullet 1"
        assert updated.tasks[1].ai_generated_text == "bullet 2"
        assert service.generate_task_text.call_count == 2


# ---------------------------------------------------------------------------
# 전체 경력기술서 생성
# ---------------------------------------------------------------------------

class TestGenerateFullResume:
    def test_returns_markdown(self):
        service = AIService(make_config())
        service._call = MagicMock(return_value="# 경력기술서\n\n내용")
        result = service.generate_full_resume([make_project()], user_name="홍길동")
        assert "경력기술서" in result

    def test_user_name_in_prompt(self):
        service = AIService(make_config())
        captured: dict = {}

        def capture(system, user, provider=None):
            captured["user"] = user
            return "ok"

        service._call = capture
        service.generate_full_resume([make_project()], user_name="홍길동")
        assert "홍길동" in captured["user"]


# ---------------------------------------------------------------------------
# 재시도 로직
# ---------------------------------------------------------------------------

class TestRetryLogic:
    def test_rate_limit_retries_then_raises(self):
        service = AIService(make_config())
        fake_litellm = MagicMock()

        class FakeRateLimitError(Exception):
            pass

        FakeRateLimitError.__name__ = "RateLimitError"
        fake_litellm.completion.side_effect = FakeRateLimitError("limit")

        with patch("devfolio.core.ai_service.get_api_key", return_value="sk-test"), \
             patch("devfolio.core.ai_service.time.sleep"), \
             patch.dict("sys.modules", {"litellm": fake_litellm}):
            with pytest.raises(DevfolioAIRateLimitError):
                service._call("system", "user", "anthropic")

        assert fake_litellm.completion.call_count == 3

    def test_auth_error_no_retry(self):
        service = AIService(make_config())
        fake_litellm = MagicMock()

        class FakeAuthError(Exception):
            pass

        FakeAuthError.__name__ = "AuthenticationError"
        fake_litellm.completion.side_effect = FakeAuthError("auth")

        with patch("devfolio.core.ai_service.get_api_key", return_value="sk-test"), \
             patch.dict("sys.modules", {"litellm": fake_litellm}):
            with pytest.raises(DevfolioAIAuthError):
                service._call("system", "user", "anthropic")

        # 재시도 없이 즉시 실패
        assert fake_litellm.completion.call_count == 1


# ---------------------------------------------------------------------------
# 연결 테스트
# ---------------------------------------------------------------------------

class TestConnectionTest:
    def test_success(self):
        service = AIService(make_config())
        service._call = MagicMock(return_value="CONNECTION_OK")
        ok, msg = service.test_connection()
        assert ok is True
        assert "CONNECTION_OK" in msg

    def test_failure(self):
        service = AIService(make_config())
        service._call = MagicMock(side_effect=Exception("연결 실패"))
        ok, msg = service.test_connection()
        assert ok is False
        assert "연결 실패" in msg


# ---------------------------------------------------------------------------
# JD 매칭
# ---------------------------------------------------------------------------

class TestMatchJD:
    def test_basic_match(self):
        service = AIService(make_config())
        service._call = MagicMock(return_value="매칭 점수: 85%\n강점: ...")
        result = service.match_job_description(
            jd_text="Java, Spring Boot, AWS 경험자 우대",
            projects=[make_project()],
        )
        assert "매칭" in result

    def test_jd_and_portfolio_in_prompt(self):
        service = AIService(make_config())
        captured: dict = {}

        def capture(system, user, provider=None):
            captured["user"] = user
            return "ok"

        service._call = capture
        service.match_job_description(
            jd_text="Python, FastAPI, Docker 필수",
            projects=[make_project()],
        )
        assert "Python, FastAPI, Docker" in captured["user"]
