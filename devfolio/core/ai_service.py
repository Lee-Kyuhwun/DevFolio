"""AI Provider 추상화 서비스 (litellm 기반, lazy import)."""

import json
import os
import re
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
from devfolio.models.draft import ProjectDraft
from devfolio.models.project import Project, Task
from devfolio.utils.security import get_api_key

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 시스템 프롬프트 (모듈 상수)
# ---------------------------------------------------------------------------

_NO_PREAMBLE = "답변은 요청한 형식의 내용만 바로 작성하세요. 인사말, 서두, 복수 버전 제안, 작성 가이드 설명을 포함하지 마세요."

_TASK_SYSTEM = f"""당신은 IT 개발자의 경력기술서 작성을 돕는 전문가입니다.
채용 담당자와 실무 리드가 함께 읽는다는 전제로,
기능 나열이 아니라 책임 범위, 기술적 판단, 구현 방식, 운영상 효과가 드러나는 achievement bullet을 작성하세요.
STAR(Situation-Task-Action-Result)를 참고하되 문장을 기계적으로 나누지 말고,
한 줄 안에서 구현 사실과 결과를 자연스럽게 연결하세요.
숫자와 구체적인 지표를 최대한 활용하고, 수치가 없으면 안정성·유지보수성·운영 효율 개선을 구체적으로 표현하세요.
{_NO_PREAMBLE}"""

_PROJECT_SYSTEM = f"""당신은 IT 개발자의 포트폴리오 문서 작성을 돕는 전문가입니다.
채용 담당자와 실무 리드가 함께 읽는다는 전제로,
주어진 프로젝트 정보를 바탕으로 책임 범위, 문제 맥락, 핵심 기술 판단, 구현 내용, 결과가 드러나는
현업형 프로젝트 소개 문단을 작성하세요.
기술 스택은 단순 나열하지 말고 어떤 문제 해결이나 개선과 연결되는지 문장 안에서 설명하세요.
{_NO_PREAMBLE}"""

_RESUME_SYSTEM = f"""당신은 IT 개발자의 경력기술서 전체 문서 작성을 돕는 전문가입니다.
주어진 모든 프로젝트와 작업 내역을 기반으로 완성된 경력기술서 초안을 Markdown 형식으로 작성하세요.
각 프로젝트별로 작업 내역을 개조식 bullet point로 정리하고,
채용 담당자가 읽기 쉬운 구조로 작성하세요.
{_NO_PREAMBLE}"""

_REFINE_SYSTEM = f"""당신은 IT 개발자의 경력기술서 문구를 개선하는 전문가입니다.
주어진 문구를 더 임팩트 있고 명확하며 채용에 유리한 표현으로 개선해주세요.
원본 의미를 유지하면서 더 강력한 동사와 구체적인 수치를 활용하세요.
{_NO_PREAMBLE}"""

_CODE_ANALYSIS_SYSTEM = """당신은 소스 코드와 프로젝트 메타데이터를 분석해 개발자 포트폴리오를 작성하는 전문가입니다.
주어진 정보를 바탕으로:
1. 프로젝트 유형과 목적을 정확히 파악하세요
2. 핵심 기술 도전과 해결 방법을 구체적으로 서술하세요
3. 코드에서 실제 확인된 정보만 사용하세요 (추측 금지)
반드시 JSON 객체만 반환하세요. 마크다운 코드블록 사용 금지."""

_JD_MATCH_SYSTEM = """당신은 개발자 채용 전문가입니다.
주어진 채용 공고(JD)를 분석하고, 포트폴리오와 비교하여:
1. 핵심 키워드 추출
2. 일치율 분석 (%)
3. 강조할 경험 추천
4. 보완할 내용 제안
을 구체적으로 알려주세요."""

_INTAKE_SYSTEM = """당신은 개발자 포트폴리오 작성 도우미입니다.
사용자가 자유롭게 적은 프로젝트 설명을 읽고, 포트폴리오 작성에 적합한 구조화 초안을 JSON으로 정리하세요.
사실을 임의로 과장하지 말고, 불명확한 값은 빈 문자열이나 null로 남겨두세요.
다만 서술 안에 암시된 역할 범위, 기능 단위 작업, 배포/운영/성능/안정성 신호는 최대한 구조화해서 추출하세요.
반드시 JSON 객체만 반환하세요. 마크다운 코드블록은 사용하지 마세요."""

