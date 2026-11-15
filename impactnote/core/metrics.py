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
_CLAIM_PATTERN = re.compile(
    r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(%|퍼센트|건|개|회|시간|분|초|배|원|명|일|주|개월|ms|초|분기|년)"
)

# 근거 텍스트에서 숫자만 뽑을 때 쓴다(단위 무관).
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def find_claims(text: str) -> list[dict[str, str]]:
    """텍스트에서 수치 주장을 추출한다."""
    claims: list[dict[str, str]] = []
    for match in _CLAIM_PATTERN.finditer(text or ""):
        claims.append(
            {
                "value": match.group(1).replace(",", "."),
                "unit": match.group(2),
                "raw": match.group(0).strip(),
            }
        )
    return claims


def _numbers(text: str) -> set[str]:
    return {match.group(0).replace(",", ".") for match in _NUMBER.finditer(text or "")}


def unsupported_claims(text: str, sources: Iterable[str]) -> list[dict[str, str]]:
    """근거 텍스트에 없는 수치 주장만 반환한다."""
    source_numbers: set[str] = set()
    for source in sources:
        source_numbers |= _numbers(source or "")
    return [
        claim for claim in find_claims(text) if claim["value"] not in source_numbers
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


def sanitize_ai_result(result: dict, sources: Iterable[str]) -> tuple[dict, list[dict]]:
    """AI 분석 결과의 모든 문자열 필드에 수치 가드레일을 적용한다."""
    source_list = list(sources)
    removed: list[dict] = []
    cleaned: dict = {}
    for key, value in (result or {}).items():
        if isinstance(value, str):
            text, dropped = sanitize_claims(value, source_list)
            cleaned[key] = text
            removed.extend({**item, "field": key} for item in dropped)
        elif isinstance(value, list):
            items = []
            for entry in value:
                if isinstance(entry, str):
                    text, dropped = sanitize_claims(entry, source_list)
                    items.append(text)
                    removed.extend({**item, "field": key} for item in dropped)
                else:
                    items.append(entry)
            cleaned[key] = items
        else:
            cleaned[key] = value
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
