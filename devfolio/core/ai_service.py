"""AI Provider 추상화 서비스 (litellm 기반, lazy import).

[Python 문법 메모 — Java 개발자용]
  - `dict | list | str` 같은 표기는 Union 타입(3.10+)이며, Java의 `Object` + instanceof 분기와 비슷하다.
  - `@dataclass(frozen=True)`는 “불변 DTO”에 가깝고, Java의 record 처럼 값 객체로 쓰기 좋다.
  - `Field(default_factory=list)`는 “매 인스턴스마다 새 리스트”를 만들어 공유 참조 버그를 막는다.
  - `**kwargs`는 “가변 키워드 인수(Map 형태)”로, Java에서 Map<String, Object>를 받는 패턴과 유사하다.
  - 리스트/딕트 컴프리헨션은 for/if + add/put 을 한 줄로 합친 문법이다.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
)  # dataclass: 필드 선언만으로 DTO 생성(Java record/DTO 느낌).
import json
import os
from pathlib import Path
import re
import time
from typing import (
    Any,
    Optional,
)  # Any=Object, Optional[T]=nullable T 힌트(실행 강제 X).

from pydantic import BaseModel, ConfigDict, Field

from devfolio.exceptions import (
    DevfolioAIAuthError,
    DevfolioAIError,
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

_NO_PREAMBLE = "답변은 요청한 형식의 내용만 바로 작성하세요. 인사말, 서두, 복수 버전 제안, 작성 가이드 설명을 포함하지 마세요."  # 시스템 프롬프트 공통 규칙.

# 일본어·중국어 유니코드 범위 — AI가 언어 지시를 무시할 때 물리적으로 제거
_FOREIGN_CHAR_RANGES = (
    (0x3040, 0x309F),  # 히라가나
    (0x30A0, 0x30FF),  # 가타카나
    (0xFF65, 0xFF9F),  # 반각 가타카나
    (0x4E00, 0x9FFF),  # CJK 통합 한자 (일본 한자·중국어, 한국 한글은 해당 없음)
    (0x3400, 0x4DBF),  # CJK 확장 A
    (0x20000, 0x2A6DF),  # CJK 확장 B
    (0xF900, 0xFAFF),  # CJK 호환 한자
    (0x31F0, 0x31FF),  # 가타카나 음성 확장
    (0x3190, 0x319F),  # CJK 한문 부호
)


def _strip_foreign_chars(text: str) -> str:
    """AI 출력에서 일본어·중국어 문자를 제거한다. 한국어(한글)·영문은 유지."""
    if not text:
        return text
    result = []
    for ch in text:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in _FOREIGN_CHAR_RANGES):
            continue
        result.append(ch)
    cleaned = "".join(result)
    # 제거로 생긴 연속 공백 정리
    import re as _re

    return _re.sub(r"  +", " ", cleaned).strip()


def _prune_empty(data: Any) -> Any:
    """dict/list 에서 비어 있는 값을 재귀적으로 제거한다.

    evidence JSON 을 프롬프트에 주입할 때 null/빈 리스트/빈 dict/빈 문자열 필드를 제거해
    신호 대 잡음비를 높이기 위함. team_size 같은 0 허용 숫자는 유지한다.
    """
    if isinstance(data, dict):  # dict이면 key/value를 순회하며 비어있는 값을 제거.
        pruned: dict = {}
        for key, value in data.items():
            cleaned = _prune_empty(value)
            if cleaned in (None, "", [], {}):
                continue
            pruned[key] = cleaned
        return pruned
    if isinstance(data, list):  # list는 “컴프리헨션(필터+변환)”으로 간결하게 처리.
        return [
            _prune_empty(item)
            for item in data
            if _prune_empty(item) not in (None, "", [], {})
        ]
    return data


def _strip_foreign_in_dict(data: dict | list | str) -> dict | list | str:
    """JSON 딕셔너리의 모든 문자열 값에 재귀적으로 외국어 필터를 적용한다."""
    if isinstance(data, str):
        return _strip_foreign_chars(data)
    if isinstance(data, list):
        return [_strip_foreign_in_dict(item) for item in data]
    if isinstance(data, dict):
        return {k: _strip_foreign_in_dict(v) for k, v in data.items()}
    return data


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
2. 커밋 히스토리와 코드에서 기술적 판단 진화 패턴을 찾아 problem_solving_cases로 추출하세요.
   - 단순 기능 추가(feat)가 아닌, 기존 방식의 한계로 인해 바꾼 것(refactor/fix/perf)을 우선합니다.
   - 동일 영역을 여러 번 수정한 흔적 = 점진적 개선 = 사례 후보
   - 의존성 변경이나 아키텍처 개편 = 기술 선택 결정 = 사례 후보
   - "이전 방식 한계 → 대안 선택 이유 → 결과"가 드러나야 합니다.
   - title은 "X를 구현했다"가 아닌 "A 방식의 한계를 B로 해결" 형식으로 작성하세요.
   - decision_reason은 반드시 채우세요 — 왜 다른 선택이 아닌 이것을 했는가.
3. 코드에서 실제 확인된 정보만 사용하세요 (추측 금지)
[언어 규칙] 모든 텍스트 값은 반드시 한국어로 작성하세요.
일본어(히라가나·가타카나·한자), 중국어 간체·번체 문자는 절대 사용하지 마세요.
기술명·라이브러리명 등 고유명사는 영문 그대로 사용하세요.
반드시 JSON 객체만 반환하세요. 마크다운 코드블록 사용 금지."""

_JD_MATCH_SYSTEM = """당신은 개발자 채용 전문가입니다.
주어진 채용 공고(JD)를 분석하고, 포트폴리오와 비교하여:
1. 핵심 키워드 추출
2. 일치율 분석 (%)
3. 강조할 경험 추천
4. 보완할 내용 제안
을 구체적으로 알려주세요."""