# ---------------------------------------------------------------------------
# 후처리 유틸리티
# ---------------------------------------------------------------------------

def _strip_preamble(text: str) -> str:
    """AI 응답에서 불필요한 전문구·복수 버전·가이드 설명을 제거한다."""
    text = text.strip()
    # "네, 알겠습니다." / "안녕하세요." 등 인사 첫 줄 제거
    text = re.sub(r'^(네[,.]?\s*알겠습니다[.!]?|안녕하세요[.!]?)[^\n]*\n+', '', text)
    # "### Version 1 (...)" 형태가 있으면 첫 번째 버전 본문만 추출
    version_match = re.search(
        r'###?\s*\*{0,2}Version\s*1[^#\n]*\*{0,2}\n+(.*?)(?=###?\s*\*{0,2}Version\s*2|\Z)',
        text, re.DOTALL,
    )
    if version_match:
        text = version_match.group(1).strip()
    # "---\n**[작성 가이드]**" 이후 내용 제거
    text = re.sub(r'\n*-{3,}\s*\n\*{0,2}\[?작성\s*가이드\]?\*{0,2}.*$', '', text, flags=re.DOTALL)
    return text.strip()


def _sentence_count(text: str) -> int:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return 0
    parts = [part.strip() for part in re.split(r'(?<=[.!?。！？])\s+', normalized) if part.strip()]
    if len(parts) > 1:
        return len(parts)
    line_parts = [line.strip() for line in text.splitlines() if line.strip()]
    return len(line_parts) if line_parts else 0


