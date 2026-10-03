"""심사 모델과 사람 판정을 비교하는 통계 함수와, 데이터를 보기 전에 정한 판정 규칙."""

from __future__ import annotations

# 사전 등록 판정 규칙 (2026-10-03, 측정 전에 고정). 결과를 본 뒤 바꾸지 않는다.
AGREEMENT_THRESHOLD = 0.80  # 사람과의 일치율이 이 값 이상이면 심사 모델 자동 판정 유지
FACTUALITY_MISS_THRESHOLD = (
    0.10  # 근거 없는 사실을 놓친 비율이 이 값을 넘으면 사람 확인 필수
)

AUTO = "auto"
HUMAN_REQUIRED = "human_required"
UNDETERMINED = "undetermined"


def agreement(pairs: list[tuple[bool, bool]]) -> float | None:
    """(사람, 심사 모델) 판정 쌍에서 둘이 같은 비율."""
    if not pairs:
        return None
    return sum(1 for human, judge in pairs if human == judge) / len(pairs)


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    """우연히 일치할 확률을 뺀 일치도. 기대 일치도가 1이면(모두 같은 값) 계산할 수 없다."""
    observed = agreement(pairs)
    if observed is None:
        return None
    n = len(pairs)
    human_true = sum(1 for human, _ in pairs if human) / n
    judge_true = sum(1 for _, judge in pairs if judge) / n
    expected = human_true * judge_true + (1 - human_true) * (1 - judge_true)
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def miss_rate(truth: list[bool], predicted: list[bool]) -> float | None:
    """truth가 True인 것 중 predicted가 False인 비율 (놓친 비율)."""
    positives = [p for t, p in zip(truth, predicted, strict=True) if t]
    if not positives:
        return None
    return sum(1 for p in positives if not p) / len(positives)


def recall_precision(
    truth: list[bool], predicted: list[bool]
) -> tuple[float | None, float | None]:
    tp = sum(1 for t, p in zip(truth, predicted, strict=True) if t and p)
    fn = sum(1 for t, p in zip(truth, predicted, strict=True) if t and not p)
    fp = sum(1 for t, p in zip(truth, predicted, strict=True) if not t and p)
    recall = tp / (tp + fn) if tp + fn else None
    precision = tp / (tp + fp) if tp + fp else None
    return recall, precision


def decide(
    agreements: dict[str, float | None], factuality_miss: float | None
) -> dict[str, str]:
    """항목별로 심사 모델에 맡길지(auto), 사람이 확인해야 할지(human_required) 정한다."""
    decisions: dict[str, str] = {}
    for axis, value in agreements.items():
        if value is None:
            decisions[axis] = UNDETERMINED
        else:
            decisions[axis] = AUTO if value >= AGREEMENT_THRESHOLD else HUMAN_REQUIRED
    if factuality_miss is not None and factuality_miss > FACTUALITY_MISS_THRESHOLD:
        decisions["factuality"] = HUMAN_REQUIRED
    return decisions
