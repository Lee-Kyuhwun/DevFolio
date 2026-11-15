"""NVIDIA NIM 독립 심사 호출.

생성 모델과 다른 모델(minimax-m3.1-flash)을 사용한다. 키는 keyring/환경변수에서만
읽고 로그·결과에 남기지 않는다. Provider fallback 을 사용하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Optional, Sequence

import httpx

from devfolio.utils.security import get_api_key

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_JUDGE_MODEL = "minimaxai/minimax-m3.1-flash"
# 같은 계열 편향을 줄이기 위해 생성 모델(gpt-oss)과 다른 모델을 쓴다.
# 1차가 503/429 로 불가능할 때만 2차로 넘어가며, 실제 사용 모델을 결과에 남긴다.
JUDGE_MODELS = (DEFAULT_JUDGE_MODEL, "z-ai/glm-5.3-flash")
CACHE_PATH = Path(__file__).with_name(".cache") / "judge.json"


class JudgeUnavailable(RuntimeError):
    pass


def _extract_json(raw: str) -> Any:
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("심사 응답에서 JSON 을 찾지 못했습니다.")


def _cache_key(model: str, system: str, user: str) -> str:
    payload = json.dumps([model, system, user], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _call(
    system: str,
    user: str,
    *,
    model: Optional[str] = None,
    max_tokens: int = 4096,
    timeout: float = 180.0,
    retries: int = 3,
) -> tuple[Any, dict]:
    key = get_api_key("nvidia_nim")
    if not key:
        raise JudgeUnavailable("NVIDIA_NIM_API_KEY 가 설정되지 않았습니다.")
    cache = _read_cache()
    models = (model,) if model else JUDGE_MODELS
    last_error: Exception | None = None
    for active_model in models:
        cache_key = _cache_key(active_model, system, user)
        cached = cache.get(cache_key)
        if isinstance(cached, dict) and cached.get("parsed") is not None:
            return cached["parsed"], {**cached.get("meta", {}), "cached": True}
        last_error = _call_one(
            key,
            system,
            user,
            active_model=active_model,
            max_tokens=max_tokens,
            timeout=timeout,
            retries=retries,
            cache=cache,
            cache_key=cache_key,
        )
        if last_error is None:
            refreshed = _read_cache()
            item = refreshed.get(cache_key, {})
            return item.get("parsed"), item.get("meta", {})
    raise JudgeUnavailable(str(last_error)[:300])


def _call_one(
    key: str,
    system: str,
    user: str,
    *,
    active_model: str,
    max_tokens: int,
    timeout: float,
    retries: int,
    cache: dict,
    cache_key: str,
) -> Optional[Exception]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        started = time.monotonic()
        try:
            response = httpx.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": active_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                },
                timeout=timeout,
            )
            elapsed_ms = round((time.monotonic() - started) * 1000)
            if response.status_code != 200:
                if response.status_code in {429, 503} and attempt < retries:
                    # 무료 NIM 은 분당 요청 한도가 있다. 즉시 재시도하지 않는다.
                    retry_after = response.headers.get("retry-after")
                    try:
                        delay = (
                            float(retry_after) if retry_after else 8.0 * (attempt + 1)
                        )
                    except ValueError:
                        delay = 8.0 * (attempt + 1)
                    time.sleep(min(30.0, max(2.0, delay)))
                raise RuntimeError(
                    f"NVIDIA 심사 HTTP {response.status_code}: {response.text[:200]}"
                )
            body = response.json()
            message = (body.get("choices") or [{}])[0].get("message") or {}
            content = message.get("content") or ""
            if not content.strip():
                raise ValueError("NVIDIA 심사가 빈 응답을 반환했습니다.")
            parsed = _extract_json(content)
            meta = {
                "model": active_model,
                "latency_ms": elapsed_ms,
                "attempt": attempt + 1,
                "usage": body.get("usage") or {},
            }
            cache[cache_key] = {"parsed": parsed, "meta": meta}
            _write_cache(cache)
            return None
        except Exception as exc:  # noqa: BLE001 — 재시도 후 다음 모델로
            last_error = exc
    return last_error


SINGLE_LABELS = (
    "ENTAILMENT",
    "CONTRADICTION",
    "NEUTRAL",
    "INSUFFICIENT_EVIDENCE",
)
DOC_LABELS = (
    "MATCH",
    "PARTIAL_MATCH",
    "MISMATCH",
    "NOT_IMPLEMENTED",
    "INSUFFICIENT_EVIDENCE",
)

_SYSTEM = """당신은 독립적인 근거 감사자입니다. 주장을 대신 작성하지 말고, 제시된 근거만으로 판정합니다.
근거에 없는 사실을 상식으로 보충하지 마세요. 숫자·기간·비율은 근거에 같은 값이 있을 때만 지지된 것으로 봅니다.
반드시 JSON 객체 하나만 반환하세요."""


def _claim_batch(items: Sequence[dict]) -> tuple[list[dict], dict]:
    payload = [
        {"id": item["id"], "claim": item["claim"], "evidence": item["evidence"]}
        for item in items
    ]
    prompt = (
        "아래 각 항목의 claim 이 evidence 에 의해 논리적으로 뒷받침되는지 판정하세요.\n"
        "레이블:\n"
        "- ENTAILMENT: evidence 가 claim 의 핵심 내용과 수치를 모두 지지한다.\n"
        "- CONTRADICTION: evidence 가 claim 과 명백히 충돌한다.\n"
        "- NEUTRAL: 관련은 있지만 claim 을 입증하지 못한다(특히 수치·인과·효과 주장).\n"
        "- INSUFFICIENT_EVIDENCE: evidence 가 claim 을 판단할 만큼 구체적이지 않다.\n"
        '출력: {"items":[{"id":"...","label":"...","reason":"한 문장"}]}\n\n'
        + json.dumps(payload, ensure_ascii=False)
    )
    parsed, meta = _call(_SYSTEM, prompt)
    rows = parsed.get("items") if isinstance(parsed, dict) else parsed
    if not isinstance(rows, list):
        raise ValueError("claim 심사 응답에 items 배열이 없습니다.")
    return rows, meta


def judge_claims(items: Sequence[dict], *, batch_size: int = 14) -> dict:
    """42개 claim 을 4개 batch 로 나눠 독립 판정한다."""
    results: dict[str, dict] = {}
    calls: list[dict] = []
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        rows, meta = _claim_batch(batch)
        calls.append(meta)
        for row in rows:
            if not isinstance(row, dict):
                continue
            item_id = str(row.get("id", ""))
            label = str(row.get("label", "")).upper().strip()
            if item_id and label in SINGLE_LABELS:
                results[item_id] = {
                    "label": label,
                    "reason": str(row.get("reason", ""))[:300],
                }
    missing = [item["id"] for item in items if item["id"] not in results]
    if missing:
        raise ValueError(f"심사 결과 누락: {missing}")
    return {"items": results, "calls": calls}


def judge_doc_code(items: Sequence[dict], *, batch_size: int = 6) -> dict:
    results: dict[str, dict] = {}
    calls: list[dict] = []
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        payload = [
            {"id": item["id"], "doc": item["doc"], "code": item["code"]}
            for item in batch
        ]
        prompt = (
            "문서 주장(doc)과 실제 코드/설정(code)의 의미적 일치를 판정하세요.\n"
            "레이블:\n"
            "- MATCH: 핵심 동작과 제약이 모두 구현됨\n"
            "- PARTIAL_MATCH: 일부 구현됐지만 문서의 수치·범위·조건이 확인되지 않음\n"
            "- MISMATCH: 구현은 있으나 문서와 반대/다른 값\n"
            "- NOT_IMPLEMENTED: 구현 자체가 없음\n"
            "- INSUFFICIENT_EVIDENCE: 코드 근거가 너무 추상적이어서 판단 불가\n"
            '출력: {"items":[{"id":"...","label":"...","reason":"한 문장"}]}\n\n'
            + json.dumps(payload, ensure_ascii=False)
        )
        parsed, meta = _call(_SYSTEM, prompt)
        calls.append(meta)
        rows = parsed.get("items") if isinstance(parsed, dict) else parsed
        if not isinstance(rows, list):
            raise ValueError("doc-code 심사 응답에 items 배열이 없습니다.")
        for row in rows:
            if not isinstance(row, dict):
                continue
            item_id = str(row.get("id", ""))
            label = str(row.get("label", "")).upper().strip()
            if item_id and label in DOC_LABELS:
                results[item_id] = {
                    "label": label,
                    "reason": str(row.get("reason", ""))[:300],
                }
    missing = [item["id"] for item in items if item["id"] not in results]
    if missing:
        raise ValueError(f"doc-code 심사 결과 누락: {missing}")
    return {"items": results, "calls": calls}


QUALITY_AXES = (
    "factual_accuracy",
    "specificity",
    "contribution_clarity",
    "problem_solution",
    "internal_report_tone",
)


def judge_quality(items: Sequence[dict], *, batch_size: int = 10) -> dict:
    """전략명을 숨기고 문장 품질을 1~5로 채점한다. evidence 를 함께 준다."""
    results: dict[str, dict] = {}
    calls: list[dict] = []
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        payload = [
            {
                "id": item["blind_id"],
                "evidence": item["evidence"],
                "summary": item["text"],
            }
            for item in batch
        ]
        prompt = (
            "아래 요약문을 회사 내부 성과보고 품질로 채점하세요. 각 축 1~5 정수.\n"
            "factual_accuracy: evidence 에 없는 수치·기능·성과가 있으면 1~2.\n"
            "specificity: 구체적 기술·행동·결과가 있으면 높음.\n"
            "contribution_clarity: 본인 행동과 공동 작업이 구분되면 높음.\n"
            "problem_solution: 문제→행동→결과가 연결되면 높음.\n"
            "internal_report_tone: 자기소개서·마케팅 과장 없이 보고 문체면 높음.\n"
            '출력: {"items":[{"id":"...","scores":{"factual_accuracy":1,"specificity":1,'
            '"contribution_clarity":1,"problem_solution":1,"internal_report_tone":1},'
            '"reason":"한 문장"}]}\n\n' + json.dumps(payload, ensure_ascii=False)
        )
        parsed, meta = _call(_SYSTEM, prompt, max_tokens=4096)
        calls.append(meta)
        rows = parsed.get("items") if isinstance(parsed, dict) else parsed
        if not isinstance(rows, list):
            raise ValueError("quality 심사 응답에 items 배열이 없습니다.")
        for row in rows:
            if not isinstance(row, dict):
                continue
            blind_id = str(row.get("id", ""))
            scores = row.get("scores")
            if not blind_id or not isinstance(scores, dict):
                continue
            clean: dict[str, int] = {}
            for axis in QUALITY_AXES:
                try:
                    clean[axis] = max(1, min(5, int(scores.get(axis))))
                except (TypeError, ValueError):
                    clean[axis] = 0
            results[blind_id] = {
                "scores": clean,
                "mean": (
                    sum(clean.values()) / len(QUALITY_AXES)
                    if all(clean.get(axis) for axis in QUALITY_AXES)
                    else None
                ),
                "reason": str(row.get("reason", ""))[:300],
            }
    missing = [item["blind_id"] for item in items if item["blind_id"] not in results]
    if missing:
        raise ValueError(f"quality 심사 결과 누락: {missing}")
    return {"items": results, "calls": calls}


__all__ = [
    "DEFAULT_JUDGE_MODEL",
    "DOC_LABELS",
    "JudgeUnavailable",
    "QUALITY_AXES",
    "SINGLE_LABELS",
    "judge_claims",
    "judge_doc_code",
    "judge_quality",
]
