"""정성 효과 주장(qualitative outcome claim) 검증.

수치 가드레일(`metrics.py`)은 숫자를 막지만, "안정성을 향상시켰다"처럼
측정값 없이 효과를 단정하는 문장은 통과시킨다. 이 모듈은 그 빈틈을 막는다.

규칙:
1. 효과 주장을 문장 단위로 찾는다(향상·개선·절감·단축·보장·예방·제거 …).
2. 근거 문장에 같은 대상(object)과 같은 효과 표현이 있거나, 주장의 수치가
   근거의 측정값과 일치할 때만 SUPPORTED 로 본다.
3. 근거가 "측정하지 않았다/기록이 없다"고 명시하면 명시적 UNSUPPORTED 다.
4. 판정 불가·근거 없음은 모두 차단한다(보수적). 차단된 문장은 삭제하고
   목록으로 남겨 사용자가 근거를 보완하게 한다.

이 모듈은 결정론적이며 외부 호출을 하지 않는다. LLM Judge 의 대체가 아니라
저장·보고서 직전의 Hard Gate 다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"

PLACEHOLDER = "[효과 검증 필요]"

# (category, 효과 표현). category 는 근거에서 같은 종류의 효과를 찾을 때 쓴다.
_EFFECT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "cost",
        re.compile(r"(비용|운영비|요금|단가)[^.!?\n]{0,24}(절감|절약|감소|줄|낮|상승)"),
    ),
    ("cost", re.compile(r"(절감|절약)(했다|되었|됐|함|했습니다)")),
    (
        "productivity",
        re.compile(
            r"(생산성|개발 효율|업무 효율|작업 효율)[^.!?\n]{0,24}(향상|개선|증가|높|올)"
        ),
    ),
    (
        "stability",
        re.compile(
            r"(안정성|가용성|신뢰성|고가용성)[^.!?\n]{0,24}(향상|개선|확보|강화|높|보장|달성|갖)"
        ),
    ),
    (
        "maintainability",
        re.compile(
            r"(유지보수성|확장성|가독성|재사용성)[^.!?\n]{0,24}(향상|개선|확보|강화|보장|높)"
        ),
    ),
    (
        "performance",
        re.compile(
            r"(성능|응답 시간|지연|처리 속도|빌드 시간|배포 시간|소요 시간)"
            r"[^.!?\n]{0,24}(향상|개선|최적화|단축|줄|감소|최소화|낮)"
        ),
    ),
    (
        "quality",
        re.compile(
            r"(품질|정합성|무결성|정확도)[^.!?\n]{0,24}(향상|개선|보장|확보|높)"
        ),
    ),
    (
        "incident",
        re.compile(
            r"(장애|오류|에러|버그)[^.!?\n]{0,16}(감소|제거|예방|줄|없앴|해결|0건|방지)"
        ),
    ),
    ("efficiency", re.compile(r"(효율)[^.!?\n]{0,24}(향상|개선|높|올)")),
    (
        "customer",
        re.compile(r"(고객 만족|대응 시간|처리 시간)[^.!?\n]{0,24}(향상|개선|단축|줄)"),
    ),
    ("risk", re.compile(r"(위험|리스크)[^.!?\n]{0,24}(감소|줄|낮|초래)")),
    (
        "reliability",
        re.compile(
            r"(중복 로그인|데이터 유실|데이터 손실)[^.!?\n]{0,20}(방지|막|제거)"
        ),
    ),
    # 대상이 잘리지 않은 일반 효과 서술. 근거에 같은 효과 표현이 있을 때만 인정한다.
    (
        "outcome",
        re.compile(
            r"(향상시켰|개선했다|개선되었|확보했다|최적화했다|절감했다|예방했다|"
            r"단축했다|단축되었|보장했다|높였다|줄였다|감소시켰|감소했|제거했다|"
            r"달성했|초래했|분산시켰|분산했)"
        ),
    ),
)

_CATEGORY_CUE: dict[str, re.Pattern[str]] = {
    "cost": re.compile(r"(절감|절약|감소|줄|낮|상승)"),
    "productivity": re.compile(r"(향상|개선|증가|높|올)"),
    "stability": re.compile(r"(향상|개선|확보|강화|높|보장|달성|갖)"),
    "maintainability": re.compile(r"(향상|개선|확보|강화|보장|높)"),
    "performance": re.compile(r"(향상|개선|최적화|단축|줄|감소|최소화|낮)"),
    "quality": re.compile(r"(향상|개선|보장|확보|높)"),
    "incident": re.compile(r"(감소|제거|예방|줄|없앴|해결|0건|방지)"),
    "efficiency": re.compile(r"(향상|개선|높|올)"),
    "customer": re.compile(r"(향상|개선|단축|줄)"),
    "risk": re.compile(r"(감소|줄|낮|초래)"),
    "reliability": re.compile(r"(방지|막|제거)"),
}

_ANY_CUE = re.compile(
    r"(향상|개선|확보|최적화|절감|절약|예방|단축|보장|달성|감소|제거|방지|"
    r"해결|증가|높였|줄였|초래|없앴|분산)"
)

_NEGATION = re.compile(
    r"(없음|없다|없고|없으며|없는|미측정|미기록|기록되지\s*않|측정되지\s*않|"
    r"확인되지\s*않|자료가\s*없|결과는\s*없|비교가\s*없|않음|않는다)"
)
_MEASUREMENT = re.compile(
    r"(측정|벤치마크|전후|before|after|→|->|퍼센트|%|\d+\s*(?:ms|초|분|시간|건|개|명))",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_SENTENCE = re.compile(r"[^.!?。\n]+[.!?。]?")

# 효과 주장의 대상(object)을 뽑을 때 제외할 일반어·효과어.
_STOP = {
    "시스템",
    "서비스",
    "프로젝트",
    "업무",
    "작업",
    "기능",
    "관련",
    "기반",
    "통해",
    "대한",
    "대비",
    "전체",
    "부분",
    "결과",
    "기록",
    "근거",
    "측정",
    "비교",
    "적용",
    "도입",
    "구축",
    "구현",
    "개발",
    "사용",
    "처리",
    "변경",
    "추가",
    "운영",
    "관리",
    "정도",
    "이상",
    "이번",
    "해당",
    "기존",
    "그리고",
    "하지만",
    "또한",
    "향상",
    "개선",
    "확보",
    "최적화",
    "절감",
    "절약",
    "예방",
    "단축",
    "보장",
    "달성",
    "감소",
    "제거",
    "방지",
    "해결",
    "증가",
    "상승",
    "초래",
    "최소화",
    "강화",
    "높였다",
    "줄였다",
    "했습니다",
    "되었습니다",
    "되었다",
    "시켰다",
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
}

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,}|[가-힣]{2,}")


@dataclass(frozen=True)
class EffectClaim:
    """효과 주장 1건의 판정 결과."""

    sentence: str
    category: str
    status: str
    reason: str
    matched_evidence: str = ""

    @property
    def supported(self) -> bool:
        return self.status == SUPPORTED

    def as_dict(self) -> dict[str, str]:
        return {
            "sentence": self.sentence,
            "category": self.category,
            "status": self.status,
            "reason": self.reason,
            "matched_evidence": self.matched_evidence,
        }


def _sentences(text: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in _SENTENCE.finditer(text or "")
        if match.group(0).strip()
    ]


def _numbers(text: str) -> set[str]:
    return {match.group(0).replace(",", ".") for match in _NUMBER.finditer(text or "")}


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN.findall(text or "")
        if len(token) >= 2 and token.lower() not in _STOP
    }


def classify_effect(sentence: str) -> str | None:
    """문장이 어떤 종류의 효과 주장인지 반환한다(효과 주장이 아니면 None)."""
    for category, pattern in _EFFECT_RULES:
        if pattern.search(sentence or ""):
            return category
    return None


def find_effect_claims(text: str) -> list[str]:
    """텍스트에서 효과 주장 문장만 추출한다."""
    return [sentence for sentence in _sentences(text) if classify_effect(sentence)]


def verify_effect_claim(sentence: str, sources: Iterable[str]) -> EffectClaim | None:
    """효과 주장 1건을 근거와 대조한다. 효과 주장이 아니면 None."""
    category = classify_effect(sentence)
    if category is None:
        return None
    source_list = [str(source) for source in sources if str(source or "").strip()]
    if not source_list:
        return EffectClaim(
            sentence=sentence,
            category=category,
            status=UNSUPPORTED,
            reason="연결된 근거가 없습니다.",
        )

    claim_numbers = _numbers(sentence)
    source_numbers: set[str] = set()
    for source in source_list:
        source_numbers |= _numbers(source)
    missing = sorted(claim_numbers - source_numbers)
    if missing:
        return EffectClaim(
            sentence=sentence,
            category=category,
            status=UNSUPPORTED,
            reason=f"근거에 없는 수치: {', '.join(missing)}",
        )

    claim_tokens = _tokens(sentence)
    cue = _CATEGORY_CUE.get(category, _ANY_CUE)
    candidates: list[tuple[str, bool]] = []
    for source in source_list:
        for block in _sentences(source):
            negated = bool(_NEGATION.search(block))
            shares_object = bool(claim_tokens & _tokens(block))
            measured = bool(claim_numbers) and bool(_MEASUREMENT.search(block))
            if negated or not (shares_object or measured):
                continue
            candidates.append(
                (
                    block,
                    bool(cue.search(block))
                    if category != "outcome"
                    else bool(_ANY_CUE.search(block)),
                )
            )

    if not candidates:
        return EffectClaim(
            sentence=sentence,
            category=category,
            status=UNSUPPORTED,
            reason="근거 문장에서 주장 대상을 확인하지 못했습니다.",
        )

    for block, has_cue in candidates:
        if has_cue:
            return EffectClaim(
                sentence=sentence,
                category=category,
                status=SUPPORTED,
                reason="근거 문장에 동일한 효과 기록이 있습니다.",
                matched_evidence=block[:300],
            )
    for block, _ in candidates:
        if claim_numbers and _MEASUREMENT.search(block):
            return EffectClaim(
                sentence=sentence,
                category=category,
                status=SUPPORTED,
                reason="근거의 측정값과 수치가 일치합니다.",
                matched_evidence=block[:300],
            )
    return EffectClaim(
        sentence=sentence,
        category=category,
        status=UNSUPPORTED,
        reason="효과를 입증하는 측정값이나 기록이 없습니다.",
    )


def gate_text(text: str, sources: Iterable[str]) -> tuple[str, list[dict[str, str]]]:
    """효과 주장을 검증해 근거 없는 문장을 삭제한다.

    반환: (정리된 텍스트, 차단된 주장 목록)
    """
    if not text:
        return text, []
    source_list = list(sources)
    kept: list[str] = []
    removed: list[dict[str, str]] = []
    for sentence in _sentences(text):
        claim = verify_effect_claim(sentence, source_list)
        if claim is not None and not claim.supported:
            removed.append(claim.as_dict())
            continue
        kept.append(sentence)
    return " ".join(kept).strip(), removed


def gate_result(
    result: dict, sources: Iterable[str]
) -> tuple[dict, list[dict[str, str]]]:
    """AI 결과 dict 의 모든 문자열에 효과 주장 게이트를 적용한다."""
    source_list = list(sources)
    removed: list[dict[str, str]] = []

    def walk(value: object, field: str) -> object:
        if isinstance(value, str):
            cleaned, dropped = gate_text(value, source_list)
            removed.extend({**item, "field": field} for item in dropped)
            return cleaned
        if isinstance(value, list):
            return [
                walk(entry, f"{field}[{index}]") for index, entry in enumerate(value)
            ]
        if isinstance(value, dict):
            return {
                key: walk(entry, f"{field}.{key}" if field else str(key))
                for key, entry in value.items()
            }
        return value

    cleaned = {key: walk(value, str(key)) for key, value in (result or {}).items()}
    return cleaned, removed


__all__ = [
    "SUPPORTED",
    "UNSUPPORTED",
    "EffectClaim",
    "classify_effect",
    "find_effect_claims",
    "gate_result",
    "gate_text",
    "verify_effect_claim",
]
