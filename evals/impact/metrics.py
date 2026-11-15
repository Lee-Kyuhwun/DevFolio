"""ImpactNote AI 평가의 분모·분자와 신뢰구간 계산.

이 모듈은 데이터를 읽지 않는다. 입력은 항상 (정답, 예측) 쌍이며,
분모가 0인 경우 None 을 돌려준다. None 을 100% 로 바꾸지 않는다.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from typing import Iterable, Optional, Sequence

LABELS = (
    "ENTAILMENT",
    "CONTRADICTION",
    "NEUTRAL",
    "INSUFFICIENT_EVIDENCE",
)
DOC_CODE_LABELS = (
    "MATCH",
    "PARTIAL_MATCH",
    "MISMATCH",
    "NOT_IMPLEMENTED",
    "INSUFFICIENT_EVIDENCE",
)
UNSUPPORTED_LABELS = frozenset({"CONTRADICTION", "NEUTRAL", "INSUFFICIENT_EVIDENCE"})


def safe_div(numerator: float, denominator: float) -> Optional[float]:
    if denominator == 0:
        return None
    return numerator / denominator


def prf(tp: int, fp: int, fn: int) -> dict[str, Optional[float]]:
    """Precision/Recall/F1. 분모가 0이면 해당 값은 None."""
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    if precision is None or recall is None or precision + recall == 0:
        f1 = None if precision is None or recall is None else 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def classify_metrics(
    gold: Sequence[str], predicted: Sequence[str], labels: Sequence[str] = LABELS
) -> dict:
    """다중 분류 정확도·클래스별 P/R/F1·confusion matrix.

    gold/predicted 는 같은 길이여야 한다. 알 수 없는 레이블은 ValueError.
    """
    if len(gold) != len(predicted):
        raise ValueError("gold 와 predicted 길이가 다릅니다.")
    allowed = set(labels)
    for value in [*gold, *predicted]:
        if value not in allowed:
            raise ValueError(f"알 수 없는 레이블: {value}")

    total = len(gold)
    correct = sum(
        1
        for expected, actual in zip(gold, predicted, strict=True)
        if expected == actual
    )
    confusion = {expected: {actual: 0 for actual in labels} for expected in labels}
    for expected, actual in zip(gold, predicted, strict=True):
        confusion[expected][actual] += 1

    per_class: dict[str, dict] = {}
    for label in labels:
        tp = sum(
            1
            for expected, actual in zip(gold, predicted, strict=True)
            if expected == label and actual == label
        )
        fp = sum(
            1
            for expected, actual in zip(gold, predicted, strict=True)
            if expected != label and actual == label
        )
        fn = sum(
            1
            for expected, actual in zip(gold, predicted, strict=True)
            if expected == label and actual != label
        )
        support = sum(1 for expected in gold if expected == label)
        per_class[label] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "support": support,
            **prf(tp, fp, fn),
        }

    defined_f1 = [item["f1"] for item in per_class.values() if item["f1"] is not None]
    return {
        "n": total,
        "accuracy": safe_div(correct, total),
        "macro_f1": sum(defined_f1) / len(defined_f1) if defined_f1 else None,
        "per_class": per_class,
        "confusion": confusion,
        "predicted_distribution": dict(Counter(predicted)),
        "gold_distribution": dict(Counter(gold)),
    }


def binary_metrics(gold: Sequence[bool], predicted: Sequence[bool]) -> dict:
    if len(gold) != len(predicted):
        raise ValueError("gold 와 predicted 길이가 다릅니다.")
    tp = sum(
        1
        for expected, actual in zip(gold, predicted, strict=True)
        if expected and actual
    )
    fp = sum(
        1
        for expected, actual in zip(gold, predicted, strict=True)
        if not expected and actual
    )
    fn = sum(
        1
        for expected, actual in zip(gold, predicted, strict=True)
        if expected and not actual
    )
    tn = len(gold) - tp - fp - fn
    return {"n": len(gold), "tp": tp, "fp": fp, "fn": fn, "tn": tn, **prf(tp, fp, fn)}


def hallucination_metrics(gold: Sequence[str]) -> dict:
    """Ground Truth 레이블만으로 hallucination 비율을 계산한다.

    - Supported: ENTAILMENT
    - Contradiction Rate: CONTRADICTION / N
    - Unsupported Claim Rate: NEUTRAL + INSUFFICIENT_EVIDENCE / N
    - Combined: (CONTRADICTION + NEUTRAL + INSUFFICIENT_EVIDENCE) / N
    """
    total = len(gold)
    counts = Counter(gold)
    contradiction = counts["CONTRADICTION"]
    unsupported = counts["NEUTRAL"] + counts["INSUFFICIENT_EVIDENCE"]
    supported = counts["ENTAILMENT"]
    return {
        "n": total,
        "supported": supported,
        "contradicted": contradiction,
        "unsupported": unsupported,
        "contradiction_rate": safe_div(contradiction, total),
        "unsupported_claim_rate": safe_div(unsupported, total),
        "combined_unsupported_or_contradicted_rate": safe_div(
            contradiction + unsupported, total
        ),
        "entailment_rate": safe_div(supported, total),
    }


def citation_metrics(gold: Sequence[str], predicted: Sequence[str]) -> dict:
    """인용이 실제로 주장을 뒷받침하는 비율.

    Unsupported Citation Rate = (predicted ENTAILMENT & gold != ENTAILMENT) /
    predicted ENTAILMENT. 분모가 0이면 None.
    """
    cited = sum(1 for value in predicted if value == "ENTAILMENT")
    wrong = sum(
        1
        for expected, actual in zip(gold, predicted, strict=True)
        if actual == "ENTAILMENT" and expected != "ENTAILMENT"
    )
    contradiction_total = sum(1 for value in gold if value == "CONTRADICTION")
    contradiction_hit = sum(
        1
        for expected, actual in zip(gold, predicted, strict=True)
        if expected == "CONTRADICTION" and actual == "CONTRADICTION"
    )
    return {
        "predicted_entailment": cited,
        "unsupported_citation_rate": safe_div(wrong, cited),
        "contradiction_recall": safe_div(contradiction_hit, contradiction_total),
    }


def bootstrap_ci(
    values: Sequence[float],
    *,
    statistic: str = "mean",
    samples: int = 1000,
    seed: int = 20261115,
    confidence: float = 0.95,
) -> Optional[tuple[float, float]]:
    """부트스트랩 신뢰구간. 표본이 1개 이하이거나 값이 없으면 None."""
    cleaned = [float(value) for value in values if value is not None]
    if len(cleaned) < 2:
        return None
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(samples):
        resample = [cleaned[rng.randrange(len(cleaned))] for _ in cleaned]
        if statistic == "mean":
            estimates.append(sum(resample) / len(resample))
        elif statistic == "accuracy":
            estimates.append(sum(resample) / len(resample))
        else:
            raise ValueError(f"지원하지 않는 statistic: {statistic}")
    estimates.sort()
    alpha = (1 - confidence) / 2
    low_index = max(0, int(math.floor(alpha * samples)) - 1)
    high_index = min(samples - 1, int(math.ceil((1 - alpha) * samples)) - 1)
    return estimates[low_index], estimates[high_index]


def proportion_ci(
    successes: int, total: int, *, samples: int = 1000, seed: int = 20261115
) -> Optional[tuple[float, float]]:
    if total <= 0:
        return None
    values = [1.0] * successes + [0.0] * (total - successes)
    return bootstrap_ci(values, samples=samples, seed=seed)


def wilson_interval(
    successes: int, total: int, *, z: float = 1.96
) -> Optional[tuple[float, float]]:
    """비율의 Wilson 95% 구간.

    percentile bootstrap 은 0/n·n/n 경계에서 구간이 0–0 으로 붕괴해
    "오류 0건 = 오류율 0%" 로 오독되게 한다. 소표본 비율에는 Wilson 을 쓴다.
    """
    if total <= 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = (
        z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    )
    return (max(0.0, center - margin), min(1.0, center + margin))


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    cleaned = [float(value) for value in values if value is not None]
    return sum(cleaned) / len(cleaned) if cleaned else None


__all__ = [
    "DOC_CODE_LABELS",
    "LABELS",
    "UNSUPPORTED_LABELS",
    "binary_metrics",
    "bootstrap_ci",
    "citation_metrics",
    "classify_metrics",
    "hallucination_metrics",
    "mean",
    "prf",
    "proportion_ci",
    "safe_div",
    "wilson_interval",
]