def _extract_bullet_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if re.match(r'^\s*(?:[-*•]|\d+\.)\s+', line)
    ]


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
                err_str = str(e)
                if "AuthenticationError" in err_class or "Unauthorized" in err_class:
                    raise DevfolioAIAuthError(provider.name) from e
                if "NotFoundError" in err_class or ('"code": 404' in err_str and "NOT_FOUND" in err_str):
                    raise DevfolioAIError(
                        f"모델을 찾을 수 없습니다: {provider.model}",
                        hint="설정 탭에서 모델 목록을 새로고침(↻)하고 다른 모델을 선택한 뒤 저장하세요.",
                    ) from e
                # quota 한도가 0인 경우 — 재시도 없이 즉시 안내
                if "limit: 0" in err_str or "free_tier_requests" in err_str:
                    raise DevfolioAIError(
                        f"{provider.name} 무료 티어 할당량이 0입니다.",
                        hint=(
                            "Google AI Studio는 결제 수단을 등록해야 무료 quota가 활성화됩니다. "
                            "https://aistudio.google.com 에서 결제 정보를 등록하거나 "
                            "다른 AI 제공자(Anthropic 등)로 전환하세요."
                        ),
                    ) from e
                if "RateLimitError" in err_class or "RESOURCE_EXHAUSTED" in err_str:
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

    @staticmethod
    def _language_instruction(lang: str) -> str:
        mapping = {
            "ko": "한국어로 작성하세요.",
            "en": "영어로 작성하세요.",
            "both": "한국어와 영어를 함께 제공합니다. 먼저 한국어, 다음에 영어를 작성하세요.",
        }
        return mapping.get(lang, mapping["ko"])

    @staticmethod
    def _extract_json(raw: str) -> dict:
        cleaned = raw.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
        if fenced:
            cleaned = fenced.group(1).strip()

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise DevfolioAIError(
                "AI가 구조화 초안을 올바른 JSON으로 반환하지 않았습니다.",
                hint="다시 시도하거나 모델 응답 형식을 점검하세요.",
            ) from e

        if not isinstance(payload, dict):
            raise DevfolioAIError(
                "AI가 프로젝트 초안을 객체 형태로 반환하지 않았습니다.",
                hint="다시 시도하거나 다른 AI Provider를 선택하세요.",
            )
        return payload

    @staticmethod
    def _draft_project_to_project(draft: ProjectDraft) -> Project:
        tasks = [
            Task(
                id=task.id or f"draft_task_{index}",
                name=task.name or f"Task {index + 1}",
                period=task.period,
                problem=task.problem,
                solution=task.solution,
                result=task.result,
                tech_used=task.tech_used,
                keywords=task.keywords,
                ai_generated_text=task.ai_generated_text,
            )
            for index, task in enumerate(draft.tasks)
        ]
        return Project(
            id=draft.id or "draft_project",
            name=draft.name or "Untitled Project",
            type=draft.type,
            status=draft.status,
            organization=draft.organization,
            period=draft.period,
            role=draft.role,
            team_size=draft.team_size,
            tech_stack=draft.tech_stack,
            summary=draft.summary,
            tags=draft.tags,
            tasks=tasks,
        )

    @staticmethod
    def _join_values(values: list[str], fallback: str = "없음") -> str:
        cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
        return ", ".join(cleaned) if cleaned else fallback

    @staticmethod
    def _execution_scope(team_size: int) -> str:
        return "단독 수행" if team_size <= 1 else f"{team_size}명 팀 내 담당"

    def _portfolio_style_guide(self) -> str:
        return """[현업형 작성 가이드]
- 독자는 채용 담당자와 실무 리드입니다. 읽기 쉬우면서도 기술적 판단이 보여야 합니다.
- 반드시 책임 범위, 문제 맥락, 핵심 기술 판단, 구현/개선 내용, 결과 또는 운영상 효과를 드러내세요.
- 추상적 미사여구, 근거 없는 '최적화/혁신/완성도 확보', 의미 없는 기술 나열은 피하세요.
- 같은 의미의 동사나 문장 구조를 반복하지 마세요."""

    def _format_task_context(self, task: Task) -> str:
        return "\n".join(
            [
                f"작업명: {task.name}",
                f"기간: {task.period.display()}",
                f"문제 상황: {task.problem or '명시되지 않음'}",
                f"해결 방법: {task.solution or '명시되지 않음'}",
                f"성과/영향: {task.result or '명시되지 않음'}",
                f"사용 기술: {self._join_values(task.tech_used)}",
                f"키워드: {self._join_values(task.keywords)}",
            ]
        )

    def _format_project_context(self, project: Project) -> str:
        task_lines = []
        for index, task in enumerate(project.tasks, start=1):
            task_lines.append(
                "\n".join(
                    [
                        f"[Task {index}]",
                        self._format_task_context(task),
                    ]
                )
            )

        tasks_section = "\n\n".join(task_lines) if task_lines else "작업 내역 없음"
        return "\n".join(
            [
                f"프로젝트명: {project.name}",
                f"프로젝트 유형: {project.type_display()} / 상태: {project.status_display()}",
                f"기간: {project.period.display()}",
                f"소속: {project.organization or '명시되지 않음'}",
                f"역할: {project.role or '명시되지 않음'}",
                f"수행 범위: {self._execution_scope(project.team_size)}",
                f"기술 스택: {self._join_values(project.tech_stack)}",
                f"태그: {self._join_values(project.tags)}",
                f"기존 요약: {project.summary or '없음'}",
                "",
                "[주요 작업 내역]",
                tasks_section,
            ]
        )

    def _task_prompt_guide(self) -> str:
        return "\n".join(
            [
                self._portfolio_style_guide(),
                "[작업 bullet 규칙]",
                "- bullet point 3~5개만 작성하세요.",
                "- 각 bullet은 '행동 + 대상/문제 + 기술적 결정/구현 + 결과' 흐름을 따르세요.",
                "- 작업명 자체를 반복하지 말고, 구현 사실과 효과를 한 줄 안에서 연결하세요.",
                "- '기능을 개발했습니다', '안정성과 완성도를 높였습니다', '사용자 경험을 개선했습니다'처럼 근거 없는 문장을 쓰지 마세요.",
            ]
        )

    def _project_prompt_guide(self) -> str:
        return "\n".join(
            [
                self._portfolio_style_guide(),
                "[프로젝트 소개 문단 규칙]",
                "- 소개 문단은 4~6문장으로 작성하세요.",
                "- 1문장: 프로젝트 성격과 본인 역할/책임 범위",
                "- 2문장: 해결하려던 문제나 도메인 맥락",
                "- 3~4문장: 핵심 기술적 실행 또는 개선 포인트",
                "- 마지막 문장: 결과, 운영상 효과, 안정성/유지보수성 측면의 임팩트",
                "- 기술 스택은 단순 나열하지 말고 어떤 문제 해결에 연결됐는지 문장 안에서 설명하세요.",
            ]
        )

    def _intake_prompt_guide(self) -> str:
        return "\n".join(
            [
                "[추출 우선순위]",
                "- role, organization, team_size를 가능한 범위에서 추출하세요.",
                "- task는 기능 단위 또는 책임 단위로 나누고 각 task에 problem, solution, result를 채우세요.",
                "- tech_stack, tech_used, keywords는 서술에 등장하는 실제 기술/개념만 추출하세요.",
                "- 배포, 운영, 성능, 안정성, 자동화, 모니터링 관련 단서는 우선적으로 구조화하세요.",
            ]
        )

    def _call_with_quality_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        provider_name: Optional[str],
        validator,
        retry_instruction: str,
        failure_message: str,
    ) -> str:
        response = _strip_preamble(self._call(system_prompt, user_prompt, provider_name))
        if validator(response):
            return response

        retry_prompt = (
            f"{user_prompt}\n\n"
            f"[추가 교정 지시]\n"
            f"{retry_instruction}"
        )
        response = _strip_preamble(self._call(system_prompt, retry_prompt, provider_name))
        if validator(response):
            return response

        raise DevfolioAIError(
            failure_message,
            hint="같은 작업을 다시 시도하거나 다른 AI Provider로 재생성해보세요.",
        )

    @staticmethod
    def _is_good_project_summary(text: str) -> bool:
        sentences = _sentence_count(text)
        if sentences >= 4:
            return True
        return sentences >= 3 and len(text.strip()) >= 180

    @staticmethod
    def _is_good_task_bullets(text: str) -> bool:
        bullet_lines = _extract_bullet_lines(text)
        return 3 <= len(bullet_lines) <= 5

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

        prompt = f"""다음 작업 정보를 바탕으로 현업형 achievement bullet을 작성해주세요.

[작업 컨텍스트]
{self._format_task_context(task)}

{self._task_prompt_guide()}
언어 지시: {self._language_instruction(lang)}
설명 없이 bullet point 목록만 반환하세요."""

        return self._call_with_quality_retry(
            _TASK_SYSTEM,
            prompt,
            provider_name,
            validator=self._is_good_task_bullets,
            retry_instruction="반드시 bullet point 3~5개만 작성하고, 각 bullet은 구현 사실과 결과를 함께 드러내세요.",
            failure_message="AI가 현업형 작업 bullet 형식을 충분히 지키지 못했습니다.",
        )

    def generate_project_summary(
        self,
        project: Project,
        lang: str = "ko",
        provider_name: Optional[str] = None,
    ) -> str:
        """프로젝트 전체 요약 생성."""
        prompt = f"""다음 프로젝트 정보를 바탕으로 현업형 프로젝트 소개 문단을 작성해주세요.

[프로젝트 컨텍스트]
{self._format_project_context(project)}

{self._project_prompt_guide()}
언어 지시: {self._language_instruction(lang)}
소개 문단 텍스트만 반환하세요. 인사말이나 부연 설명 없이 본문만 작성하세요."""

        return self._call_with_quality_retry(
            _PROJECT_SYSTEM,
            prompt,
            provider_name,
            validator=self._is_good_project_summary,
            retry_instruction="문단을 4~6문장으로 보강하고, 책임 범위·문제 맥락·핵심 구현·결과가 모두 드러나게 다시 작성하세요.",
            failure_message="AI가 프로젝트 소개 문단을 충분한 밀도로 생성하지 못했습니다.",
        )

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

