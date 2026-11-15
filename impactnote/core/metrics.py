"""수치 검증 — 근거 없는 정량 성과를 만들지 않기 위한 가드레일.

AI 는 그럴듯한 숫자를 만들어내기 쉽다. 성과노트는 아래 규칙을 강제한다.

1. 숫자+단위(예: `40%`, `3건`, `2시간`)는 "주장"으로 본다.
2. 그 숫자가 원본 기록이나 연결된 근거 텍스트에 없으면 사실로 쓰지 않는다.
3. 근거 없는 숫자는 `[확인 필요]` 로 바꾸고, 별도 목록에 남겨 사용자가 검토하게 한다.
"""

from __future__ import annotations

import re
from typing import Iterable

# 40%, 3.5시간, 12건, 2배 …
# 단위를 함께 본다. 값만 비교하면 "80%" 가 근거의 "80ms" 로 통과한다.
_CLAIM_PATTERN = re.compile(
    r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*"
    r"(개월|분기|퍼센트|밀리초|시간|ms|min|hr|sec|분|초|년|주|일|건|개|회|배|원|명|%|m|h|s)"
)

_UNIT_ALIASES = {
    "퍼센트": "%",
    "%": "%",
    "분": "분",
    "m": "분",
    "min": "분",
    "시간": "시간",
    "h": "시간",
    "hr": "시간",
    "초": "초",
    "s": "초",
    "sec": "초",
    "ms": "ms",
    "밀리초": "ms",
}


def normalize_unit(unit: str) -> str:
    """단위 표기를 비교 가능한 형태로 통일한다(10m ↔ 10분, % ↔ 퍼센트)."""
    return _UNIT_ALIASES.get((unit or "").lower(), (unit or "").lower())


def find_claims(text: str) -> list[dict[str, str]]:
    """텍스트에서 수치 주장을 추출한다."""
    claims: list[dict[str, str]] = []
    for match in _CLAIM_PATTERN.finditer(text or ""):
        claims.append(
            {
                "value": match.group(1).replace(",", "."),
                "unit": match.group(2),
                "normalized_unit": normalize_unit(match.group(2)),
                "raw": match.group(0).strip(),
            }
        )
    return claims


def _measurements(text: str) -> set[tuple[str, str]]:
    """(값, 정규화 단위) 쌍. 근거에 같은 값이라도 단위가 다르면 인정하지 않는다."""
    return {
        (claim["value"], claim["normalized_unit"]) for claim in find_claims(text or "")
    }


def unsupported_claims(text: str, sources: Iterable[str]) -> list[dict[str, str]]:
    """근거 텍스트에 없는 수치 주장만 반환한다(값 + 단위 대조)."""
    source_measurements: set[tuple[str, str]] = set()
    for source in sources:
        source_measurements |= _measurements(source or "")
    return [
        claim
        for claim in find_claims(text)
        if (claim["value"], claim["normalized_unit"]) not in source_measurements
    ]


def sanitize_claims(
    text: str, sources: Iterable[str], *, placeholder: str = "[확인 필요]"
) -> tuple[str, list[dict[str, str]]]:
    """근거 없는 수치를 자리표시자로 바꾼다.

    반환: (정리된 텍스트, 제거된 주장 목록)
    """
    removed = unsupported_claims(text, sources)
    if not removed:
        return text, []
    cleaned = text
    for claim in removed:
        cleaned = cleaned.replace(claim["raw"], placeholder)
    return cleaned, removed


def _sanitize_value(
    value: object,
    sources: list[str],
    removed: list[dict],
    field: str,
) -> object:
    """문자열·리스트·중첩 dict 를 재귀적으로 검사한다.

    `statements.weekly`·`contribution.decisions` 처럼 dict 안에 들어간 문장도
    수치 가드레일을 우회하지 못하게 한다(2026-11-15 평가에서 60% 파생 수치가
    statements.monthly 를 통과한 결함).
    """
    if isinstance(value, str):
        text, dropped = sanitize_claims(value, sources)
        removed.extend({**item, "field": field} for item in dropped)
        return text
    if isinstance(value, list):
        return [
            _sanitize_value(entry, sources, removed, f"{field}[{index}]")
            for index, entry in enumerate(value)
        ]
    if isinstance(value, dict):
        return {
            key: _sanitize_value(
                entry, sources, removed, f"{field}.{key}" if field else str(key)
            )
            for key, entry in value.items()
        }
    return value


def sanitize_ai_result(result: dict, sources: Iterable[str]) -> tuple[dict, list[dict]]:
    """AI 분석 결과의 모든 문자열 필드에 수치 가드레일을 적용한다."""
    source_list = list(sources)
    removed: list[dict] = []
    cleaned = {
        key: _sanitize_value(value, source_list, removed, str(key))
        for key, value in (result or {}).items()
    }
    return cleaned, removed


def metric_is_verified(
    value: str, unit: str, sources: Iterable[str], *, evidence_id: str, basis: str
) -> bool:
    """지표가 근거를 갖는지 판단한다(근거 ID 또는 산출 기준 + 출처 텍스트)."""
    if not evidence_id and not basis.strip():
        return False
    haystack = " ".join(source or "" for source in sources)
    raw = f"{value}{unit}".replace(" ", "")
    return bool(raw) and raw.replace(",", ".") in haystack.replace(" ", "")


__all__ = [
    "find_claims",
    "metric_is_verified",
    "sanitize_ai_result",
    "sanitize_claims",
    "unsupported_claims",
]
