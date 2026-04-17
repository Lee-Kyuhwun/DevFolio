"""AI Provider 추상화 서비스 (litellm 기반, lazy import)."""

import os
import time
from typing import Optional

from devfolio.exceptions import (
    DevfolioAIAuthError,
    DevfolioAIError,
    DevfolioAINotConfiguredError,
    DevfolioAIRateLimitError,
)
from devfolio.log import get_logger
from devfolio.models.config import AIProviderConfig, Config
from devfolio.models.project import Project, Task
from devfolio.utils.security import get_api_key

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 시스템 프롬프트 (모듈 상수)
# ---------------------------------------------------------------------------

_TASK_SYSTEM = """당신은 IT 개발자의 경력기술서 작성을 돕는 전문가입니다.
STAR(Situation-Task-Action-Result) 구조를 따르되,
채용 담당자가 한 눈에 파악할 수 있는 간결하고 임팩트 있는 개조식 문체로 작성하세요.
숫자와 구체적인 지표를 최대한 활용하세요.
문장은 동사로 시작하고 결과를 명확히 드러내세요."""

_PROJECT_SYSTEM = """당신은 IT 개발자의 포트폴리오 문서 작성을 돕는 전문가입니다.
주어진 프로젝트 정보를 바탕으로 채용 담당자에게 임팩트 있게 전달되는
포트폴리오용 프로젝트 소개 문단을 작성하세요.
기술적 성취와 비즈니스 임팩트를 균형 있게 서술하세요."""

_RESUME_SYSTEM = """당신은 IT 개발자의 경력기술서 전체 문서 작성을 돕는 전문가입니다.
주어진 모든 프로젝트와 작업 내역을 기반으로 완성된 경력기술서 초안을 Markdown 형식으로 작성하세요.
각 프로젝트별로 작업 내역을 개조식 bullet point로 정리하고,
채용 담당자가 읽기 쉬운 구조로 작성하세요."""

_REFINE_SYSTEM = """당신은 IT 개발자의 경력기술서 문구를 개선하는 전문가입니다.
주어진 문구를 더 임팩트 있고 명확하며 채용에 유리한 표현으로 개선해주세요.
원본 의미를 유지하면서 더 강력한 동사와 구체적인 수치를 활용하세요."""

_JD_MATCH_SYSTEM = """당신은 개발자 채용 전문가입니다.
주어진 채용 공고(JD)를 분석하고, 포트폴리오와 비교하여:
1. 핵심 키워드 추출
2. 일치율 분석 (%)
3. 강조할 경험 추천
4. 보완할 내용 제안
을 구체적으로 알려주세요."""

# ---------------------------------------------------------------------------
# AI 서비스 클래스
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_RETRY_DELAY = 2.0  # 초


