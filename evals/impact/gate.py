"""정성 효과 Hard Gate 의 Ground Truth 평가.

42개 고정 claim 중 "효과 주장"으로 탐지된 것만 대상으로 한다.
효과 주장이 아닌 사실·수치 claim 은 이 Gate 의 적용 대상이 아니므로
분모에서 제외하고, coverage 를 함께 보고한다(과대 해석 방지).
"""

from __future__ import annotations

from typing import Any

from evals.impact.metrics import safe_div, wilson_interval
from impactnote.core.claims import verify_effect_claim


def evaluate_effect_gate(dataset: dict) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for unit in dataset["claim_units"]:
        verdict = verify_effect_claim(unit["claim"], [unit["evidence"]])
        if verdict is None:
            continue
        gold_supported = unit["label"] == "ENTAILMENT"
        rows.append(
            {
                "id": unit["id"],
                "claim": unit["claim"],
                "evidence": unit["evidence"],
                "gold": unit["label"],
                "gold_supported": gold_supported,
                "category": verdict.category,
                "accepted": verdict.supported,
                "reason": verdict.reason,
            }
        )

    total = len(dataset["claim_units"])
    supported = [row for row in rows if row["gold_supported"]]
    unsupported = [row for row in rows if not row["gold_supported"]]
    false_accepts = [row for row in unsupported if row["accepted"]]
    false_rejections = [row for row in supported if not row["accepted"]]
    accepted = [row for row in rows if row["accepted"]]

    return {
        "n_total_claims": total,
        "n_effect_claims": len(rows),
        "coverage": safe_div(len(rows), total),
        "accepted": len(accepted),
        "blocked": len(rows) - len(accepted),
        "supported_effect_claims": len(supported),
        "unsupported_effect_claims": len(unsupported),
        "false_accepts": len(false_accepts),
        "false_rejections": len(false_rejections),
        "false_accept_rate": safe_div(len(false_accepts), len(unsupported)),
        "blocked_unsupported_rate": safe_div(
            len(unsupported) - len(false_accepts), len(unsupported)
        ),
        "retention": safe_div(len(supported) - len(false_rejections), len(supported)),
        "accepted_precision": safe_div(
            len(supported) - len(false_rejections), len(accepted)
        ),
        "false_accept_ci": wilson_interval(len(false_accepts), len(unsupported)),
        "false_accept_ids": [row["id"] for row in false_accepts],
        "false_rejection_ids": [row["id"] for row in false_rejections],
        "rows": rows,
    }


__all__ = ["evaluate_effect_gate"]