# Sequential budget-forcing 리파인 프롬프트 (s1-style).
# 범용 LLM 에서는 reasoning 토큰 주입이 불가능하므로,
# "다시 점검하라" 는 명시적 지시로 동등한 효과를 낸다.
_REFINE_SIGNAL = """<wait_signal>
잠깐. 최종본을 내놓기 전에 다시 점검한다.
- 리뷰어가 지적한 issues 와 missing_points 를 하나씩 훑어본다.
- evidence 에 있지만 초안에서 빠진 맥락·결과가 있는지 확인한다.
- 같은 표현 반복, 약한 동사("담당했습니다", "진행했습니다"), 추상어 단독 사용이 있으면 고친다.
- 출력 계약(bullet 수, 문장 수, 섹션 순서) 을 다시 센다.
- 제품 슬로건·마케팅 문구("올인원", "혁신적", "~을 위한 도구")가 섞이지 않았는지 본다.
</wait_signal>

<revision_rules>
- evidence 밖 사실은 절대 추가하지 않는다.
- 리뷰의 revision_instructions 를 모두 반영한다.
- {validation_feedback}
</revision_rules>

개선된 최종본만 출력한다. 사고 과정·해설은 출력하지 않는다."""


_INTAKE_SYSTEM = """당신은 개발자 포트폴리오 작성 도우미입니다.
사용자가 자유롭게 적은 프로젝트 설명을 읽고, 포트폴리오 작성에 적합한 구조화 초안을 JSON으로 정리하세요.
사실을 임의로 과장하지 말고, 불명확한 값은 빈 문자열이나 null로 남겨두세요.
다만 서술 안에 암시된 역할 범위, 기능 단위 작업, 배포/운영/성능/안정성 신호는 최대한 구조화해서 추출하세요.
반드시 JSON 객체만 반환하세요. 마크다운 코드블록은 사용하지 마세요."""

# ---------------------------------------------------------------------------
# 후처리 유틸리티
# ---------------------------------------------------------------------------


def _strip_preamble(text: str) -> str:
    """AI 응답에서 불필요한 전문구·복수 버전·가이드 설명·외국어를 제거한다."""
    text = text.strip()
    # "네, 알겠습니다." / "안녕하세요." 등 인사 첫 줄 제거
    text = re.sub(r"^(네[,.]?\s*알겠습니다[.!]?|안녕하세요[.!]?)[^\n]*\n+", "", text)
    # "### Version 1 (...)" 형태가 있으면 첫 번째 버전 본문만 추출
    version_match = re.search(
        r"###?\s*\*{0,2}Version\s*1[^#\n]*\*{0,2}\n+(.*?)(?=###?\s*\*{0,2}Version\s*2|\Z)",
        text,
        re.DOTALL,
    )
    if version_match:
        text = version_match.group(1).strip()
    # "---\n**[작성 가이드]**" 이후 내용 제거
    text = re.sub(
        r"\n*-{3,}\s*\n\*{0,2}\[?작성\s*가이드\]?\*{0,2}.*$", "", text, flags=re.DOTALL
    )
    # 일본어·중국어 문자 제거 (언어 지시를 무시하는 모델 대응)
    return _strip_foreign_chars(text.strip())


def _sentence_count(text: str) -> int:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return 0
    parts = [
        part.strip()
        for part in re.split(r"(?<=[.!?。！？])\s+", normalized)
        if part.strip()
    ]
    if len(parts) > 1:
        return len(parts)
    line_parts = [line.strip() for line in text.splitlines() if line.strip()]
    return len(line_parts) if line_parts else 0


def _extract_bullet_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if re.match(r"^\s*(?:[-*•]|\d+\.)\s+", line)
    ]


# ---------------------------------------------------------------------------
# AI 서비스 클래스
# ---------------------------------------------------------------------------

_MAX_RETRIES = 2
# Rate limit 재시도는 RPM 리셋 주기(60초)에 맞춰야 의미가 있음
# 짧은 간격 재시도는 quota만 낭비
_RETRY_DELAY = 2.0  # 초 (일반 오류용)
_RATE_LIMIT_RETRY_DELAY = 65.0  # 초 (rate limit 전용 — RPM 윈도우 넘김)
_AI_LOG_MAX_ENTRIES = 500
_AI_LOG_PREVIEW_CHARS = 400


def _write_ai_log(
    *,
    provider: str,
    model: str,
    messages: list[dict],
    response: str,
    duration_ms: int,
    ok: bool,
    error: str | None = None,
) -> None:
    try:
        from datetime import datetime, timezone
        from devfolio.core.storage import AI_LOG_FILE, DEVFOLIO_DATA_DIR

        DEVFOLIO_DATA_DIR.mkdir(parents=True, exist_ok=True)

        system_msg = next(
            (m.get("content", "") for m in messages if m.get("role") == "system"), ""
        )
        user_msg = next(
            (m.get("content", "") for m in messages if m.get("role") == "user"), ""
        )

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "model": model,
            "op": "call",
            "prompt_chars": sum(len(m.get("content", "")) for m in messages),
            "response_chars": len(response),
            "duration_ms": duration_ms,
            "ok": ok,
            "error": error,
            "system_preview": system_msg[:_AI_LOG_PREVIEW_CHARS],
            "user_preview": user_msg[:_AI_LOG_PREVIEW_CHARS],
            "response_preview": response[:_AI_LOG_PREVIEW_CHARS],
        }

        existing: list[str] = []
        if AI_LOG_FILE.exists():
            existing = AI_LOG_FILE.read_text(encoding="utf-8").splitlines()

        existing.append(json.dumps(entry, ensure_ascii=False))
        if len(existing) > _AI_LOG_MAX_ENTRIES:
            existing = existing[-_AI_LOG_MAX_ENTRIES:]

        AI_LOG_FILE.write_text("\n".join(existing) + "\n", encoding="utf-8")
    except Exception:
        pass


# API 키 없이 사용 가능한 기본 내장 provider (pollinations.ai)
_POLLINATIONS_BASE_URL = "https://text.pollinations.ai/openai"
_POLLINATIONS_BUILTIN: "AIProviderConfig | None" = None  # lazy init (순환 참조 방지)


