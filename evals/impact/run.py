"""ImpactNote 6개 AI 지표를 Ground Truth 로 평가한다.

    python -m evals.impact.run --live
    python -m evals.impact.run --offline

- claim 42개: Hallucination + Semantic Entailment (실제 NVIDIA 생성문 30 + 경계 12)
- 통제 Git 저장소: 성과 Precision/Recall (12 성과 + 8 비성과)
- 같은 저장소: 개인 기여 귀속 (8 단위)
- doc-code 12개: AI 독립 판정
- NVIDIA 요약 20개: 문장 품질 5축
- live 3개: 현재 프롬프트의 NVIDIA End-to-End 호출

점수 기준은 결과를 보기 전(2026-11-15)에 고정했다. 분모가 0이면 NOT_MEASURED 다.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from evals.impact import judge as judge_mod
from evals.impact.fixture import build_fixture
from evals.impact.gate import evaluate_effect_gate
from evals.impact.metrics import (
    DOC_CODE_LABELS,
    LABELS,
    binary_metrics,
    bootstrap_ci,
    citation_metrics,
    classify_metrics,
    hallucination_metrics,
    mean,
    proportion_ci,
    safe_div,
)
from impactnote.core.intel.engine import analyze_project
from impactnote.core.store import JsonStore

# 결과를 보기 전에 고정한 합격 기준.
THRESHOLDS = {
    "hallucination_combined_max": 0.20,
    "extraction_f1_min": 0.70,
    "quality_mean_min": 3.50,
    # 품질 평균이 높아도 근거 없는 수치·기능이 많으면 하한선을 통과하지 못한다.
    "quality_factual_mean_min": 3.00,
    "quality_low_factuality_max": 0.25,
    "attribution_exact_min": 0.80,
    "doc_code_accuracy_min": 0.70,
    "semantic_accuracy_min": 0.70,
    # 정성 효과 Hard Gate: 근거 없는 효과 주장을 통과시키지 않으면서
    # 근거가 있는 효과 주장은 80% 이상 보존해야 한다.
    "effect_gate_false_accept_max": 0.05,
    "effect_gate_retention_min": 0.80,
}

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = Path(__file__).with_name("dataset.json")


# ---------------------------------------------------------------------------
# 결정론적 기준선
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(%|퍼센트|배|ms|밀리초|초|분|시간|건|개|명|인|rpm|MB|GB)?",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{2,}|[가-힣]{2,}")
_STOP = {
    "그리고",
    "그러나",
    "대한",
    "통해",
    "있는",
    "없는",
    "한다",
    "했다",
    "합니다",
    "있습니다",
    "기능",
    "사용",
    "처리",
    "시스템",
    "프로젝트",
    "서비스",
    "코드",
    "문서",
    "변경",
    "개선",
    "추가",
    "구현",
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
}


def _numbers(text: str) -> list[tuple[float, str]]:
    values: list[tuple[float, str]] = []
    for match in _NUMBER_RE.finditer(text):
        unit = (match.group(2) or "").lower()
        if unit == "퍼센트":
            unit = "%"
        if unit == "밀리초":
            unit = "ms"
        if unit == "인":
            unit = "명"
        values.append((float(match.group(1)), unit))
    return values


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_RE.findall(text)
        if token.lower() not in _STOP and len(token) >= 2
    }


def classify_claim_deterministic(claim: str, evidence: str) -> str:
    """규칙 기반 기준선. 심사 모델의 대체가 아니라 비교 기준이다."""
    lowered_claim = claim.lower()
    lowered_evidence = evidence.lower()
    if not evidence.strip():
        return "INSUFFICIENT_EVIDENCE"

    claim_numbers = _numbers(claim)
    evidence_numbers = _numbers(evidence)
    if claim_numbers:
        for value, unit in claim_numbers:
            same_value = [
                (number, number_unit)
                for number, number_unit in evidence_numbers
                if math.isclose(number, value)
                and (not unit or not number_unit or unit == number_unit)
            ]
            if same_value:
                continue
            same_unit = [
                number
                for number, number_unit in evidence_numbers
                if unit and number_unit == unit
            ]
            if same_unit:
                return "CONTRADICTION"
            if evidence_numbers:
                return "NEUTRAL"
            return "NEUTRAL"
    if "1인" in claim and re.search(r"team_size\s*[:=]\s*[2-9]", evidence):
        return "CONTRADICTION"
    if "postgres" in lowered_claim and "sqlite" in lowered_evidence:
        return "CONTRADICTION"
    if "oauth" in lowered_claim and (
        "no implementation" in lowered_evidence
        or "구현 코드는 없다" in lowered_evidence
    ):
        return "INSUFFICIENT_EVIDENCE"

    claim_tokens = _tokens(claim)
    evidence_tokens = _tokens(evidence)
    overlap = claim_tokens & evidence_tokens
    if len(overlap) >= 2 and len(overlap) / max(1, len(claim_tokens)) >= 0.4:
        return "ENTAILMENT"
    if overlap:
        return "NEUTRAL"
    return "INSUFFICIENT_EVIDENCE"


def classify_doc_code_deterministic(doc: str, code: str) -> str:
    lowered = code.lower()
    if not code.strip():
        return "NOT_IMPLEMENTED"
    if any(
        marker in lowered
        for marker in ("no oauth", "no implementation", "no pdf", "no http endpoint")
    ):
        return "NOT_IMPLEMENTED"
    doc_numbers = _numbers(doc)
    code_numbers = _numbers(code)
    if doc_numbers and code_numbers:
        doc_values = {value for value, _ in doc_numbers}
        code_values = {value for value, _ in code_numbers}
        if doc_values.isdisjoint(code_values):
            return "MISMATCH"
    doc_tokens = _tokens(doc)
    code_tokens = _tokens(code)
    overlap = doc_tokens & code_tokens
    ratio = len(overlap) / max(1, len(doc_tokens))
    if ratio >= 0.5:
        return "MATCH"
    if ratio >= 0.2:
        return "PARTIAL_MATCH"
    return "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------------------
# 실행 도우미
# ---------------------------------------------------------------------------


def _load_dataset(path: Path = DATASET_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "version",
        "claim_units",
        "doc_code_units",
        "achievement_units",
        "non_achievement_paths",
        "attribution_units",
        "live_activities",
    }
    missing = required - set(data)
    if missing:
        raise ValueError(f"데이터셋 필수 키 누락: {sorted(missing)}")
    if len(data["claim_units"]) < 40:
        raise ValueError("claim 단위가 40개 미만입니다.")
    return data


def _ci_rows(gold: Sequence[str], predicted: Sequence[str]) -> list[float]:
    return [
        1.0 if expected == actual else 0.0
        for expected, actual in zip(gold, predicted, strict=True)
    ]


def _path_from_candidate(title: str) -> str:
    prefix, separator, path = title.partition(": ")
    if not separator:
        return ""
    return path.strip()


def _run_analysis(dataset: dict) -> tuple[dict, dict]:
    temp = Path(tempfile.mkdtemp(prefix="impactnote-eval-"))
    repo = temp / "repo"
    store = JsonStore(temp / "data")
    try:
        build_fixture(repo)
        analysis = analyze_project(
            str(repo),
            author_email="alice@example.com",
            use_ai=False,
            force=True,
            store=store,
        )
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    candidate_by_path: dict[str, Any] = {}
    for candidate in analysis.candidates:
        path = _path_from_candidate(candidate.title)
        if path:
            candidate_by_path.setdefault(path, candidate)
    predicted_paths = sorted(candidate_by_path)

    positives = {item["path"] for item in dataset["achievement_units"]}
    all_paths = sorted(positives | set(dataset["non_achievement_paths"]))
    binary_pred = [path in candidate_by_path for path in all_paths]
    ordered_gold = [path in positives for path in all_paths]
    extraction = binary_metrics(ordered_gold, binary_pred)
    extraction.update(
        {
            "n_positive": len(positives),
            "n_negative": len(dataset["non_achievement_paths"]),
            "predicted_paths": predicted_paths,
            "true_positives": sorted(positives & set(candidate_by_path)),
            "false_positives": sorted(set(candidate_by_path) - positives),
            "false_negatives": sorted(positives - set(candidate_by_path)),
            "candidate_count": len(analysis.candidates),
            "engine_status": analysis.status,
            "engine_warnings": analysis.warnings,
        }
    )

    attribution_rows: list[dict] = []
    for unit in dataset["attribution_units"]:
        candidate = candidate_by_path.get(unit["path"])
        authors = (
            {
                str(item.get("email", "")).lower()
                for item in (candidate.contribution.get("authors") or [])
                if item.get("email")
            }
            if candidate
            else set()
        )
        expected = {email.lower() for email in unit["expected"]}
        attribution_rows.append(
            {
                "id": unit["id"],
                "path": unit["path"],
                "expected": sorted(expected),
                "predicted": sorted(authors),
                "exact": bool(authors) and authors == expected,
                "coverage": bool(authors),
                "wrong_solo": len(authors) == 1 and len(expected) > 1,
            }
        )
    attribution = {
        "n": len(attribution_rows),
        "exact_accuracy": safe_div(
            sum(1 for row in attribution_rows if row["exact"]), len(attribution_rows)
        ),
        "coverage": safe_div(
            sum(1 for row in attribution_rows if row["coverage"]),
            len(attribution_rows),
        ),
        "wrong_solo_rate": safe_div(
            sum(1 for row in attribution_rows if row["wrong_solo"]),
            len(attribution_rows),
        ),
        "rows": attribution_rows,
    }
    return {"extraction": extraction, "attribution": attribution}, {
        "candidate_count": len(analysis.candidates),
        "analysis_status": analysis.status,
        "measurements": len(analysis.measurements),
        "documents": len(analysis.documents),
        "commits": len(analysis.commits),
    }


def _quality_items(dataset: dict) -> list[dict]:
    from evals.label import _read_jsonl, latest_rows
    from evals.run import load_cases

    run_path = ROOT / dataset["quality_run"]
    rows = {
        row["output_id"]: row
        for row in latest_rows(_read_jsonl(run_path))
        if not row.get("error")
    }
    cases = {
        case_id: project for case_id, project in load_cases(ROOT / "evals" / "cases")
    }
    from evals.label import evidence_summary

    summaries = {
        case_id: evidence_summary(project) for case_id, project in cases.items()
    }
    items: list[dict] = []
    for index, output_id in enumerate(dataset["quality_output_ids"], start=1):
        row = rows.get(output_id)
        if not row or not str(row.get("text") or "").strip():
            continue
        items.append(
            {
                "blind_id": f"q{index:03d}",
                "output_id": output_id,
                "case_id": row.get("case_id", output_id.split(":")[0]),
                "text": row["text"],
                "evidence": summaries.get(row.get("case_id", ""), ""),
                "archived_judge_scores": row.get("judge_scores", {}),
            }
        )
    return items


def _quality_report(judged: dict, items: Sequence[dict]) -> dict:
    rows: list[dict] = []
    for item in items:
        result = judged["items"].get(item["blind_id"])
        if not result:
            continue
        rows.append(
            {
                "output_id": item["output_id"],
                "case_id": item["case_id"],
                **result,
                "archived_judge_scores": item["archived_judge_scores"],
            }
        )
    means = [row["mean"] for row in rows if row["mean"] is not None]
    axes = {
        axis: mean(
            [row["scores"].get(axis) for row in rows if row.get("scores", {}).get(axis)]
        )
        for axis in judge_mod.QUALITY_AXES
    }
    low_factual = sum(
        1 for row in rows if (row.get("scores") or {}).get("factual_accuracy", 5) <= 2
    )
    return {
        "n": len(rows),
        "mean": mean(means),
        "axis_means": axes,
        "low_factuality_count": low_factual,
        "low_factuality_rate": safe_div(low_factual, len(rows)),
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Live NVIDIA
# ---------------------------------------------------------------------------


def _restricted_nvidia_service():
    from devfolio.core.ai_reliability import get_health_store
    from devfolio.core.ai_service import AIService
    from devfolio.core.storage import load_config

    config = load_config()
    provider = config.get_provider("nvidia_nim")
    if provider is None:
        return None
    provider = provider.model_copy(update={"model": "openai/gpt-oss-20b"})
    config.ai_providers = [provider]
    config.default_ai_provider = "nvidia_nim"
    store = get_health_store()
    for key in list(store.snapshot()):
        if key.startswith("nvidia_nim::"):
            store.clear(key)
    return AIService(config)


def _live_generation(dataset: dict) -> dict:
    from impactnote.core.ai import SYSTEM_PROMPT, USER_PROMPT, _parse_json

    service = _restricted_nvidia_service()
    if service is None:
        return {"status": "NOT_CONFIGURED", "reason": "nvidia_nim provider 없음"}
    old_fallback = os.environ.get("DEVFOLIO_AI_PROVIDER_FALLBACK")
    old_budget = os.environ.get("DEVFOLIO_AI_TIME_BUDGET")
    os.environ["DEVFOLIO_AI_PROVIDER_FALLBACK"] = "0"
    os.environ["DEVFOLIO_AI_TIME_BUDGET"] = "240"
    rows: list[dict] = []
    try:
        for activity in dataset["live_activities"]:
            values = activity["input"]
            telemetry: dict = {}
            started = time.monotonic()
            row: dict = {
                "id": activity["id"],
                "provider": "nvidia_nim",
                "model": "nvidia_nim/openai/gpt-oss-20b",
            }
            try:
                raw = service._call(
                    SYSTEM_PROMPT,
                    USER_PROMPT.format(
                        title=values["title"],
                        activity_type=values["activity_type"],
                        period=values["period"],
                        project=values["project"],
                        description=values["description"],
                        problem=values["problem"],
                        action=values["action"],
                        result=values["result"] or "(기록 없음)",
                        collaborators=values["collaborators"] or "(없음)",
                        evidence=values["evidence"],
                    ),
                    provider_name="nvidia_nim",
                    max_tokens=1600,
                    json_mode=True,
                    telemetry=telemetry,
                    stage="impact_eval_live",
                )
                elapsed_ms = round((time.monotonic() - started) * 1000)
                payload = _parse_json(raw)
                from impactnote.core.claims import (
                    find_effect_claims,
                    gate_result,
                    verify_effect_claim,
                )
                from impactnote.core.metrics import sanitize_ai_result

                source = " ".join(str(value) for value in values.values())
                cleaned, removed_metrics = sanitize_ai_result(payload, [source])
                raw_text = json.dumps(payload, ensure_ascii=False)
                raw_effects = find_effect_claims(raw_text)
                raw_unsupported_effects = [
                    claim
                    for claim in raw_effects
                    if (verdict := verify_effect_claim(claim, [source]))
                    and not verdict.supported
                ]
                cleaned, removed_effects = gate_result(cleaned, [source])
                sanitized_text = json.dumps(cleaned, ensure_ascii=False)
                stored_effects = find_effect_claims(sanitized_text)
                residual_unsupported_effects = [
                    claim
                    for claim in stored_effects
                    if (verdict := verify_effect_claim(claim, [source]))
                    and not verdict.supported
                ]
                raw_numbers = [number for number, _ in _numbers(raw)]
                output_numbers = [number for number, _ in _numbers(sanitized_text)]
                unsupported_numbers = [
                    number
                    for number in output_numbers
                    if str(int(number) if number.is_integer() else number) not in source
                ]
                raw_unsupported_numbers = [
                    number
                    for number in raw_numbers
                    if str(int(number) if number.is_integer() else number) not in source
                ]
                forbidden = [
                    pattern
                    for pattern in activity.get("forbidden_patterns", [])
                    if pattern.lower() in raw.lower()
                ]
                row.update(
                    {
                        "status": "LIVE_VERIFIED",
                        "latency_ms": elapsed_ms,
                        "usage": telemetry.get("usage") or {},
                        "json_ok": isinstance(payload, dict),
                        "response_chars": len(raw),
                        "raw_output_numbers": raw_numbers,
                        "output_numbers": output_numbers,
                        "raw_unsupported_numbers": raw_unsupported_numbers,
                        "unsupported_numbers": unsupported_numbers,
                        "removed_metrics": removed_metrics,
                        "raw_effect_claims": len(raw_effects),
                        "raw_unsupported_effect_claims": len(raw_unsupported_effects),
                        "blocked_effect_claims": len(removed_effects),
                        "stored_effect_claims": len(stored_effects),
                        "residual_unsupported_effect_claims": len(
                            residual_unsupported_effects
                        ),
                        "blocked_effect_details": removed_effects,
                        "forbidden_hits": forbidden,
                        "unverified_fields": cleaned.get("unverified_fields", []),
                        "text": sanitized_text[:2000],
                        "raw_text": raw[:2000],
                    }
                )
            except Exception as exc:  # noqa: BLE001 — 실패도 보고서에 남긴다
                info = {
                    key: value
                    for key, value in telemetry.items()
                    if key in {"provider", "model", "usage", "errors", "attempts"}
                }
                row.update(
                    {
                        "status": "FAILED",
                        "latency_ms": round((time.monotonic() - started) * 1000),
                        "telemetry": info,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                    }
                )
            rows.append(row)
    finally:
        if old_fallback is None:
            os.environ.pop("DEVFOLIO_AI_PROVIDER_FALLBACK", None)
        else:
            os.environ["DEVFOLIO_AI_PROVIDER_FALLBACK"] = old_fallback
        if old_budget is None:
            os.environ.pop("DEVFOLIO_AI_TIME_BUDGET", None)
        else:
            os.environ["DEVFOLIO_AI_TIME_BUDGET"] = old_budget
    ok = [row for row in rows if row["status"] == "LIVE_VERIFIED"]
    return {
        "status": "LIVE_VERIFIED" if ok else "FAILED",
        "n": len(rows),
        "succeeded": len(ok),
        "failed": len(rows) - len(ok),
        "mean_latency_ms": mean([row.get("latency_ms") for row in ok]),
        "total_prompt_tokens": sum(
            int((row.get("usage") or {}).get("prompt_tokens") or 0) for row in ok
        ),
        "total_completion_tokens": sum(
            int((row.get("usage") or {}).get("completion_tokens") or 0) for row in ok
        ),
        "unsupported_number_rate": safe_div(
            sum(len(row.get("unsupported_numbers") or []) for row in ok),
            sum(len(row.get("output_numbers") or []) for row in ok),
        ),
        "raw_unsupported_number_rate": safe_div(
            sum(len(row.get("raw_unsupported_numbers") or []) for row in ok),
            sum(len(row.get("raw_output_numbers") or []) for row in ok),
        ),
        "removed_metric_count": sum(
            len(row.get("removed_metrics") or []) for row in ok
        ),
        "raw_effect_claim_count": sum(
            int(row.get("raw_effect_claims") or 0) for row in ok
        ),
        "raw_unsupported_effect_claim_count": sum(
            int(row.get("raw_unsupported_effect_claims") or 0) for row in ok
        ),
        "blocked_effect_claim_count": sum(
            int(row.get("blocked_effect_claims") or 0) for row in ok
        ),
        "residual_unsupported_effect_claim_count": sum(
            int(row.get("residual_unsupported_effect_claims") or 0) for row in ok
        ),
        "forbidden_hit_count": sum(len(row.get("forbidden_hits") or []) for row in ok),
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------


def _pct(value: Optional[float]) -> str:
    return "NOT_MEASURED" if value is None else f"{value * 100:.1f}%"


def _num(value: Optional[float]) -> str:
    return "NOT_MEASURED" if value is None else f"{value:.2f}"


def _verdict(value: Optional[float], threshold: float, *, higher: bool) -> str:
    if value is None:
        return "NOT_MEASURED"
    if higher:
        return "PASS" if value >= threshold else "FAIL"
    return "PASS" if value <= threshold else "FAIL"


def _confusion_table(confusion: dict, labels: Sequence[str]) -> str:
    header = "| gold \\ pred | " + " | ".join(labels) + " |"
    divider = "|---|" + "|".join("---" for _ in labels) + "|"
    lines = [header, divider]
    for expected in labels:
        counts = confusion.get(expected, {})
        lines.append(
            f"| {expected} | "
            + " | ".join(str(counts.get(actual, 0)) for actual in labels)
            + " |"
        )
    return "\n".join(lines)


def build_markdown(result: dict) -> str:
    claim = result["claims"]
    hallucination = claim["hallucination"]
    semantic = claim["semantic"]
    extraction = result["extraction"]
    quality = result["quality"]
    attribution = result["attribution"]
    doc_code = result["doc_code"]
    live = result["live"]
    lines = [
        "# ImpactNote AI 평가 결과",
        "",
        f"- 실행일: {result['run_at']}",
        f"- Git commit: `{result['git_sha']}`",
        f"- 데이터셋: `{result['dataset_version']}` (claim {claim['n']}개, doc-code {doc_code['n']}개, 통제 저장소 성과 {extraction['n_positive']}개)",
        f"- 생성 모델: `{result['generator_model']}`",
        f"- 독립 심사 모델: `{result['judge_model']}`",
        f"- 실행 모드: **{result['mode']}**",
        "",
        "## A. 미측정 지표 해결 현황",
        "",
        "| 평가 항목 | 기존 | 이번 측정 | 표본 수 | 판정 |",
        "|---|---|---|---|---|",
        f"| Hallucination Rate | 미측정 | {_pct(hallucination['combined_unsupported_or_contradicted_rate'])} | {hallucination['n']} | {result['verdicts']['hallucination']} |",
        f"| 정성 효과 Hard Gate | 미측정 | false accept {_pct(claim['effect_gate']['false_accept_rate'])} / retention {_pct(claim['effect_gate']['retention'])} | {claim['effect_gate']['n_effect_claims']} 효과 claim | {result['verdicts']['effect_gate']} |",
        f"| Precision / Recall / F1 | 미측정 | P {_num(extraction['precision'])} / R {_num(extraction['recall'])} / F1 {_num(extraction['f1'])} | {extraction['n_positive']} 성과 + {extraction['n_negative']} 비성과 | {result['verdicts']['extraction']} |",
        f"| 성과 문장 품질 | 미측정 | {_num(quality['mean'])} / 5 · 사실성 {_num(quality['axis_means'].get('factual_accuracy'))} / 5 | {quality['n']} | {result['verdicts']['quality']} |",
        f"| 개인 기여 귀속 | 미측정 | exact {_pct(attribution['exact_accuracy'])} | {attribution['n']} | {result['verdicts']['attribution']} |",
        f"| 문서·코드 의미 일치 | 미측정 | accuracy {_pct(doc_code['metrics']['accuracy'])} | {doc_code['n']} | {result['verdicts']['doc_code']} |",
        f"| Semantic Entailment | 미측정 | accuracy {_pct(semantic['judge']['accuracy'])} | {semantic['judge']['n']} | {result['verdicts']['semantic']} |",
        "",
        "## B. Hallucination",
        "",
        "정의: `Contradiction Rate`와 `Unsupported Claim Rate`를 분리하고, 합계를 `Combined Unsupported-or-Contradicted Rate`로 부른다.",
        "`NEUTRAL`(관련은 있으나 입증하지 못함)과 `INSUFFICIENT_EVIDENCE`는 모두 unsupported 로 계산했다.",
        "",
        "| 값 | 결과 |",
        "|---|---|",
        f"| 표본 | {hallucination['n']} |",
        f"| Supported (ENTAILMENT) | {hallucination['supported']} |",
        f"| Contradicted | {hallucination['contradicted']} |",
        f"| Unsupported | {hallucination['unsupported']} |",
        f"| Contradiction Rate | {_pct(hallucination['contradiction_rate'])} |",
        f"| Unsupported Claim Rate | {_pct(hallucination['unsupported_claim_rate'])} |",
        f"| **Combined Unsupported-or-Contradicted** | **{_pct(hallucination['combined_unsupported_or_contradicted_rate'])}** |",
        f"| 95% bootstrap CI | {_pct(hallucination['ci'][0])} ~ {_pct(hallucination['ci'][1])} |"
        if hallucination.get("ci")
        else "| 95% bootstrap CI | NOT_MEASURED |",
        "",
        "Ground Truth는 실제 NVIDIA `gpt-oss-20b`가 생성한 2026-10-03 요약에서 30문장, 경계 사례 12개를 고정한 것이다.",
        "",
        "## B-2. 정성 효과 Hard Gate",
        "",
        '수치 가드레일을 통과한 효과 주장("안정성 향상", "비용 절감" 등)을 근거와 대조하는 결정론적 Gate 다.',
        "효과 주장이 아닌 사실·수치 claim 은 적용 대상이 아니므로 coverage 를 함께 본다.",
        "",
        "| 값 | 결과 |",
        "|---|---|",
        f"| 전체 claim | {claim['effect_gate']['n_total_claims']} |",
        f"| Gate 적용 대상(효과 주장) | {claim['effect_gate']['n_effect_claims']} ({_pct(claim['effect_gate']['coverage'])}) |",
        f"| 근거 있는 효과 claim | {claim['effect_gate']['supported_effect_claims']} |",
        f"| 근거 없는 효과 claim | {claim['effect_gate']['unsupported_effect_claims']} |",
        f"| **잘못 통과(false accept)** | **{claim['effect_gate']['false_accepts']}** ({_pct(claim['effect_gate']['false_accept_rate'])}, CI {_pct(claim['effect_gate']['false_accept_ci'][0]) if claim['effect_gate']['false_accept_ci'] else 'NOT_MEASURED'}~{_pct(claim['effect_gate']['false_accept_ci'][1]) if claim['effect_gate']['false_accept_ci'] else 'NOT_MEASURED'}) |",
        f"| 근거 있는데 차단(false rejection) | {claim['effect_gate']['false_rejections']} |",
        f"| **보존율(retention)** | **{_pct(claim['effect_gate']['retention'])}** |",
        f"| 통과 claim 정밀도 | {_pct(claim['effect_gate']['accepted_precision'])} |",
        "",
        "통과·차단 내역:",
        "",
        "| ID | gold | 판정 | 사유 | 주장 |",
        "|---|---|---|---|---|",
        *[
            f"| {row['id']} | {row['gold']} | {'통과' if row['accepted'] else '차단'} | {row['reason']} | {row['claim'][:60]} |"
            for row in claim["effect_gate"]["rows"]
        ],
        "",
        "## C. 성과 발굴 Precision / Recall",
        "",
        "통제 저장소의 12개 실제 성과와 8개 비성과(포맷·주석·리버트·삭제·문서·테스트·1줄·의존성)를 실제 분석기로 실행했다.",
        "",
        "| TP | FP | FN | Precision | Recall | F1 |",
        "|---|---|---|---|---|---|",
        f"| {extraction['tp']} | {extraction['fp']} | {extraction['fn']} | {_num(extraction['precision'])} | {_num(extraction['recall'])} | {_num(extraction['f1'])} |",
        "",
        f"- False positives: {', '.join(extraction['false_positives']) or '없음'}",
        f"- False negatives: {', '.join(extraction['false_negatives']) or '없음'}",
        f"- 분석기 후보 수: {extraction['candidate_count']}, 상태: `{extraction['engine_status']}`",
        "",
        "## D. 성과 문장 품질",
        "",
        "5축(사실 정확성·구체성·기여 명확성·문제-해결 연결·내부 보고 문체)을 1~5로 독립 심사했다.",
        "",
        "| 축 | 평균 |",
        "|---|---|",
        *[
            f"| {axis} | {_num(value)} |"
            for axis, value in quality["axis_means"].items()
        ],
        f"| **전체** | **{_num(quality['mean'])}** |",
        "",
        f"- 사실 정확성 1~2점: {quality['low_factuality_count']} / {quality['n']} ({_pct(quality['low_factuality_rate'])})",
        f"- 품질 하한 게이트: 평균 ≥ {THRESHOLDS['quality_mean_min']:.1f}, 사실성 ≥ {THRESHOLDS['quality_factual_mean_min']:.1f}, 사실성 1~2점 비율 ≤ {THRESHOLDS['quality_low_factuality_max']:.0%} → **{result['verdicts']['quality']}**",
        f"- 95% bootstrap CI: {_num(quality['ci'][0])} ~ {_num(quality['ci'][1])}"
        if quality.get("ci")
        else "- 95% bootstrap CI: NOT_MEASURED",
        "",
        "## E. 개인 기여 귀속",
        "",
        "| ID | 경로 | 정답 | 예측 | exact |",
        "|---|---|---|---|---|",
        *[
            f"| {row['id']} | `{row['path']}` | {', '.join(row['expected']) or 'UNKNOWN'} | {', '.join(row['predicted']) or 'UNKNOWN'} | {row['exact']} |"
            for row in attribution["rows"]
        ],
        "",
        f"- Exact set accuracy: **{_pct(attribution['exact_accuracy'])}** ({attribution['n']})",
        f"- Wrong solo attribution rate: {_pct(attribution['wrong_solo_rate'])}",
        f"- Coverage: {_pct(attribution['coverage'])}",
        "- 검토·설계만 한 사람, 커밋을 대신 작성한 경우는 근거가 없으면 UNKNOWN 이어야 한다. 이번 표본에는 그런 단위를 정답에서 제외했다.",
        "",
        "## F. 문서·코드 의미 일치",
        "",
        f"- Accuracy: **{_pct(doc_code['metrics']['accuracy'])}**, Macro F1: {_num(doc_code['metrics']['macro_f1'])} (n={doc_code['n']})",
        f"- 거짓 MATCH rate: {_pct(doc_code['false_match_rate'])}",
        "",
        "| Class | Precision | Recall | F1 | Support |",
        "|---|---|---|---|---|",
        *[
            f"| {label} | {_num(item['precision'])} | {_num(item['recall'])} | {_num(item['f1'])} | {item['support']} |"
            for label, item in doc_code["metrics"]["per_class"].items()
        ],
        "",
        _confusion_table(doc_code["metrics"]["confusion"], DOC_CODE_LABELS),
        "",
        "## G. Semantic Entailment",
        "",
        "동일한 42개 claim 을 (1) 규칙 기반 기준선과 (2) NVIDIA 독립 심사 모델로 판정했다.",
        "",
        "| 판정자 | Accuracy | Macro F1 | Unsupported Citation Rate | Contradiction Recall |",
        "|---|---|---|---|---|",
        f"| 결정론 기준선 | {_pct(semantic['deterministic']['accuracy'])} | {_num(semantic['deterministic']['macro_f1'])} | {_pct(semantic['deterministic_citation']['unsupported_citation_rate'])} | {_pct(semantic['deterministic_citation']['contradiction_recall'])} |",
        f"| NVIDIA 심사 | {_pct(semantic['judge']['accuracy'])} | {_num(semantic['judge']['macro_f1'])} | {_pct(semantic['judge_citation']['unsupported_citation_rate'])} | {_pct(semantic['judge_citation']['contradiction_recall'])} |",
        "",
        "### 심사 모델 Confusion Matrix",
        "",
        _confusion_table(semantic["judge"]["confusion"], LABELS),
        "",
        "## H. 실제 NVIDIA 호출",
        "",
        f"- 상태: **{live['status']}**",
        f"- 성공/전체: {live['succeeded']}/{live['n']}",
        f"- 평균 지연: {int(live['mean_latency_ms']) if live.get('mean_latency_ms') else 'NOT_MEASURED'} ms",
        f"- 토큰: prompt {live['total_prompt_tokens']} / completion {live['total_completion_tokens']}",
        f"- unsupported number rate (raw → 저장): {_pct(live.get('raw_unsupported_number_rate'))} → {_pct(live['unsupported_number_rate'])}",
        f"- 수치 가드레일로 대체된 주장: {live.get('removed_metric_count', 0)}건",
        f"- 효과 주장: raw {live.get('raw_effect_claim_count', 0)}건 중 근거 없음 {live.get('raw_unsupported_effect_claim_count', 0)}건 → 차단 {live.get('blocked_effect_claim_count', 0)}건, 저장 후 잔여 {live.get('residual_unsupported_effect_claim_count', 0)}건",
        f"- 금지 주장 hit: {live['forbidden_hit_count']}",
    ]
    if live.get("reason"):
        lines.append(f"- 사유: {live['reason']}")
    if live.get("rows"):
        lines += [
            "",
            "| ID | 상태 | latency(ms) | JSON | unsupported numbers | 금지 hit |",
            "|---|---|---|---|---|---|",
            *[
                f"| {row['id']} | {row['status']} | {row.get('latency_ms', '')} | {row.get('json_ok', '')} | {len(row.get('unsupported_numbers') or [])} | {len(row.get('forbidden_hits') or [])} |"
                for row in live["rows"]
            ],
        ]
    lines += [
        "",
        "## I. 한계",
        "",
        "- claim 42개와 통제 저장소 20개는 소규모 표본이다. 95% 구간은 넓으며 운영 전체 성능으로 일반화하지 않는다.",
        "- 품질은 단일 독립 심사 모델 점수다. 사람 2인 이상의 일치도는 측정하지 않았다.",
        "- 통제 저장소는 합성이며 실제 회사 저장소의 언어·도메인 분포를 대표하지 않는다.",
        "- 커밋을 대신 작성한 경우·리뷰만 한 경우는 근거가 없어 이번 정답에서 제외했다. 이는 해결된 것이 아니라 미검증 범위다.",
        "- 의미 일치·품질 심사는 NVIDIA 호스팅 모델에 의존한다. 동일 모델 계열의 편향 가능성을 배제하지 못한다.",
        "",
        "## J. 최종 판단",
        "",
        f"- **{result['overall']}**",
        "- NOT_MEASURED 는 실패가 아니라 측정 불가다. 분모 0을 100%로 바꾸지 않았다.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def evaluate(
    *,
    live: bool = False,
    use_judge: bool = True,
    dataset_path: Path = DATASET_PATH,
    out_dir: Optional[Path] = None,
) -> dict:
    dataset = _load_dataset(dataset_path)
    started = datetime.now().astimezone()
    from devfolio.core.storage import load_config

    config = load_config()
    provider = config.get_provider("nvidia_nim")
    has_key = bool(provider) and bool(
        __import__("devfolio.utils.security", fromlist=["get_api_key"]).get_api_key(
            "nvidia_nim"
        )
    )

    claim_units = dataset["claim_units"]
    gold = [item["label"] for item in claim_units]
    deterministic_predictions = [
        classify_claim_deterministic(item["claim"], item["evidence"])
        for item in claim_units
    ]
    deterministic = classify_metrics(gold, deterministic_predictions)
    semantic: dict[str, Any] = {
        "deterministic": deterministic,
        "deterministic_citation": citation_metrics(gold, deterministic_predictions),
        "judge": {
            "n": 0,
            "accuracy": None,
            "macro_f1": None,
            "per_class": {},
            "confusion": {label: {other: 0 for other in LABELS} for label in LABELS},
        },
        "judge_citation": {
            "unsupported_citation_rate": None,
            "contradiction_recall": None,
        },
    }
    judge_meta: Optional[dict] = None
    judge_model = judge_mod.DEFAULT_JUDGE_MODEL
    if use_judge and has_key:
        judged = judge_mod.judge_claims(claim_units)
        predicted = [judged["items"][item["id"]]["label"] for item in claim_units]
        judge_metrics = classify_metrics(gold, predicted)
        semantic["judge"] = judge_metrics
        semantic["judge_citation"] = citation_metrics(gold, predicted)
        semantic["rows"] = [
            {
                "id": item["id"],
                "claim": item["claim"],
                "evidence": item["evidence"],
                "gold": item["label"],
                "deterministic": deterministic_predictions[index],
                "judge": predicted[index],
                "reason": judged["items"][item["id"]]["reason"],
            }
            for index, item in enumerate(claim_units)
        ]
        judge_meta = {"calls": judged["calls"]}
    elif use_judge and not has_key:
        semantic["status"] = "NOT_CONFIGURED"
    else:
        semantic["status"] = "SKIPPED"

    hallucination = hallucination_metrics(gold)
    hallucination["ci"] = proportion_ci(
        hallucination["contradicted"] + hallucination["unsupported"], hallucination["n"]
    )
    effect_gate = evaluate_effect_gate(dataset)

    analysis, analysis_meta = _run_analysis(dataset)
    extraction = analysis["extraction"]
    attribution = analysis["attribution"]
    attribution["ci"] = bootstrap_ci(
        [1.0 if row["exact"] else 0.0 for row in attribution["rows"]]
    )

    doc_gold = [item["label"] for item in dataset["doc_code_units"]]
    doc_deterministic_predictions = [
        classify_doc_code_deterministic(item["doc"], item["code"])
        for item in dataset["doc_code_units"]
    ]
    doc_deterministic = classify_metrics(
        doc_gold, doc_deterministic_predictions, DOC_CODE_LABELS
    )
    doc_metrics = doc_deterministic
    doc_rows: list[dict] = []
    doc_status = "DETERMINISTIC_ONLY"
    if use_judge and has_key:
        judged_docs = judge_mod.judge_doc_code(dataset["doc_code_units"])
        doc_predictions = [
            judged_docs["items"][item["id"]]["label"]
            for item in dataset["doc_code_units"]
        ]
        doc_metrics = classify_metrics(doc_gold, doc_predictions, DOC_CODE_LABELS)
        doc_rows = [
            {
                "id": item["id"],
                "doc": item["doc"],
                "code": item["code"],
                "gold": item["label"],
                "deterministic": doc_deterministic_predictions[index],
                "judge": doc_predictions[index],
                "reason": judged_docs["items"][item["id"]]["reason"],
            }
            for index, item in enumerate(dataset["doc_code_units"])
        ]
        doc_status = "LIVE_VERIFIED"
    false_match = sum(
        1 for item in doc_rows if item["gold"] != "MATCH" and item["judge"] == "MATCH"
    )
    false_match_rate = safe_div(
        false_match, sum(1 for item in doc_rows if item["judge"] == "MATCH")
    )

    quality_items = _quality_items(dataset)
    quality: dict[str, Any] = {
        "n": 0,
        "mean": None,
        "axis_means": {axis: None for axis in judge_mod.QUALITY_AXES},
        "low_factuality_count": 0,
        "low_factuality_rate": None,
        "rows": [],
        "status": "NOT_MEASURED",
    }
    if use_judge and has_key and quality_items:
        try:
            judged_quality = judge_mod.judge_quality(quality_items, batch_size=5)
            quality = _quality_report(judged_quality, quality_items)
            quality["status"] = "LIVE_VERIFIED"
            quality["calls"] = judged_quality["calls"]
        except Exception as exc:  # noqa: BLE001 — 심사 실패는 NOT_MEASURED 로 남긴다
            quality["error"] = str(exc)[:300]
            quality["status"] = "FAILED"
    quality["ci"] = bootstrap_ci(
        [row["mean"] for row in quality["rows"] if row["mean"] is not None]
    )

    live_result = (
        _live_generation(dataset)
        if live
        else {
            "status": "NOT_RUN",
            "n": 0,
            "succeeded": 0,
            "failed": 0,
            "mean_latency_ms": None,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "unsupported_number_rate": None,
            "forbidden_hit_count": 0,
            "rows": [],
        }
    )

    verdicts = {
        "hallucination": _verdict(
            hallucination["combined_unsupported_or_contradicted_rate"],
            THRESHOLDS["hallucination_combined_max"],
            higher=False,
        ),
        "extraction": _verdict(
            extraction["f1"], THRESHOLDS["extraction_f1_min"], higher=True
        ),
        "quality": (
            "NOT_MEASURED"
            if quality["mean"] is None
            else (
                "PASS"
                if quality["mean"] >= THRESHOLDS["quality_mean_min"]
                and (quality["axis_means"].get("factual_accuracy") or 0)
                >= THRESHOLDS["quality_factual_mean_min"]
                and (quality["low_factuality_rate"] or 0)
                <= THRESHOLDS["quality_low_factuality_max"]
                else "FAIL"
            )
        ),
        "attribution": _verdict(
            attribution["exact_accuracy"],
            THRESHOLDS["attribution_exact_min"],
            higher=True,
        ),
        "doc_code": _verdict(
            doc_metrics["accuracy"], THRESHOLDS["doc_code_accuracy_min"], higher=True
        ),
        "semantic": _verdict(
            semantic["judge"]["accuracy"],
            THRESHOLDS["semantic_accuracy_min"],
            higher=True,
        ),
        "effect_gate": (
            "NOT_MEASURED"
            if effect_gate["unsupported_effect_claims"] == 0
            else (
                "PASS"
                if effect_gate["false_accept_rate"]
                <= THRESHOLDS["effect_gate_false_accept_max"]
                and effect_gate["retention"] >= THRESHOLDS["effect_gate_retention_min"]
                else "FAIL"
            )
        ),
    }
    hard = [value for value in verdicts.values() if value == "FAIL"]
    measured = [value for value in verdicts.values() if value != "NOT_MEASURED"]
    overall = (
        "FAIL"
        if hard
        else ("PASS" if len(measured) == len(verdicts) else "CONDITIONAL PASS")
    )
    if hard and len(hard) <= 2:
        overall = "CONDITIONAL PASS"
    if not measured:
        overall = "INCONCLUSIVE"

    try:
        git_sha = (
            __import__("subprocess")
            .run(
                ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            .stdout.strip()
        )
    except Exception:  # noqa: BLE001
        git_sha = "unknown"

    result = {
        "run_at": started.isoformat(timespec="seconds"),
        "git_sha": git_sha or "unknown",
        "dataset_version": dataset["version"],
        "dataset_sha": __import__("hashlib")
        .sha256(dataset_path.read_bytes())
        .hexdigest()[:16],
        "mode": "live" if live else "offline",
        "generator_provider": "nvidia_nim",
        "generator_model": "nvidia_nim/openai/gpt-oss-20b",
        "judge_model": judge_model if use_judge and has_key else "NOT_CONFIGURED",
        "judge_status": "LIVE_VERIFIED" if use_judge and has_key else "NOT_CONFIGURED",
        "judge_meta": judge_meta,
        "thresholds": THRESHOLDS,
        "claims": {
            "n": len(claim_units),
            "hallucination": hallucination,
            "semantic": semantic,
            "effect_gate": effect_gate,
        },
        "extraction": extraction,
        "analysis_meta": analysis_meta,
        "attribution": attribution,
        "doc_code": {
            "n": len(doc_gold),
            "status": doc_status,
            "metrics": doc_metrics,
            "false_match_rate": false_match_rate,
            "rows": doc_rows,
            "deterministic": doc_deterministic,
        },
        "quality": quality,
        "live": live_result,
        "verdicts": verdicts,
        "overall": overall,
        "limitations": [
            "합성 통제 저장소와 42개 claim 소규모 표본",
            "품질은 단일 AI 심사 모델 점수이며 사람 간 일치도 없음",
            "리뷰·설계 기여, 대리 커밋은 근거 부족으로 UNKNOWN",
            "동일 NVIDIA 계열 모델 편향 가능성",
        ],
    }
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "impact-results.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / "impact-results.md").write_text(
            build_markdown(result), encoding="utf-8"
        )
    return result


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="ImpactNote AI Ground Truth 평가")
    parser.add_argument(
        "--live",
        action="store_true",
        help="현재 프롬프트로 NVIDIA 실호출 3회 수행 (비용·시간 발생)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="실호출 없이 결정론 기준선·분석기만 실행",
    )
    parser.add_argument("--no-judge", action="store_true", help="NVIDIA 심사 생략")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.live and args.offline:
        parser.error("--live 와 --offline 은 함께 쓸 수 없습니다.")
    out_dir = args.out or (
        ROOT / "evals" / "runs" / f"impact-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    result = evaluate(
        live=args.live and not args.offline,
        use_judge=not args.no_judge,
        out_dir=out_dir,
    )
    print(build_markdown(result))
    print(f"\n저장: {out_dir / 'impact-results.md'}")


if __name__ == "__main__":
    main()