언어 지시: {self._language_instruction(lang)}
경력기술서 Markdown 문서만 반환하세요. 인사말이나 설명 없이 문서 본문만 작성하세요."""

        return _strip_preamble(self._call(_RESUME_SYSTEM, prompt, provider_name))

    def generate_project_draft(
        self,
        raw_text: str,
        lang: str = "ko",
        provider_name: Optional[str] = None,
    ) -> ProjectDraft:
        """자유 텍스트를 구조화된 프로젝트 초안으로 변환한다."""
        prompt = f"""다음 자유 텍스트를 읽고 개발자 포트폴리오용 프로젝트 초안 JSON으로 구조화해주세요.

요구 사항:
- 사실로 보이지 않는 정보는 추측하지 말고 빈 문자열 또는 null로 두세요.
- type은 company, side, course 중 하나만 사용하세요.
- status는 done, in_progress, planned 중 하나만 사용하세요.
- period는 {{\"start\": \"YYYY-MM 또는 null\", \"end\": \"YYYY-MM 또는 null\"}} 형식으로 작성하세요.
- tech_stack, tags, tasks, tech_used, keywords는 항상 배열로 반환하세요.
- tasks 각 항목은 name, period, problem, solution, result, tech_used, keywords, ai_generated_text 필드를 모두 포함하세요.
- team_size를 알 수 없으면 1을 사용하세요.
- summary는 과장된 마케팅 문구보다 프로젝트 성격과 역할이 드러나는 짧은 초안으로 작성하세요.
- 자유 텍스트에 운영, 배포, 성능, 안정성, 자동화 관련 단서가 있으면 적절한 task나 keywords에 반영하세요.
- 응답은 JSON 객체만 반환하세요.

{self._intake_prompt_guide()}

출력 스키마:
{{
  "name": "",
  "type": "company",
  "status": "done",
  "organization": "",
  "period": {{"start": null, "end": null}},
  "role": "",
  "team_size": 1,
  "tech_stack": [],
  "summary": "",
  "tags": [],
  "tasks": [
    {{
      "name": "",
      "period": {{"start": null, "end": null}},
      "problem": "",
      "solution": "",
      "result": "",
      "tech_used": [],
      "keywords": [],
      "ai_generated_text": ""
    }}
  ]
}}

언어 지시: {self._language_instruction(lang)}

[자유 텍스트]
{raw_text}"""

        payload = self._extract_json(self._call(_INTAKE_SYSTEM, prompt, provider_name))
        payload.setdefault("name", "")
        payload.setdefault("type", "company")
        payload.setdefault("status", "done")
        payload.setdefault("organization", "")
        payload.setdefault("period", {"start": None, "end": None})
        payload.setdefault("role", "")
        payload.setdefault("team_size", 1)
        payload.setdefault("tech_stack", [])
        payload.setdefault("summary", "")
        payload.setdefault("tags", [])
        payload.setdefault("tasks", [])
        payload["raw_text"] = raw_text

        for task in payload["tasks"]:
            if not isinstance(task, dict):
                continue
            task.setdefault("name", "")
            task.setdefault("period", {"start": None, "end": None})
            task.setdefault("problem", "")
            task.setdefault("solution", "")
            task.setdefault("result", "")
            task.setdefault("tech_used", [])
            task.setdefault("keywords", [])
            task.setdefault("ai_generated_text", "")

        return ProjectDraft.model_validate(payload)

    def generate_draft_project_summary(
        self,
        draft: ProjectDraft,
        lang: str = "ko",
        provider_name: Optional[str] = None,
    ) -> str:
        """저장 전 초안 기준 프로젝트 요약을 생성한다."""
        return self.generate_project_summary(
            self._draft_project_to_project(draft),
            lang=lang,
            provider_name=provider_name,
        )

    def generate_draft_task_texts(
        self,
        draft: ProjectDraft,
        lang: str = "ko",
        provider_name: Optional[str] = None,
        force_refresh: bool = True,
    ) -> ProjectDraft:
        """저장 전 초안 기준으로 작업 bullet을 일괄 생성한다."""
        if not draft.tasks:
            raise DevfolioAIError(
                "AI bullet을 생성할 작업 내역이 없습니다.",
                hint="초안에 최소 한 개의 작업을 추가한 뒤 다시 시도하세요.",
            )

        updated_tasks = []
        for index, task in enumerate(draft.tasks, start=1):
            temp_task = Task(
                id=task.id or f"draft_task_{index}",
                name=task.name or f"Task {index}",
                period=task.period,
                problem=task.problem,
                solution=task.solution,
                result=task.result,
                tech_used=task.tech_used,
                keywords=task.keywords,
                ai_generated_text=task.ai_generated_text,
            )
            generated = self.generate_task_text(
                temp_task,
                lang=lang,
                provider_name=provider_name,
                force_refresh=force_refresh,
            )
            updated_tasks.append(task.model_copy(update={"ai_generated_text": generated}))

        return draft.model_copy(update={"tasks": updated_tasks})

    def refine_text(
        self,
        text: str,
        provider_name: Optional[str] = None,
    ) -> str:
        """기존 문구 개선."""
        prompt = f"""다음 경력기술서 문구를 더 임팩트 있게 개선해주세요. 개선된 문구만 반환하세요. 설명이나 원문 비교 없이.

{text}"""
        return _strip_preamble(self._call(_REFINE_SYSTEM, prompt, provider_name))

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

    def analyze_project_from_code(
        self,
        repo_name: str,
        project_context: dict,
        scan_metrics: dict,
        lang: str = "ko",
        provider_name: Optional[str] = None,
    ) -> dict:
        """소스 코드·README·의존성 정보를 분석해 포트폴리오 초안을 생성한다.

        project_context: analyze_project_structure() 반환값
          {"readme": str, "dependencies": dict, "key_files": dict[str,str], "languages": dict}
        scan_metrics: git 통계
          {"commits": int, "period_months": int, "languages": dict}
        반환: {"project_type", "purpose", "key_features", "problem", "solution",
               "tech_stack", "summary", "tasks"}
        """
        # --- README 섹션 ---
        readme_section = ""
        if project_context.get("readme"):
            readme_section = f"[README]\n{project_context['readme']}\n\n"

        # --- 의존성 섹션 ---
        deps_section = ""
        if project_context.get("dependencies"):
            lines = []
            for fname, pkgs in project_context["dependencies"].items():
                lines.append(f"{fname}: {', '.join(pkgs[:20])}")
            deps_section = "[의존성]\n" + "\n".join(lines) + "\n\n"

        # --- 소스 파일 섹션 ---
        files_section = ""
        if project_context.get("key_files"):
            parts = []
            for fpath, content in project_context["key_files"].items():
                parts.append(f"--- {fpath} ---\n{content}")
            files_section = "[주요 소스 파일]\n" + "\n\n".join(parts) + "\n\n"

        # --- Git 통계 섹션 ---
        langs_str = ", ".join(
            f"{k}({v}%)" for k, v in (scan_metrics.get("languages") or {}).items()
        )
        git_section = (
            f"[Git 통계]\n"
            f"레포지토리: {repo_name}\n"
            f"총 커밋: {scan_metrics.get('commits', 0)}\n"
            f"언어 비율: {langs_str}\n\n"
        )

        schema = """{
  "project_type": "웹 API | CLI 도구 | 라이브러리 | 모바일 앱 | ...",
  "purpose": "한 문장 핵심 목적",
  "key_features": ["주요 기능1", "주요 기능2"],
  "problem": "이 프로젝트가 해결하는 문제 (2~4문장)",
  "solution": "구현 방식과 기술적 접근 (2~4문장)",
  "tech_stack": ["실제 사용 기술 목록"],
  "summary": "포트폴리오용 한 줄 소개",
  "tasks": [
    {
      "name": "작업명",
      "problem": "이 작업이 해결한 구체적 문제 (1~2문장)",
      "solution": "구현 방법 (2~3문장)",
      "tech_used": ["기술"],
      "result": "정성적 성과 — 무엇을 달성했는지 1~2문장. 커밋 수·LOC 같은 raw 통계 제외"
    }
  ]
}"""

        lang_instr = self._language_instruction(lang)
        prompt = (
            f"다음 프로젝트 정보를 분석해 포트폴리오 초안을 JSON으로 작성해주세요.\n\n"
            f"{git_section}{readme_section}{deps_section}{files_section}"
            f"[출력 스키마]\n{schema}\n\n"
            f"[중요 규칙]\n"
            f"- tasks는 2~3개로 제한하세요. 각 task는 프로젝트 내 독립적인 기능 영역을 나타냅니다.\n"
            f"- tasks의 result 필드에는 정성적 성과만 작성하세요. 커밋 수·LOC 수치는 포함하지 마세요.\n"
            f"- 언어 지시: {lang_instr}\n"
            f"반드시 위 스키마 형태의 JSON 객체만 반환하세요."
        )

        raw = self._call(_CODE_ANALYSIS_SYSTEM, prompt, provider_name)
        payload = self._extract_json(raw)

        # 필수 키 보장 (AI가 일부 생략할 경우 대비)
        for key in ("project_type", "purpose", "key_features", "problem", "solution", "tech_stack", "summary", "tasks"):
            payload.setdefault(key, [] if key in ("key_features", "tech_stack", "tasks") else "")

        return payload

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