def _builtin_provider() -> "AIProviderConfig":
    global _POLLINATIONS_BUILTIN
    if _POLLINATIONS_BUILTIN is None:
        _POLLINATIONS_BUILTIN = AIProviderConfig(
            name="pollinations",
            model="openai-fast",
            key_stored=False,
            base_url=_POLLINATIONS_BASE_URL,
        )
    return _POLLINATIONS_BUILTIN


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
    "gemini": (
        "gemini-3.1-flash-lite-preview",  # 무료 (preview, 한도 미공개)
        "gemini-3-flash-preview",  # 무료 (preview, 한도 미공개)
        "gemini-2.5-flash-lite",  # 무료 stable 15 RPM / 1000 RPD
        "gemini-2.5-flash",  # 무료 stable 10 RPM / 250 RPD
        "gemini-2.5-pro",  # 무료 stable 5 RPM / 100 RPD
        "gemini-1.5-flash",  # 유료
        "gemini-1.5-pro",  # 유료
    ),
    # 무료 한도: 14,400 req/일 (출처: console.groq.com/docs/rate-limits)
    "groq": (
        "llama-3.3-70b-versatile",  # 무료, 고성능
        "llama-3.1-8b-instant",  # 무료, 초고속
        "gemma2-9b-it",  # 무료
        "deepseek-r1-distill-llama-70b",  # 무료, 추론
    ),
    # :free 태그 모델은 무료 (출처: openrouter.ai/models?q=free)
    "openrouter": (
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemma-3-27b-it:free",
        "deepseek/deepseek-r1:free",
        "microsoft/phi-4:free",
        "qwen/qwen3-235b-a22b:free",
    ),
    # API 키 불필요 — pollinations.ai 기본 내장 (출처: text.pollinations.ai/models)
    "pollinations": (
        "openai-fast",  # GPT-OSS 20B, Anonymous 접근 가능
    ),
}


@dataclass(frozen=True)
class GenerationModelResolution:
    # frozen=True: 생성 후 필드 변경 불가(불변 객체). Java의 record에 가까움.
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


def resolve_generation_model(
    provider_name: str, model_name: str
) -> GenerationModelResolution:
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
        warning = (
            f"저장된 모델 {display_model} 대신 생성 시 {generation_model}를 사용합니다."
        )
    elif requested_generation and generation_model != display_model:
        status = "fallback"
        warning = (
            f"저장된 모델 {display_model}은 생성 시 {generation_model}로 해석됩니다."
        )
    elif (
        display_model
        and display_model not in safe_models
        and requested_generation not in safe_models
    ):
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
    one_line_summary: str = ""
    summary: str = ""
    problem: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    audience_value: list[str] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)
    overview: dict[str, Any] = Field(default_factory=dict)
    user_flow: list[dict[str, Any]] = Field(default_factory=list)
    tech_stack_detail: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    architecture: dict[str, Any] = Field(default_factory=dict)
    features: list[dict[str, str]] = Field(default_factory=list)
    problem_solving_cases: list[dict[str, Any]] = Field(default_factory=list)
    performance_security_operations: dict[str, list[str]] = Field(default_factory=dict)
    detailed_results: dict[str, Any] = Field(default_factory=dict)
    retrospective: dict[str, list[str]] = Field(default_factory=dict)
    assets: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    tasks: list[EvidenceTask] = Field(default_factory=list)
    focus_task: Optional[EvidenceTask] = None
    raw_text: str = ""


class ReviewResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    passed: bool = Field(
        alias="pass"
    )  # JSON 키 "pass"는 Python 예약어라 passed로 매핑(alias 사용).
    scores: dict[str, int] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ReviewedCandidate:
    draft: str
    review: ReviewResult
    score: int
    is_valid: bool
    sample_index: int