class AIService:
    def __init__(self, config: Config):
        self.config = config

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _get_provider(self, provider_name: Optional[str] = None) -> AIProviderConfig:
        name = provider_name or self.config.default_ai_provider
        if not name:
            raise DevfolioAINotConfiguredError()
        provider = self.config.get_provider(name)
        if not provider:
            raise DevfolioAIError(
                f"등록되지 않은 Provider: {name}",
                hint="`devfolio config ai list`로 등록된 Provider를 확인하세요.",
            )
        return provider

    def _model_string(self, provider: AIProviderConfig) -> str:
        """litellm 모델 문자열 반환."""
        mapping = {
            "anthropic": f"anthropic/{provider.model}",
            "openai": provider.model,
            "gemini": f"gemini/{provider.model}",
            "ollama": f"ollama/{provider.model}",
        }
        return mapping.get(provider.name, provider.model)

    def _set_env_key(self, provider: AIProviderConfig) -> None:
        """API 키를 환경 변수에 설정 (litellm이 읽도록)."""
        if provider.name == "ollama":
            return
        api_key = get_api_key(provider.name)
        if not api_key:
            raise DevfolioAIAuthError(provider.name)
        env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }
        env_var = env_map.get(provider.name, f"{provider.name.upper()}_API_KEY")
        os.environ[env_var] = api_key

    def _call(
        self,
        system_prompt: str,
        user_prompt: str,
        provider_name: Optional[str] = None,
    ) -> str:
        """litellm 호출 (재시도 + 예외 변환 포함, lazy import)."""
        try:
            import litellm  # lazy import for fast CLI startup
        except ImportError:
            raise DevfolioAIError(
                "litellm이 설치되지 않았습니다.",
                hint="`pip install devfolio[ai]`로 AI 의존성을 설치하세요.",
            )

        provider = self._get_provider(provider_name)
        self._set_env_key(provider)

        kwargs: dict = {
            "model": self._model_string(provider),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if provider.base_url:
            kwargs["api_base"] = provider.base_url

        last_error: Exception = RuntimeError("알 수 없는 오류")
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                logger.debug("AI 호출 시도 %d/%d (model=%s)", attempt, _MAX_RETRIES, kwargs["model"])
                response = litellm.completion(**kwargs)
                return response.choices[0].message.content or ""
            except Exception as e:
                err_class = type(e).__name__
                if "AuthenticationError" in err_class or "Unauthorized" in err_class:
                    raise DevfolioAIAuthError(provider.name) from e
                if "RateLimitError" in err_class:
                    if attempt < _MAX_RETRIES:
                        logger.warning("Rate limit 발생, %0.1f초 후 재시도 (%d/%d)", _RETRY_DELAY * attempt, attempt, _MAX_RETRIES)
                        time.sleep(_RETRY_DELAY * attempt)
                        continue
                    raise DevfolioAIRateLimitError(provider.name) from e
                last_error = e
                logger.warning("AI 호출 실패 (%d/%d): %s", attempt, _MAX_RETRIES, e)
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)
        raise DevfolioAIError(str(last_error)) from last_error

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def generate_task_text(
        self,
        task: Task,
        lang: str = "ko",
        provider_name: Optional[str] = None,
        force_refresh: bool = False,
    ) -> str:
        """작업 내역 → 경력기술서 bullet point."""
        if task.ai_generated_text and not force_refresh:
            return task.ai_generated_text

        lang_map = {
            "ko": "한국어로 작성하세요.",
            "en": "영어로 작성하세요.",
            "both": "한국어와 영어를 병기하여 작성하세요.",
        }

        prompt = f"""다음 작업 내역을 경력기술서 bullet point로 변환해주세요.

작업명: {task.name}
문제 상황: {task.problem}
해결 방법: {task.solution}
성과: {task.result}
사용 기술: {", ".join(task.tech_used)}

{lang_map.get(lang, lang_map["ko"])}
개조식 bullet point 3~5개를 작성해주세요."""

        return self._call(_TASK_SYSTEM, prompt, provider_name)

    def generate_project_summary(
        self,
        project: Project,
        lang: str = "ko",
        provider_name: Optional[str] = None,
    ) -> str:
        """프로젝트 전체 요약 생성."""
        tasks_text = "\n".join(
            f"- {t.name}: {t.problem} → {t.solution} (결과: {t.result})"
            for t in project.tasks
        ) or "작업 내역 없음"

        prompt = f"""다음 프로젝트 정보를 바탕으로 포트폴리오용 소개 문단을 작성해주세요.

프로젝트명: {project.name}
기간: {project.period.display()}
역할: {project.role}
기술 스택: {", ".join(project.tech_stack)}
한 줄 요약: {project.summary}

주요 작업 내역:
{tasks_text}

언어: {"한국어" if lang == "ko" else "영어"}
3~5문장으로 작성해주세요."""

        return self._call(_PROJECT_SYSTEM, prompt, provider_name)

    def generate_full_resume(
        self,
        projects: list[Project],
        user_name: str = "",
        lang: str = "ko",
        provider_name: Optional[str] = None,
    ) -> str:
        """전체 경력기술서 Markdown 생성."""
        projects_text = ""
        for project in projects:
            tasks_text = "\n".join(
                f"  - [{t.name}] 문제: {t.problem} / 해결: {t.solution} / 성과: {t.result}"
                for t in project.tasks
            )
            projects_text += (
                f"### {project.name}\n"
                f"- 기간: {project.period.display()}\n"
                f"- 소속: {project.organization}\n"
                f"- 역할: {project.role}\n"
                f"- 기술 스택: {', '.join(project.tech_stack)}\n"
                f"- 팀 규모: {project.team_size}명\n"
                f"{tasks_text}\n\n"
            )

        prompt = f"""다음 개발자의 전체 프로젝트 이력을 바탕으로 경력기술서 Markdown 문서를 작성해주세요.

개발자: {user_name}

프로젝트 이력:
{projects_text}

언어: {"한국어" if lang == "ko" else "영어"}
완성된 경력기술서 형식으로 작성해주세요."""

        return self._call(_RESUME_SYSTEM, prompt, provider_name)

    def refine_text(
        self,
        text: str,
        provider_name: Optional[str] = None,
    ) -> str:
        """기존 문구 개선."""
        prompt = f"""다음 경력기술서 문구를 더 임팩트 있게 개선해주세요:

{text}"""
        return self._call(_REFINE_SYSTEM, prompt, provider_name)

    def match_job_description(
        self,
        jd_text: str,
        projects: list[Project],
        provider_name: Optional[str] = None,
    ) -> str:
        """채용 공고 JD와 포트폴리오 매칭 분석."""
        portfolio_summary = "\n".join(
            f"- {p.name} ({p.period.display()}): {p.summary} | 기술: {', '.join(p.tech_stack)}"
            for p in projects
        )

        prompt = f"""다음 채용 공고와 포트폴리오를 분석해주세요.

[채용 공고]
{jd_text}

[포트폴리오 요약]
{portfolio_summary}

분석 결과를 아래 형식으로 작성해주세요:
1. 핵심 요구 키워드 (JD에서 추출)
2. 매칭 키워드 (포트폴리오와 일치)
3. 부족한 키워드 (포트폴리오에 없음)
4. 매칭 점수 (0~100%)
5. 강조 추천 프로젝트/경험
6. 어필 방법 제안"""

        return self._call(_JD_MATCH_SYSTEM, prompt, provider_name)

    def test_connection(self, provider_name: Optional[str] = None) -> tuple[bool, str]:
        """AI Provider 연결 테스트."""
        try:
            result = self._call(
                "You are a helpful assistant.",
                "Please respond with exactly: CONNECTION_OK",
                provider_name,
            )
            return True, result
        except Exception as e:
            return False, str(e)
