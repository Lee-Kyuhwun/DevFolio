"""AI Provider 추상화 서비스 (litellm 기반, lazy import)."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

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

_MAX_RETRIES = 2
# Rate limit 재시도는 RPM 리셋 주기(60초)에 맞춰야 의미가 있음
# 짧은 간격 재시도는 quota만 낭비
_RETRY_DELAY = 2.0  # 초 (일반 오류용)
_RATE_LIMIT_RETRY_DELAY = 65.0  # 초 (rate limit 전용 — RPM 윈도우 넘김)

_GENERATION_MODEL_ALIASES: dict[str, dict[str, str]] = {
    # Gemini stable snapshot -> generation-safe stable alias
    "gemini": {
        "gemini-2.5-flash-lite-001": "gemini-2.5-flash-lite",
    }
}

_GENERATION_SAFE_MODEL_REGISTRY: dict[str, tuple[str, ...]] = {
    "anthropic": (
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "claude-haiku-4-5-20251001",
    ),
    "openai": ("gpt-4o", "gpt-4o-mini", "gpt-4-turbo"),
    # 무료 등급 우선 정렬 (출처: ai.google.dev/gemini-api/docs/pricing 2026-04)
    # gemini-2.0-flash / gemini-2.0-flash-lite: 2026-03 retire — 제거
    "gemini": (
        "gemini-2.5-flash",        # 무료 10 RPM / 250 RPD
        "gemini-2.5-flash-lite",   # 무료 15 RPM / 1000 RPD
        "gemini-2.5-pro",          # 유료
        "gemini-1.5-flash",        # 유료
        "gemini-1.5-pro",          # 유료
    ),
}


@dataclass(frozen=True)
class GenerationModelResolution:
    provider_name: str
    display_model: str
    generation_model: str
    candidate_models: tuple[str, ...]
    status: str
    warning: str = ""


def _clean_provider_model_name(model_name: str) -> str:
    return (model_name or "").strip().removeprefix("models/")


def normalize_provider_model_name(provider_name: str, model_name: str) -> str:
    return _clean_provider_model_name(model_name)


def is_legacy_provider_model(provider_name: str, model_name: str) -> bool:
    normalized = _clean_provider_model_name(model_name)
    return normalized in _GENERATION_MODEL_ALIASES.get(provider_name, {})


def _generation_alias(provider_name: str, model_name: str) -> str:
    normalized = normalize_provider_model_name(provider_name, model_name)
    if not normalized:
        return normalized
    return _GENERATION_MODEL_ALIASES.get(provider_name, {}).get(normalized, normalized)


def _safe_generation_models(provider_name: str) -> tuple[str, ...]:
    return _GENERATION_SAFE_MODEL_REGISTRY.get(provider_name, ())


def resolve_generation_model(provider_name: str, model_name: str) -> GenerationModelResolution:
    display_model = normalize_provider_model_name(provider_name, model_name)
    safe_models = _safe_generation_models(provider_name)

    if provider_name == "ollama":
        candidates = (display_model,) if display_model else ()
        return GenerationModelResolution(
            provider_name=provider_name,
            display_model=display_model,
            generation_model=display_model,
            candidate_models=candidates,
            status="ready" if display_model else "unavailable",
            warning="",
        )

    requested_generation = _generation_alias(provider_name, display_model)
    candidates: list[str] = []

    if requested_generation in safe_models:
        candidates.append(requested_generation)
    else:
        family_match = next(
            (
                safe_model
                for safe_model in safe_models
                if requested_generation.startswith(f"{safe_model}-")
            ),
            "",
        )
        if family_match:
            candidates.append(family_match)

    for safe_model in safe_models:
        if safe_model not in candidates:
            candidates.append(safe_model)

    generation_model = candidates[0] if candidates else requested_generation
    warning = ""
    status = "ready"

    if not generation_model:
        status = "unavailable"
        warning = "현재 생성에 사용할 수 있는 안전 모델이 없습니다."
    elif display_model and generation_model != requested_generation:
        status = "fallback"
        warning = f"저장된 모델 {display_model} 대신 생성 시 {generation_model}를 사용합니다."
    elif requested_generation and generation_model != display_model:
        status = "fallback"
        warning = f"저장된 모델 {display_model}은 생성 시 {generation_model}로 해석됩니다."
    elif display_model and display_model not in safe_models and requested_generation not in safe_models:
        status = "fallback"
        warning = f"저장된 모델 {display_model}은 생성용 안정 모델이 아니어서 {generation_model}를 사용합니다."

    return GenerationModelResolution(
        provider_name=provider_name,
        display_model=display_model,
        generation_model=generation_model,
        candidate_models=tuple(candidates),
        status=status,
        warning=warning,
    )


class EvidenceTask(BaseModel):
    name: str = ""
    period: dict[str, Optional[str]] = Field(default_factory=dict)
    problem: str = ""
    solution: str = ""
    result: str = ""
    tech_used: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class PortfolioEvidence(BaseModel):
    name: str
    project_type: str = ""
    status: str = ""
    role: str = ""
    organization: str = ""
    team_size: int = 1
    period: dict[str, Optional[str]] = Field(default_factory=dict)
    summary: str = ""
    problem: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    audience_value: list[str] = Field(default_factory=list)
    tasks: list[EvidenceTask] = Field(default_factory=list)
    focus_task: Optional[EvidenceTask] = None
    raw_text: str = ""


class ReviewResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    passed: bool = Field(alias="pass")
    scores: dict[str, int] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)


@dataclass
class GenerationProfile:
    mode: str
    language: str = "ko"
    audience: str = "백엔드/플랫폼/풀스택 개발자 채용 담당자"
    priority_keywords: tuple[str, ...] = (
        "확장성",
        "유지보수성",
        "안정성",
        "개발 생산성",
    )
    temperature: float = 0.3
    max_tokens: int = 2200


@dataclass
class PromptPack:
    system_prompt: str
    user_prompt: str
    review_prompt: str

    @classmethod
    def load(cls, lang: str = "ko") -> "PromptPack":
        root = Path(__file__).resolve().parent.parent / "prompts" / lang
        return cls(
            system_prompt=(root / "system_prompt.md").read_text(encoding="utf-8"),
            user_prompt=(root / "user_prompt.md").read_text(encoding="utf-8"),
            review_prompt=(root / "review_prompt.md").read_text(encoding="utf-8"),
        )


_PROMPT_PACK_CACHE: dict[str, PromptPack] = {}


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

    @staticmethod
    def _provider_model_string(provider_name: str, model_name: str) -> str:
        mapping = {
            "anthropic": f"anthropic/{model_name}",
            "openai": model_name,
            "gemini": f"gemini/{model_name}",
            "ollama": f"ollama/{model_name}",
        }
        return mapping.get(provider_name, model_name)

    def _model_string(self, provider: AIProviderConfig) -> str:
        """litellm 모델 문자열 반환."""
        resolution = resolve_generation_model(provider.name, provider.model)
        model_name = resolution.generation_model or normalize_provider_model_name(provider.name, provider.model)
        return self._provider_model_string(provider.name, model_name)

    def _runtime_model_candidates(self, provider: AIProviderConfig) -> list[str]:
        resolution = resolve_generation_model(provider.name, provider.model)
        candidates = list(resolution.candidate_models)
        if not candidates and resolution.generation_model:
            candidates = [resolution.generation_model]
        return candidates

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
        """system/user 2턴 호출 호환용 래퍼."""
        return self._call_messages(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            provider_name=provider_name,
        )

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
    def _prompt_pack(lang: str = "ko") -> PromptPack:
        if lang not in _PROMPT_PACK_CACHE:
            _PROMPT_PACK_CACHE[lang] = PromptPack.load(lang)
        return _PROMPT_PACK_CACHE[lang]

    @staticmethod
    def _period_dict(period) -> dict[str, Optional[str]]:
        return {
            "start": getattr(period, "start", None),
            "end": getattr(period, "end", None),
        }

    @staticmethod
    def _extract_metrics(text: str) -> list[str]:
        if not text:
            return []
        fragments = re.split(r"[,.]| 및 | 그리고 ", text)
        return [fragment.strip() for fragment in fragments if re.search(r"\d", fragment)]

    @staticmethod
    def _derive_audience_value(results: list[str]) -> list[str]:
        lowered = " ".join(results).lower()
        values: list[str] = []
        keyword_map = {
            "안정성": ("다운타임", "오류", "장애", "stability", "availability"),
            "유지보수성": ("리팩터", "유지보수", "표준화", "maintain", "refactor"),
            "개발 생산성": ("자동화", "배포 시간", "생산성", "workflow", "ci"),
            "확장성": ("확장", "스케일", "멀티", "확장성", "scale"),
        }
        for label, terms in keyword_map.items():
            if any(term in lowered for term in terms):
                values.append(label)
        return values

    @classmethod
    def _format_priority_keywords(cls, keywords: tuple[str, ...]) -> str:
        return "\n".join(f"- {keyword}" for keyword in keywords)

    def _call_messages(
        self,
        messages: list[dict[str, str]],
        provider_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """litellm 호출 (메시지 배열 직접 사용)."""
        try:
            import litellm  # lazy import for fast CLI startup
        except ImportError:
            raise DevfolioAIError(
                "litellm이 설치되지 않았습니다.",
                hint="`pip install devfolio[ai]`로 AI 의존성을 설치하세요.",
            )

        provider = self._get_provider(provider_name)
        self._set_env_key(provider)

        kwargs: dict = {"messages": messages}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if provider.base_url:
            kwargs["api_base"] = provider.base_url

        last_error: Exception = RuntimeError("알 수 없는 오류")
        model_candidates = self._runtime_model_candidates(provider)
        for model_index, runtime_model in enumerate(model_candidates, start=1):
            kwargs["model"] = self._provider_model_string(provider.name, runtime_model)
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    logger.debug(
                        "AI 호출 시도 %d/%d (model=%s, candidate=%d/%d)",
                        attempt,
                        _MAX_RETRIES,
                        kwargs["model"],
                        model_index,
                        len(model_candidates),
                    )
                    response = litellm.completion(**kwargs)
                    return response.choices[0].message.content or ""
                except Exception as e:
                    err_class = type(e).__name__
                    err_str = str(e)
                    if "AuthenticationError" in err_class or "Unauthorized" in err_class:
                        raise DevfolioAIAuthError(provider.name) from e
                    if "NotFoundError" in err_class or ('"code": 404' in err_str and "NOT_FOUND" in err_str):
                        last_error = e
                        if model_index < len(model_candidates):
                            logger.warning(
                                "모델을 찾지 못해 대체 후보로 재시도합니다: provider=%s requested=%s fallback=%s failure=%s",
                                provider.name,
                                provider.model,
                                model_candidates[model_index],
                                err_class,
                            )
                            break
                        raise DevfolioAIError(
                            f"모델을 찾을 수 없습니다: {provider.model}",
                            hint=f"시도한 생성 모델: {', '.join(model_candidates)}. 설정 탭에서 지원 모델 상태를 확인하거나 다른 제공자를 선택하세요.",
                        ) from e
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
                        # 일일 한도(RPD) 초과는 자정까지 복구 안 됨 — 즉시 실패
                        if "quota" in err_str.lower() and "day" in err_str.lower():
                            raise DevfolioAIRateLimitError(provider.name) from e
                        # RPM 초과: 60초 뒤에야 윈도우가 리셋됨.
                        # 짧은 간격 재시도는 quota만 낭비하므로 1회만 재시도
                        if attempt < _MAX_RETRIES:
                            logger.warning(
                                "Rate limit 발생, %0.0f초 후 재시도 (%d/%d) — 무료 RPM 한도 초과",
                                _RATE_LIMIT_RETRY_DELAY,
                                attempt,
                                _MAX_RETRIES,
                            )
                            time.sleep(_RATE_LIMIT_RETRY_DELAY)
                            continue
                        raise DevfolioAIRateLimitError(provider.name) from e
                    last_error = e
                    logger.warning("AI 호출 실패 (%d/%d): %s", attempt, _MAX_RETRIES, e)
                    if attempt < _MAX_RETRIES:
                        time.sleep(_RETRY_DELAY)
                        continue
                    break
        raise DevfolioAIError(str(last_error)) from last_error

    def build_evidence(
        self,
        project: Optional[Project] = None,
        task: Optional[Task] = None,
        raw_text: str = "",
    ) -> PortfolioEvidence:
        if task and not project:
            results = [task.result] if task.result else []
            return PortfolioEvidence(
                name=task.name or "Task",
                period=self._period_dict(task.period),
                problem=[task.problem] if task.problem else [],
                actions=[task.solution] if task.solution else [],
                results=results,
                metrics=self._extract_metrics(task.result),
                tech_stack=list(task.tech_used),
                audience_value=self._derive_audience_value(results),
                tasks=[
                    EvidenceTask(
                        name=task.name,
                        period=self._period_dict(task.period),
                        problem=task.problem,
                        solution=task.solution,
                        result=task.result,
                        tech_used=task.tech_used,
                        keywords=task.keywords,
                    )
                ],
                focus_task=EvidenceTask(
                    name=task.name,
                    period=self._period_dict(task.period),
                    problem=task.problem,
                    solution=task.solution,
                    result=task.result,
                    tech_used=task.tech_used,
                    keywords=task.keywords,
                ),
                raw_text=raw_text,
            )

        if not project:
            raise DevfolioAIError("프로젝트 또는 작업 evidence가 필요합니다.")

        results = [item.result for item in project.tasks if item.result]
        evidence_tasks = [
            EvidenceTask(
                name=item.name,
                period=self._period_dict(item.period),
                problem=item.problem,
                solution=item.solution,
                result=item.result,
                tech_used=item.tech_used,
                keywords=item.keywords,
            )
            for item in project.tasks
        ]
        return PortfolioEvidence(
            name=project.name,
            project_type=project.type,
            status=project.status,
            role=project.role,
            organization=project.organization,
            team_size=project.team_size,
            period=self._period_dict(project.period),
            summary=project.summary,
            problem=[item.problem for item in project.tasks if item.problem],
            actions=[item.solution for item in project.tasks if item.solution],
            results=results,
            metrics=[metric for item in results for metric in self._extract_metrics(item)],
            constraints=[],
            tech_stack=project.tech_stack,
            tags=project.tags,
            audience_value=self._derive_audience_value(results),
            tasks=evidence_tasks,
            raw_text=raw_text,
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

    def _render_generation_prompt(
        self,
        prompt_pack: PromptPack,
        evidence: PortfolioEvidence,
        profile: GenerationProfile,
    ) -> str:
        evidence_json = json.dumps(
            evidence.model_dump(),
            ensure_ascii=False,
            indent=2,
        )
        return prompt_pack.user_prompt.format(
            project_evidence_json=evidence_json,
            output_mode=profile.mode,
            audience=profile.audience,
            priority_keywords=self._format_priority_keywords(profile.priority_keywords),
            language=profile.language,
        )

    def _review_generated_text(
        self,
        prompt_pack: PromptPack,
        evidence: PortfolioEvidence,
        draft_text: str,
        profile: GenerationProfile,
        provider_name: Optional[str],
    ) -> ReviewResult:
        evidence_json = json.dumps(
            evidence.model_dump(),
            ensure_ascii=False,
            indent=2,
        )
        review_prompt = prompt_pack.review_prompt.format(
            project_evidence_json=evidence_json,
            draft_text=draft_text,
            output_mode=profile.mode,
        )
        raw = self._call_messages(
            [
                {"role": "system", "content": "리뷰어는 반드시 JSON 객체만 반환한다."},
                {"role": "user", "content": review_prompt},
            ],
            provider_name=provider_name,
            temperature=0.0,
            max_tokens=1200,
        )
        return ReviewResult.model_validate(self._extract_json(raw))

    def _validate_generated_output(self, mode: str, text: str) -> bool:
        if mode == "resume_bullets":
            return 4 <= len(_extract_bullet_lines(text)) <= 6
        if mode == "project_summary":
            sentences = _sentence_count(text)
            return 5 <= sentences <= 7
        return bool(text.strip())

    def _format_validation_feedback(self, mode: str) -> str:
        if mode == "resume_bullets":
            return "반드시 '- '로 시작하는 bullet 4~6개를 작성하고, 각 bullet에 행동·기술/맥락·결과를 모두 포함하며 너무 짧게 끝내지 마세요."
        if mode == "project_summary":
            return "반드시 5~7문장으로 작성하고, 책임 범위·문제 맥락·핵심 구현·기술 선택 이유·결과를 모두 포함하세요."
        return "출력 계약을 정확히 지켜 다시 작성하세요."

    def generate_with_review(
        self,
        *,
        evidence: PortfolioEvidence,
        profile: GenerationProfile,
        provider_name: Optional[str] = None,
    ) -> tuple[str, ReviewResult]:
        prompt_pack = self._prompt_pack("ko")
        user_prompt = self._render_generation_prompt(prompt_pack, evidence, profile)
        writer_messages = [
            {"role": "system", "content": prompt_pack.system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        draft = _strip_preamble(
            self._call_messages(
                writer_messages,
                provider_name=provider_name,
                temperature=profile.temperature,
                max_tokens=profile.max_tokens,
            )
        )
        review = self._review_generated_text(
            prompt_pack,
            evidence,
            draft,
            profile,
            provider_name,
        )
        if review.passed and self._validate_generated_output(profile.mode, draft):
            return draft, review

        revision_payload = json.dumps(
            review.model_dump(by_alias=True),
            ensure_ascii=False,
            indent=2,
        )
        revised_prompt = (
            f"{user_prompt}\n\n"
            f"<review_result>\n{revision_payload}\n</review_result>\n\n"
            f"<revision_rules>\n"
            f"- 리뷰의 revision_instructions와 missing_points를 모두 반영할 것.\n"
            f"- evidence 밖의 사실은 추가하지 말 것.\n"
            f"- {self._format_validation_feedback(profile.mode)}\n"
            f"</revision_rules>"
        )
        revised = _strip_preamble(
            self._call_messages(
                [
                    {"role": "system", "content": prompt_pack.system_prompt},
                    {"role": "user", "content": revised_prompt},
                ],
                provider_name=provider_name,
                temperature=profile.temperature,
                max_tokens=profile.max_tokens,
            )
        )
        if not self._validate_generated_output(profile.mode, revised):
            raise DevfolioAIError(
                "AI가 출력 형식을 충분히 지키지 못했습니다.",
                hint="같은 작업을 다시 시도하거나 다른 AI Provider로 재생성해보세요.",
            )
        return revised, review

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

        evidence = self.build_evidence(task=task)
        profile = GenerationProfile(
            mode="resume_bullets",
            language=lang,
            max_tokens=2200,
        )
        result, _ = self.generate_with_review(
            evidence=evidence,
            profile=profile,
            provider_name=provider_name,
        )
        return result

    def generate_project_summary(
        self,
        project: Project,
        lang: str = "ko",
        provider_name: Optional[str] = None,
    ) -> str:
        """프로젝트 전체 요약 생성."""
        evidence = self.build_evidence(project=project)
        profile = GenerationProfile(
            mode="project_summary",
            language=lang,
            max_tokens=2800,
        )
        result, _ = self.generate_with_review(
            evidence=evidence,
            profile=profile,
            provider_name=provider_name,
        )
        return result

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
        prompt = f"""<task>
다음 자유 텍스트를 읽고 개발자 포트폴리오용 프로젝트 초안 JSON으로 구조화해주세요.
</task>

<instructions>
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
</instructions>

<extraction_priorities>
{self._intake_prompt_guide()}
</extraction_priorities>

<output_schema>
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
</output_schema>

<language_instruction>{self._language_instruction(lang)}</language_instruction>

<project_brief>
{raw_text}
</project_brief>"""

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
