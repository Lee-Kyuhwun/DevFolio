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

    def test_model_string_normalizes_legacy_gemini_alias(self):
        config = Config()
        config.default_ai_provider = "gemini"
        config.ai_providers = [
            AIProviderConfig(name="gemini", model="gemini-2.0-flash")
        ]
        service = AIService(config)
        provider = service.config.get_provider("gemini")
        assert service._model_string(provider) == "gemini/gemini-2.0-flash-001"

    def test_runtime_model_candidates_include_legacy_alias_and_snapshot_fallback(self):
        config = Config()
        config.default_ai_provider = "gemini"
        config.ai_providers = [
            AIProviderConfig(name="gemini", model="gemini-2.0-flash")
        ]
        service = AIService(config)
        provider = service.config.get_provider("gemini")

        assert service._runtime_model_candidates(provider) == [
            "gemini-2.0-flash",
            "gemini-2.0-flash-001",
        ]


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
        service._call_messages = MagicMock(side_effect=[
            "- 블루그린 배포 전략을 적용해 다운타임을 제거했습니다.\n- Jenkins와 ECS 배포 파이프라인을 연결해 배포 시간을 단축했습니다.\n- 운영 배포 절차를 표준화해 장애 대응 부담을 줄였습니다.\n- 배포 자동화 흐름을 정리해 운영 안정성을 높였습니다.",
            '{"pass": true, "scores": {"factuality": 5}, "issues": [], "missing_points": [], "revision_instructions": []}',
        ])
        task = make_task()

        result = service.generate_task_text(task, lang="ko")
        assert "블루그린" in result
        assert service._call_messages.call_count == 2

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
        service._call_messages = MagicMock(side_effect=[
            "- 새 bullet 1입니다.\n- 새 bullet 2입니다.\n- 새 bullet 3입니다.\n- 새 bullet 4입니다.",
            '{"pass": true, "scores": {"factuality": 5}, "issues": [], "missing_points": [], "revision_instructions": []}',
        ])
        task = make_task()
        task = task.model_copy(update={"ai_generated_text": "캐시된 문구"})

        result = service.generate_task_text(task, force_refresh=True)
        assert "새 bullet 1" in result
        assert service._call_messages.call_count == 2

    def test_prompt_contains_task_fields(self):
        service = AIService(make_config())
        captured: dict = {}

        def capture(messages, provider_name=None, temperature=None, max_tokens=None):
            if "writer_user" not in captured:
                captured["writer_system"] = messages[0]["content"]
                captured["writer_user"] = messages[1]["content"]
                return "- 결과 1\n- 결과 2\n- 결과 3\n- 결과 4"
            captured["review_user"] = messages[1]["content"]
            return '{"pass": true, "scores": {"factuality": 5}, "issues": [], "missing_points": [], "revision_instructions": []}'

        service._call_messages = capture
        task = make_task()
        service.generate_task_text(task, lang="ko")

        assert "<project_evidence>" in captured["writer_user"]
        assert '"problem": [' in captured["writer_user"]
        assert task.problem in captured["writer_user"]
        assert "output_mode: resume_bullets" in captured["writer_user"]
        assert "<review_result>" not in captured["writer_user"]
        assert "output_contract" in captured["review_user"]

    def test_revises_task_text_when_review_requests_changes(self):
        service = AIService(make_config())
        service._call_messages = MagicMock(side_effect=[
            "- 첫 초안입니다.\n- 둘째 초안입니다.\n- 셋째 초안입니다.\n- 넷째 초안입니다.",
            '{"pass": false, "scores": {"specificity": 2}, "issues": ["추상적 표현"], "missing_points": ["기술적 근거"], "revision_instructions": ["기술 선택과 결과를 더 구체화하세요."]}',
            "- 배포 자동화를 구축해 다운타임을 제거했습니다.\n- Jenkins와 ECS 배포 전략을 연결해 배포 시간을 줄였습니다.\n- 운영 배포 절차를 표준화해 유지보수성을 높였습니다.\n- 장애 대응 흐름을 단순화해 운영 부담을 낮췄습니다.",
        ])

        result = service.generate_task_text(make_task(), lang="ko")

        assert "장애 대응 흐름" in result
        assert service._call_messages.call_count == 3


# ---------------------------------------------------------------------------
# 프로젝트 요약 생성
# ---------------------------------------------------------------------------