@dataclass(frozen=True)
class ReasoningPlan:
    """generate_with_review 실행 계획.

    strategy:
      - "single": 1회 생성
      - "best_of_n": sample_count 개 parallel draft → 최고 점수 반환
      - "s1_refine": sequential budget forcing (draft → refine×N, early stop)
      - "hybrid": sample_count 개 parallel draft → 각각 1회 refine → 최고 점수
    """

    strategy: str
    sample_count: int
    refinement_budget: int
    patience: int


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
            # 설정된 provider가 없으면 API 키 불필요한 pollinations 기본 사용
            logger.info("AI provider 미설정 — 기본 내장 provider(pollinations) 사용")
            return _builtin_provider()
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
            "groq": f"groq/{model_name}",
            "openrouter": f"openrouter/{model_name}",
            # pollinations: OpenAI-compatible endpoint → openai/ 프리픽스, base_url로 라우팅
            "pollinations": f"openai/{model_name}",
        }
        return mapping.get(provider_name, model_name)

    def _model_string(self, provider: AIProviderConfig) -> str:
        """litellm 모델 문자열 반환."""
        resolution = resolve_generation_model(provider.name, provider.model)
        model_name = resolution.generation_model or normalize_provider_model_name(
            provider.name, provider.model
        )
        return self._provider_model_string(provider.name, model_name)

    def _runtime_model_candidates(self, provider: AIProviderConfig) -> list[str]:
        resolution = resolve_generation_model(provider.name, provider.model)
        candidates = list(resolution.candidate_models)
        if not candidates and resolution.generation_model:
            candidates = [resolution.generation_model]
        return candidates

    def _set_env_key(self, provider: AIProviderConfig) -> None:
        """API 키를 환경 변수에 설정 (litellm이 읽도록)."""
        if provider.name in ("ollama", "pollinations"):
            # 키 불필요 — litellm이 base_url 있을 때 dummy 키 허용
            os.environ.setdefault("OPENAI_API_KEY", "pollinations-free")
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
        json_mode: bool = False,
    ) -> str:
        """system/user 2턴 호출 호환용 래퍼."""
        return self._call_messages(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            provider_name=provider_name,
            json_mode=json_mode,
        )

    @staticmethod
    def _language_instruction(lang: str) -> str:
        mapping = {
            "ko": "한국어로만 작성하세요. 일본어(히라가나/가타카나/한자)·중국어 문자는 절대 사용 금지. 기술명·라이브러리명 등 고유명사는 영문 허용.",
            "en": "영어로 작성하세요.",
            "both": "한국어와 영어를 함께 제공합니다. 먼저 한국어, 다음에 영어를 작성하세요.",
        }
        return mapping.get(lang, mapping["ko"])

    @staticmethod
    def _extract_json(raw: str) -> dict:
        cleaned = raw.strip()

        def _try_parse(text: str) -> dict | None:
            try:
                payload = json.loads(text.strip())
                return payload if isinstance(payload, dict) else None
            except json.JSONDecodeError:
                return None

        # 1. 코드 펜스 내부 추출
        for fenced in re.finditer(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL):
            result = _try_parse(fenced.group(1))
            if result is not None:
                return result

        # 2. 직접 파싱
        result = _try_parse(cleaned)
        if result is not None:
            return result

        # 3. 응답 내 첫 번째 {...} 블록 추출 (모델이 앞뒤에 텍스트를 붙인 경우)
        brace_match = re.search(r"\{[\s\S]*\}", cleaned)
        if brace_match:
            result = _try_parse(brace_match.group(0))
            if result is not None:
                return result

        raise DevfolioAIError(
            "AI가 구조화 초안을 올바른 JSON으로 반환하지 않았습니다.",
            hint="다시 시도하거나 모델 응답 형식을 점검하세요.",
        )

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
            one_line_summary=draft.one_line_summary,
            summary=draft.summary,
            links=draft.links,
            overview=draft.overview,
            user_flow=draft.user_flow,
            tech_stack_detail=draft.tech_stack_detail,
            architecture=draft.architecture,
            features=draft.features,
            problem_solving_cases=draft.problem_solving_cases,
            performance_security_operations=draft.performance_security_operations,
            results=draft.results,
            retrospective=draft.retrospective,
            assets=draft.assets,
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
        return [
            fragment.strip() for fragment in fragments if re.search(r"\d", fragment)
        ]

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
        cleaned = [k.strip() for k in keywords if k and k.strip()]
        if not cleaned:
            return "- (지정 없음: evidence 에서 자연스럽게 드러나는 축을 선택한다)"
        return "\n".join(f"- {keyword}" for keyword in cleaned)

    def _call_messages(
        self,
        messages: list[dict[str, str]],
        provider_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """litellm 호출 (메시지 배열 직접 사용).

        messages는 OpenAI 스타일 Chat API 포맷과 동일한 구조다:
          [{"role": "system"|"user"|"assistant", "content": "..."}]
        """
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
            "messages": messages
        }  # kwargs는 litellm.completion(**kwargs)로 “옵션 맵”처럼 전달됨.
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        # JSON 구조화 응답이 필요한 호출에서만 json_object 요청
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if provider.base_url:
            kwargs["api_base"] = provider.base_url

        last_error: Exception = RuntimeError("알 수 없는 오류")
        t_start = time.monotonic()
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
                    t_start = time.monotonic()
                    response = litellm.completion(**kwargs)
                    t_end = time.monotonic()
                    content = response.choices[0].message.content or ""
                    _write_ai_log(
                        provider=provider.name,
                        model=kwargs["model"],
                        messages=messages,
                        response=content,
                        duration_ms=int((t_end - t_start) * 1000),
                        ok=True,
                    )
                    return content
                except Exception as e:
                    err_class = type(e).__name__
                    err_str = str(e)
                    if (
                        "AuthenticationError" in err_class
                        or "Unauthorized" in err_class
                    ):
                        raise DevfolioAIAuthError(provider.name) from e
                    if "NotFoundError" in err_class or (
                        '"code": 404' in err_str and "NOT_FOUND" in err_str
                    ):
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
                    _write_ai_log(
                        provider=provider.name,
                        model=kwargs.get("model", "unknown"),
                        messages=messages,
                        response="",
                        duration_ms=int((time.monotonic() - t_start) * 1000),
                        ok=False,
                        error=str(e),
                    )
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
            one_line_summary=project.one_line_summary,
            summary=project.summary,
            problem=[item.problem for item in project.tasks if item.problem],
            actions=[item.solution for item in project.tasks if item.solution],
            results=results,
            metrics=[
                metric for item in results for metric in self._extract_metrics(item)
            ],
            constraints=[],
            tech_stack=project.tech_stack,
            tags=project.tags,
            audience_value=self._derive_audience_value(results),
            links=project.links.model_dump(),
            overview=project.overview.model_dump(),
            user_flow=[step.model_dump() for step in project.user_flow],
            tech_stack_detail=project.tech_stack_detail.model_dump(),
            architecture=project.architecture.model_dump(),
            features=[feature.model_dump() for feature in project.features],
            problem_solving_cases=[
                case.model_dump() for case in project.problem_solving_cases
            ],
            performance_security_operations=project.performance_security_operations.model_dump(),
            detailed_results=project.results.model_dump(),
            retrospective=project.retrospective.model_dump(),
            assets=project.assets.model_dump(),
            tasks=evidence_tasks,
            raw_text=raw_text,
        )

    def _intake_prompt_guide(self) -> str:
        return "\n".join(
            [
                "[추출 우선순위]",
                "- role, organization, team_size를 가능한 범위에서 추출하세요.",
                "- background, problem, goals, target_users를 우선적으로 구조화하세요.",
                "- user_flow는 사용자가 실제로 거치는 단계 순서대로 정리하세요.",
                "- features는 사용자 가치와 구현 포인트가 같이 보이도록 정리하세요.",
                "- problem_solving_cases는 문제 상황, 원인, 행동, 판단 이유, 결과 순서가 드러나도록 작성하세요.",
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
        # 빈 필드를 제거해 프롬프트 신호 대 잡음비를 높인다.
        evidence_payload = _prune_empty(evidence.model_dump(exclude_none=True))
        evidence_json = json.dumps(
            evidence_payload,
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
        evidence_payload = _prune_empty(evidence.model_dump(exclude_none=True))
        evidence_json = json.dumps(
            evidence_payload,
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
            json_mode=True,
        )
        return ReviewResult.model_validate(self._extract_json(raw))

    _MOTIVATION_BANNED_PHRASES: tuple[str, ...] = (
        "올인원",
        "지역 첫 번째",
        "혁신적",
        "을 위한 도구",
        "를 위한 도구",
        "을 위해 만들어진",
        "를 위해 만들어진",
    )

    def _validate_generated_output(self, mode: str, text: str) -> bool:
        if mode == "resume_bullets":
            return 4 <= len(_extract_bullet_lines(text)) <= 6
        if mode == "project_summary":
            sentences = _sentence_count(text)
            return 5 <= sentences <= 7
        if mode == "project_motivation":
            sentences = _sentence_count(text)
            if not (3 <= sentences <= 5):
                return False
            if any(banned in text for banned in self._MOTIVATION_BANNED_PHRASES):
                return False
            if text.lstrip().startswith(("##", "- ", "* ")):
                return False
            return True
        if mode == "project_case_study":
            required_sections = (
                "## 프로젝트 개요",
                "## 문제 정의",
                "## 사용자 흐름",
                "## 기술 스택 및 선정 이유",
                "## 아키텍처",
                "## 핵심 기능",
                "## 문제 해결 사례",
                "## 결과 및 성과",
                "## 회고",
            )
            return all(section in text for section in required_sections)
        return bool(text.strip())

    def _format_validation_feedback(self, mode: str) -> str:
        if mode == "resume_bullets":
            return "반드시 '- '로 시작하는 bullet 4~6개를 작성하고, 각 bullet에 행동·기술/맥락·결과를 모두 포함하며 너무 짧게 끝내지 마세요."
        if mode == "project_summary":
            return "반드시 5~7문장으로 작성하고, 책임 범위·문제 맥락·핵심 구현·기술 선택 이유·결과를 모두 포함하세요."
        if mode == "project_motivation":
            return (
                "반드시 3~5문장 단일 문단으로 작성하고, 제품 소개가 아닌 동기·문제 진단을 담으세요. "
                "'~을 위한 도구', '올인원', '혁신적', '지역 첫 번째' 같은 슬로건성 표현은 금지합니다."
            )
        if mode == "project_case_study":
            return "반드시 Markdown 섹션을 유지하고, 프로젝트 개요·문제 정의·사용자 흐름·기술 스택 및 선정 이유·아키텍처·핵심 기능·문제 해결 사례·결과 및 성과·회고를 모두 포함하세요."
        return "출력 계약을 정확히 지켜 다시 작성하세요."

    def _resolve_reasoning_plan(self, samples: Optional[int] = None) -> ReasoningPlan:
        configured_strategy = self.config.reasoning.strategy or "single"
        configured_samples = self.config.reasoning.samples or 1
        sample_count = samples if samples is not None else configured_samples
        sample_count = max(1, min(sample_count, 5))

        refinement_budget = max(0, min(self.config.reasoning.refinement_budget or 0, 4))
        patience = max(1, min(self.config.reasoning.early_stop_patience or 2, 4))

        strategy = configured_strategy
        if strategy == "s1_refine":
            if refinement_budget == 0:
                strategy = "single"
            sample_count = 1
        elif strategy == "hybrid":
            if sample_count < 2 and refinement_budget == 0:
                strategy = "single"
            elif refinement_budget == 0:
                strategy = "best_of_n"
        elif sample_count > 1:
            strategy = "best_of_n"
        elif strategy == "best_of_n" and sample_count < 2:
            strategy = "single"

        return ReasoningPlan(
            strategy=strategy,
            sample_count=sample_count,
            refinement_budget=refinement_budget,
            patience=patience,
        )

    def _review_provider_name(self, provider_name: Optional[str]) -> Optional[str]:
        judge_provider = (self.config.reasoning.judge_provider or "").strip()
        return judge_provider or provider_name

    @staticmethod
    def _review_score(review: ReviewResult, is_valid: bool) -> int:
        weights = {
            "factuality": 5,
            "specificity": 3,
            "result_orientation": 3,
            "hiring_relevance": 2,
            "redundancy": 1,
            "output_contract": 4,
            "naturalness": 3,
        }
        weighted = sum(
            review.scores.get(key, 0) * weight for key, weight in weights.items()
        )
        return weighted + (12 if review.passed else 0) + (8 if is_valid else 0)

    def _generate_reviewed_candidate(
        self,
        *,
        prompt_pack: PromptPack,
        evidence: PortfolioEvidence,
        profile: GenerationProfile,
        provider_name: Optional[str],
        writer_messages: list[dict[str, str]],
        sample_index: int,
    ) -> ReviewedCandidate:
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
            self._review_provider_name(provider_name),
        )
        is_valid = self._validate_generated_output(profile.mode, draft)
        return ReviewedCandidate(
            draft=draft,
            review=review,
            score=self._review_score(review, is_valid),
            is_valid=is_valid,
            sample_index=sample_index,
        )

    @staticmethod
    def _candidate_sort_key(candidate: ReviewedCandidate) -> tuple:
        return (
            candidate.score,
            candidate.review.passed,
            candidate.is_valid,
            -len(candidate.review.issues),
        )

    def _is_better(
        self, new: ReviewedCandidate, best: Optional[ReviewedCandidate]
    ) -> bool:
        if best is None:
            return True
        return self._candidate_sort_key(new) > self._candidate_sort_key(best)

    def _refine_candidate(
        self,
        *,
        prompt_pack: PromptPack,
        evidence: PortfolioEvidence,
        profile: GenerationProfile,
        provider_name: Optional[str],
        user_prompt: str,
        previous: ReviewedCandidate,
        sample_index: int,
    ) -> ReviewedCandidate:
        """리뷰 피드백 + wait_signal 을 주입해 단일 draft 를 sequential 하게 개선한다."""
        review_payload = json.dumps(
            previous.review.model_dump(by_alias=True),
            ensure_ascii=False,
            indent=2,
        )
        refine_signal = _REFINE_SIGNAL.format(
            validation_feedback=self._format_validation_feedback(profile.mode),
        )
        revised_user_prompt = (
            f"{user_prompt}\n\n"
            f"<previous_draft>\n{previous.draft}\n</previous_draft>\n\n"
            f"<review_result>\n{review_payload}\n</review_result>\n\n"
            f"{refine_signal}"
        )
        draft = _strip_preamble(
            self._call_messages(
                [
                    {"role": "system", "content": prompt_pack.system_prompt},
                    {"role": "user", "content": revised_user_prompt},
                ],
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
            self._review_provider_name(provider_name),
        )
        is_valid = self._validate_generated_output(profile.mode, draft)
        return ReviewedCandidate(
            draft=draft,
            review=review,
            score=self._review_score(review, is_valid),
            is_valid=is_valid,
            sample_index=sample_index,
        )

    def _run_best_of_n(
        self,
        *,
        prompt_pack: PromptPack,
        evidence: PortfolioEvidence,
        profile: GenerationProfile,
        provider_name: Optional[str],
        writer_messages: list[dict[str, str]],
        sample_count: int,
    ) -> ReviewedCandidate:
        best: Optional[ReviewedCandidate] = None
        for sample_index in range(1, sample_count + 1):
            candidate = self._generate_reviewed_candidate(
                prompt_pack=prompt_pack,
                evidence=evidence,
                profile=profile,
                provider_name=provider_name,
                writer_messages=writer_messages,
                sample_index=sample_index,
            )
            if self._is_better(candidate, best):
                best = candidate
        if best is None:
            raise DevfolioAIError("AI 후보 초안을 생성하지 못했습니다.")
        return best

    def _run_s1_refine(
        self,
        *,
        prompt_pack: PromptPack,
        evidence: PortfolioEvidence,
        profile: GenerationProfile,
        provider_name: Optional[str],
        writer_messages: list[dict[str, str]],
        user_prompt: str,
        refinement_budget: int,
        patience: int,
    ) -> ReviewedCandidate:
        """Sequential budget forcing: draft → refine×N, 점수 정체 시 조기 종료."""
        current = self._generate_reviewed_candidate(
            prompt_pack=prompt_pack,
            evidence=evidence,
            profile=profile,
            provider_name=provider_name,
            writer_messages=writer_messages,
            sample_index=1,
        )
        best = current
        stagnant = 0

        if current.review.passed and current.is_valid:
            return current

        for step in range(1, refinement_budget + 1):
            refined = self._refine_candidate(
                prompt_pack=prompt_pack,
                evidence=evidence,
                profile=profile,
                provider_name=provider_name,
                user_prompt=user_prompt,
                previous=current,
                sample_index=step + 1,
            )
            if self._is_better(refined, best):
                best = refined
                stagnant = 0
            else:
                stagnant += 1

            current = refined

            if refined.review.passed and refined.is_valid:
                return refined
            if stagnant >= patience:
                break

        return best

    def _run_hybrid(
        self,
        *,
        prompt_pack: PromptPack,
        evidence: PortfolioEvidence,
        profile: GenerationProfile,
        provider_name: Optional[str],
        writer_messages: list[dict[str, str]],
        user_prompt: str,
        sample_count: int,
        refinement_budget: int,
    ) -> ReviewedCandidate:
        """Parallel sampling + 각 sample 에 sequential refine 1회."""
        refine_steps = max(1, min(refinement_budget, 2))
        best: Optional[ReviewedCandidate] = None
        for sample_index in range(1, sample_count + 1):
            candidate = self._generate_reviewed_candidate(
                prompt_pack=prompt_pack,
                evidence=evidence,
                profile=profile,
                provider_name=provider_name,
                writer_messages=writer_messages,
                sample_index=sample_index,
            )
            if not (candidate.review.passed and candidate.is_valid):
                for step in range(1, refine_steps + 1):
                    refined = self._refine_candidate(
                        prompt_pack=prompt_pack,
                        evidence=evidence,
                        profile=profile,
                        provider_name=provider_name,
                        user_prompt=user_prompt,
                        previous=candidate,
                        sample_index=sample_index * 10 + step,
                    )
                    if self._is_better(refined, candidate):
                        candidate = refined
                    if refined.review.passed and refined.is_valid:
                        break
            if self._is_better(candidate, best):
                best = candidate
        if best is None:
            raise DevfolioAIError("AI 후보 초안을 생성하지 못했습니다.")
        return best

    def generate_with_review(
        self,
        *,
        evidence: PortfolioEvidence,
        profile: GenerationProfile,
        provider_name: Optional[str] = None,
        samples: Optional[int] = None,
    ) -> tuple[str, ReviewResult]:
        prompt_pack = self._prompt_pack("ko")
        user_prompt = self._render_generation_prompt(prompt_pack, evidence, profile)
        writer_messages = [
            {"role": "system", "content": prompt_pack.system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        plan = self._resolve_reasoning_plan(samples)

        if plan.strategy == "s1_refine":
            best_candidate = self._run_s1_refine(
                prompt_pack=prompt_pack,
                evidence=evidence,
                profile=profile,
                provider_name=provider_name,
                writer_messages=writer_messages,
                user_prompt=user_prompt,
                refinement_budget=plan.refinement_budget,
                patience=plan.patience,
            )
        elif plan.strategy == "hybrid":
            best_candidate = self._run_hybrid(
                prompt_pack=prompt_pack,
                evidence=evidence,
                profile=profile,
                provider_name=provider_name,
                writer_messages=writer_messages,
                user_prompt=user_prompt,
                sample_count=plan.sample_count,
                refinement_budget=plan.refinement_budget,
            )
        elif plan.strategy == "best_of_n":
            best_candidate = self._run_best_of_n(
                prompt_pack=prompt_pack,
                evidence=evidence,
                profile=profile,
                provider_name=provider_name,
                writer_messages=writer_messages,
                sample_count=plan.sample_count,
            )
        else:
            best_candidate = self._generate_reviewed_candidate(
                prompt_pack=prompt_pack,
                evidence=evidence,
                profile=profile,
                provider_name=provider_name,
                writer_messages=writer_messages,
                sample_index=1,
            )

        if best_candidate is None:
            raise DevfolioAIError("AI 후보 초안을 생성하지 못했습니다.")

        if best_candidate.review.passed and best_candidate.is_valid:
            return best_candidate.draft, best_candidate.review

        # 마지막 안전망: 최상 후보가 리뷰/검증을 모두 통과하지 못한 경우
        # review 호출 없이 단일 revision 만 시도해 출력 계약을 맞춘다.
        # (s1_refine/hybrid 는 내부에서 이미 refine 을 충분히 돌렸으므로 추가 review 비용은 불필요.)
        revision_payload = json.dumps(
            best_candidate.review.model_dump(by_alias=True),
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
        return revised, best_candidate.review

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def generate_task_text(
        self,
        task: Task,
        lang: str = "ko",
        provider_name: Optional[str] = None,
        force_refresh: bool = False,
        samples: Optional[int] = None,
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
            samples=samples,
        )
        return result

    def generate_project_summary(
        self,
        project: Project,
        lang: str = "ko",
        provider_name: Optional[str] = None,
        samples: Optional[int] = None,
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
            samples=samples,
        )
        return result

    def generate_project_case_study(
        self,
        project: Project,
        lang: str = "ko",
        provider_name: Optional[str] = None,
        samples: Optional[int] = None,
    ) -> str:
        """프로젝트 전체를 케이스 스터디형 Markdown으로 생성한다."""
        evidence = self.build_evidence(project=project)
        profile = GenerationProfile(
            mode="project_case_study",
            language=lang,
            max_tokens=4200,
        )
        result, _ = self.generate_with_review(
            evidence=evidence,
            profile=profile,
            provider_name=provider_name,
            samples=samples,
        )
        return result

    def generate_project_motivation(
        self,
        project: Project,
        lang: str = "ko",
        provider_name: Optional[str] = None,
        samples: Optional[int] = None,
    ) -> tuple[str, ReviewResult]:
        """프로젝트 동기·문제 정의 문단을 생성한다.

        overview.background 가 비어 있거나 판박이 문구가 들어가 있을 때
        evidence 를 근거로 3~5문장 자연 문단을 만든다.
        """
        evidence = self.build_evidence(project=project)
        profile = GenerationProfile(
            mode="project_motivation",
            language=lang,
            temperature=0.4,
            max_tokens=900,
            priority_keywords=tuple(project.tags)
            if project.tags
            else (
                "문제 맥락",
                "기존 방식의 한계",
                "만든 이유",
            ),
        )
        return self.generate_with_review(
            evidence=evidence,
            profile=profile,
            provider_name=provider_name,
            samples=samples,
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
        prompt = f"""<task>
다음 자유 텍스트를 읽고 개발자 포트폴리오용 프로젝트 초안 JSON으로 구조화해주세요.
</task>

<instructions>
- 사실로 보이지 않는 정보는 추측하지 말고 빈 문자열 또는 null로 두세요.
- type은 company, side, course 중 하나만 사용하세요.
- status는 done, in_progress, planned 중 하나만 사용하세요.
- period는 {{\"start\": \"YYYY-MM 또는 null\", \"end\": \"YYYY-MM 또는 null\"}} 형식으로 작성하세요.
- tech_stack, tags, tasks, tech_used, keywords는 항상 배열로 반환하세요.
- target_users, goals, non_goals, performance, security, operations, qualitative, what_went_well, what_was_hard, what_i_learned, next_steps도 항상 배열로 반환하세요.
- tasks 각 항목은 name, period, problem, solution, result, tech_used, keywords, ai_generated_text 필드를 모두 포함하세요.
- user_flow, features, problem_solving_cases, screenshots, diagrams는 비어 있더라도 배열 필드를 유지하세요.
- links, overview, tech_stack_detail, architecture, performance_security_operations, results, retrospective, assets는 항상 객체로 반환하세요.
- team_size를 알 수 없으면 1을 사용하세요.
- one_line_summary는 프로젝트의 가치가 한 문장으로 드러나도록 작성하세요.
- summary는 과장된 마케팅 문구보다 프로젝트 성격과 역할이 드러나는 3~5문장 수준의 초안으로 작성하세요.
- 자유 텍스트에 운영, 배포, 성능, 안정성, 자동화 관련 단서가 있으면 적절한 task나 keywords에 반영하세요.
- 링크가 명시되면 links에 채우고, 기술 선택 이유가 드러나면 tech_stack_detail에 reason까지 채우세요.
- 설계 판단, 트러블슈팅, 기술 선택 이유가 보이면 problem_solving_cases로 분리하세요.
  추출 패턴: "처음엔 A로 했지만", "B 방식으로는 한계가 있어서", "C를 선택한 이유는",
  "성능/안정성 문제가 있어서", "대신/변경/교체/리팩토링" 등의 표현이 단서입니다.
  title은 "X를 구현했다"가 아닌 "A 방식의 한계를 B로 해결" 형식으로 작성하세요.
  decision_reason은 반드시 채우세요 — 왜 다른 선택이 아닌 이것을 했는가.
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
  "one_line_summary": "",
  "summary": "",
  "links": {{
    "github": "",
    "demo": "",
    "docs": "",
    "video": ""
  }},
  "overview": {{
    "background": "",
    "problem": "",
    "target_users": [],
    "goals": [],
    "non_goals": []
  }},
  "user_flow": [
    {{
      "step": 1,
      "title": "",
      "description": ""
    }}
  ],
  "tech_stack_detail": {{
    "frontend": [{{"name": "", "reason": ""}}],
    "backend": [{{"name": "", "reason": ""}}],
    "database": [{{"name": "", "reason": ""}}],
    "infra": [{{"name": "", "reason": ""}}],
    "tools": [{{"name": "", "reason": ""}}]
  }},
  "architecture": {{
    "summary": "",
    "components": [{{"name": "", "role": ""}}],
    "data_model": [{{"entity": "", "fields": [""]}}],
    "api_examples": [{{"method": "GET", "path": "", "purpose": ""}}]
  }},
  "features": [
    {{
      "name": "",
      "user_value": "",
      "implementation": ""
    }}
  ],
  "problem_solving_cases": [
    {{
      "title": "",
      "situation": "",
      "cause": "",
      "action": "",
      "decision_reason": "",
      "result": "",
      "metric": "",
      "tech_used": []
    }}
  ],
  "performance_security_operations": {{
    "performance": [],
    "security": [],
    "operations": []
  }},
  "results": {{
    "quantitative": [
      {{
        "metric_name": "",
        "before": "",
        "after": "",
        "impact": ""
      }}
    ],
    "qualitative": []
  }},
  "retrospective": {{
    "what_went_well": [],
    "what_was_hard": [],
    "what_i_learned": [],
    "next_steps": []
  }},
  "assets": {{
    "screenshots": [
      {{
        "title": "",
        "description": "",
        "path": ""
      }}
    ],
    "diagrams": [
      {{
        "title": "",
        "description": "",
        "path": ""
      }}
    ]
  }},
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

        payload = self._extract_json(
            self._call(_INTAKE_SYSTEM, prompt, provider_name, json_mode=True)
        )
        payload.setdefault("name", "")
        payload.setdefault("type", "company")
        payload.setdefault("status", "done")
        payload.setdefault("organization", "")
        payload.setdefault("period", {"start": None, "end": None})
        payload.setdefault("role", "")
        payload.setdefault("team_size", 1)
        payload.setdefault("tech_stack", [])
        payload.setdefault("one_line_summary", "")
        payload.setdefault("summary", "")
        payload.setdefault("links", {"github": "", "demo": "", "docs": "", "video": ""})
        payload.setdefault(
            "overview",
            {
                "background": "",
                "problem": "",
                "target_users": [],
                "goals": [],
                "non_goals": [],
            },
        )
        payload.setdefault("user_flow", [])
        payload.setdefault(
            "tech_stack_detail",
            {"frontend": [], "backend": [], "database": [], "infra": [], "tools": []},
        )
        payload.setdefault(
            "architecture",
            {"summary": "", "components": [], "data_model": [], "api_examples": []},
        )
        payload.setdefault("features", [])
        payload.setdefault("problem_solving_cases", [])
        payload.setdefault(
            "performance_security_operations",
            {"performance": [], "security": [], "operations": []},
        )
        payload.setdefault("results", {"quantitative": [], "qualitative": []})
        payload.setdefault(
            "retrospective",
            {
                "what_went_well": [],
                "what_was_hard": [],
                "what_i_learned": [],
                "next_steps": [],
            },
        )
        payload.setdefault("assets", {"screenshots": [], "diagrams": []})
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
        samples: Optional[int] = None,
    ) -> str:
        """저장 전 초안 기준 프로젝트 요약을 생성한다."""
        return self.generate_project_summary(
            self._draft_project_to_project(draft),
            lang=lang,
            provider_name=provider_name,
            samples=samples,
        )

    def generate_draft_task_texts(
        self,
        draft: ProjectDraft,
        lang: str = "ko",
        provider_name: Optional[str] = None,
        force_refresh: bool = True,
        samples: Optional[int] = None,
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
                samples=samples,
            )
            updated_tasks.append(
                task.model_copy(update={"ai_generated_text": generated})
            )

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
            f"- 일본어(히라가나/가타카나/한자)·중국어 문자는 절대 사용 금지. 한국어와 영문 고유명사만 허용.\n"
            f"반드시 위 스키마 형태의 JSON 객체만 반환하세요."
        )

        raw = self._call(_CODE_ANALYSIS_SYSTEM, prompt, provider_name, json_mode=True)
        payload = self._extract_json(raw)

        # 필수 키 보장 (AI가 일부 생략할 경우 대비)
        for key in ("project_type", "purpose", "key_features", "problem", "solution", "tech_stack", "summary", "tasks"):
            payload.setdefault(key, [] if key in ("key_features", "tech_stack", "tasks") else "")

        # --- 2차 호출: 커밋 히스토리 기반 문제 해결 사례 추출 ---
        # 별도 호출로 분리해 메인 분석 실패와 독립적으로 처리
        commit_history = project_context.get("commit_history", "")
        payload["problem_solving_cases"] = self._extract_problem_solving_cases(
            commit_history=commit_history,
            readme=project_context.get("readme", ""),
            repo_name=repo_name,
            lang=lang,
            provider_name=provider_name,
        )

        # 언어 지시를 무시한 모델 출력에서 일본어·중국어 문자 물리적 제거
        return _strip_foreign_in_dict(payload)

    def _extract_problem_solving_cases(
        self,
        *,
        commit_history: str,
        readme: str,
        repo_name: str,
        lang: str = "ko",
        provider_name: Optional[str] = None,
    ) -> list[dict]:
        """커밋 히스토리에서 기술적 판단 진화 사례를 추출한다.

        메인 analyze_project_from_code 와 독립적으로 호출되어
        실패 시 빈 리스트를 반환하고 메인 분석 결과를 유지한다.
        """
        if not commit_history:
            return []

        schema = """[
  {
    "title": "'A 방식의 한계를 B로 해결' 형식의 한 줄 제목",
    "situation": "어떤 맥락에서 문제가 드러났는가 (1~2문장)",
    "cause": "기존 방식이 한계에 부딪힌 구체적 원인",
    "action": "어떤 기술적 접근으로 해결했는가",
    "decision_reason": "왜 다른 대안이 아닌 이 방식을 선택했는가 (트레이드오프)",
    "result": "어떤 개선이 있었는가",
    "metric": "수치 지표 또는 빈 문자열",
    "tech_used": ["관련 기술"]
  }
]"""
        readme_snip = readme[:1500] if readme else ""
        lang_instr = self._language_instruction(lang)
        prompt = (
            f"레포지토리: {repo_name}\n\n"
            f"[커밋 히스토리 (최근 순)]\n{commit_history}\n\n"
            + (f"[README 요약]\n{readme_snip}\n\n" if readme_snip else "")
            + f"위 커밋 히스토리에서 기술적 판단이 드러나는 문제 해결 사례 1~3개를 JSON 배열로 추출하세요.\n"
            f"추출 기준:\n"
            f"- 단순 기능 추가(feat)가 아닌, 기존 방식의 한계로 인해 바꾼 것(refactor/fix/perf)을 우선\n"
            f"- 동일 영역 여러 번 수정 = 점진적 개선 = 사례 후보\n"
            f"- 커밋 흐름에서 'A 추가 → A 개선 → A 고도화' 패턴이 보이면 하나의 사례로 묶어 서술\n"
            f"- decision_reason 필드는 반드시 채울 것\n"
            f"- 언어 지시: {lang_instr}\n\n"
            f"[출력 스키마]\n{schema}\n\n"
            f"반드시 JSON 배열만 반환하세요. 다른 텍스트나 마크다운 금지."
        )

        try:
            raw = self._call(_CODE_ANALYSIS_SYSTEM, prompt, provider_name, json_mode=False)
            cleaned = raw.strip()
            # 코드 펜스 제거
            for fenced in re.finditer(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL):
                cleaned = fenced.group(1).strip()
                break
            # 배열 추출
            arr_match = re.search(r"\[[\s\S]*\]", cleaned)
            if arr_match:
                result = json.loads(arr_match.group(0))
                if isinstance(result, list):
                    return [c for c in result if isinstance(c, dict)]
        except Exception as exc:
            logger.warning("문제 해결 사례 추출 실패 (빈 배열로 계속): %s", exc)
        return []

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