class TestGenerateProjectSummary:
    def test_returns_ai_result(self):
        service = AIService(make_config())
        service._call_messages = MagicMock(side_effect=[
            "첫째 문장입니다. 둘째 문장입니다. 셋째 문장입니다. 넷째 문장입니다.",
            '{"pass": true, "scores": {"factuality": 5}, "issues": [], "missing_points": [], "revision_instructions": []}',
        ])
        result = service.generate_project_summary(make_project(), lang="ko")
        assert "넷째 문장입니다." in result

    def test_includes_tasks_in_prompt(self):
        service = AIService(make_config())
        captured: dict = {}

        def capture(messages, provider_name=None, temperature=None, max_tokens=None):
            if "writer_user" not in captured:
                captured["writer_user"] = messages[1]["content"]
                return "첫째 문장입니다. 둘째 문장입니다. 셋째 문장입니다. 넷째 문장입니다."
            return '{"pass": true, "scores": {"factuality": 5}, "issues": [], "missing_points": [], "revision_instructions": []}'

        service._call_messages = capture
        service.generate_project_summary(make_project(), lang="ko")
        assert "블루그린 배포 구축" in captured["writer_user"]
        assert '"team_size": 5' in captured["writer_user"]
        assert "output_mode: project_summary" in captured["writer_user"]

    def test_revises_summary_when_review_requests_changes(self):
        service = AIService(make_config())
        service._call_messages = MagicMock(side_effect=[
            "짧은 첫 문장입니다. 둘째 문장입니다. 셋째 문장입니다.",
            '{"pass": false, "scores": {"output_contract": 2}, "issues": ["문장이 짧음"], "missing_points": ["운영상 효과"], "revision_instructions": ["4~6문장으로 늘리고 결과를 보강하세요."]}',
            "첫째 문장입니다. 둘째 문장입니다. 셋째 문장입니다. 넷째 문장입니다.",
        ])

        result = service.generate_project_summary(make_project(), lang="ko")

        assert "넷째 문장" in result
        assert service._call_messages.call_count == 3


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

    def test_prompt_mentions_operational_signals_and_structure(self):
        service = AIService(make_config())
        captured: dict = {}

        def capture(system, user, provider=None):
            captured["user"] = user
            return """
{
  "name": "AI 초안 프로젝트",
  "type": "company",
  "status": "done",
  "organization": "",
  "period": {"start": null, "end": null},
  "role": "",
  "team_size": 1,
  "tech_stack": [],
  "summary": "",
  "tags": [],
  "tasks": []
}
"""

        service._call = capture
        service.generate_project_draft("배포 자동화와 성능 개선을 진행했습니다.", lang="ko")

        assert "배포, 운영, 성능, 안정성, 자동화" in captured["user"]
        assert "role, organization, team_size" in captured["user"]
        assert "<project_brief>" in captured["user"]
        assert "<output_schema>" in captured["user"]


class TestEvidenceAndPromptPack:
    def test_build_evidence_aggregates_project_fields(self):
        service = AIService(make_config())

        evidence = service.build_evidence(project=make_project())

        assert evidence.name == "테스트 프로젝트"
        assert evidence.role == "백엔드 개발자"
        assert evidence.tasks[0].name == "블루그린 배포 구축"
        assert "다운타임 0" in " ".join(evidence.metrics)

    def test_prompt_pack_loads_file_templates(self):
        prompt_pack = AIService._prompt_pack("ko")

        assert "<mission>" in prompt_pack.system_prompt
        assert "<project_evidence>" in prompt_pack.user_prompt
        assert '"pass": true' in prompt_pack.review_prompt


class TestDraftAugmentation:
    def test_generate_draft_summary_uses_existing_project_summary_flow(self):
        service = AIService(make_config())
        draft = ProjectDraft(
            name="초안 프로젝트",
            tech_stack=["Python"],
            tasks=[TaskDraft(name="작업", result="성과")],
        )
        service._call_messages = MagicMock(side_effect=[
            "첫째 문장입니다. 둘째 문장입니다. 셋째 문장입니다. 넷째 문장입니다.",
            '{"pass": true, "scores": {"factuality": 5}, "issues": [], "missing_points": [], "revision_instructions": []}',
        ])

        result = service.generate_draft_project_summary(draft, lang="ko")

        assert "넷째 문장입니다." in result
        assert service._call_messages.call_count == 2

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

    def test_gemini_not_found_falls_back_to_versioned_snapshot(self):
        config = Config()
        config.default_ai_provider = "gemini"
        config.ai_providers = [
            AIProviderConfig(name="gemini", model="gemini-2.0-flash", key_stored=True)
        ]
        service = AIService(config)
        fake_litellm = MagicMock()

        class FakeNotFoundError(Exception):
            pass

        FakeNotFoundError.__name__ = "NotFoundError"

        def completion_side_effect(**kwargs):
            if kwargs["model"] == "gemini/gemini-2.0-flash":
                raise FakeNotFoundError("missing")
            response = MagicMock()
            response.choices = [MagicMock(message=MagicMock(content="ok"))]
            return response

        fake_litellm.completion.side_effect = completion_side_effect

        with patch("devfolio.core.ai_service.get_api_key", return_value="AIza-test"), \
             patch.dict("sys.modules", {"litellm": fake_litellm}):
            result = service._call("system", "user", "gemini")

        assert result == "ok"
        assert [call.kwargs["model"] for call in fake_litellm.completion.call_args_list] == [
            "gemini/gemini-2.0-flash",
            "gemini/gemini-2.0-flash-001",
        ]


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
