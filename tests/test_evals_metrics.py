"""심사 신뢰도 측정의 통계 함수와 사전 등록 판정 규칙."""

import pytest

from evals.metrics import agreement, cohen_kappa, decide, miss_rate, recall_precision


def test_agreement_and_kappa():
    pairs = [(True, True), (True, False), (False, False), (False, False)]
    assert agreement(pairs) == 0.75
    assert cohen_kappa(pairs) == pytest.approx(0.5)


def test_kappa_undefined_when_all_same():
    assert cohen_kappa([(True, True), (True, True)]) is None


def test_empty_inputs_are_undefined():
    assert agreement([]) is None
    assert cohen_kappa([]) is None
    assert miss_rate([], []) is None


def test_miss_rate_and_recall_precision():
    assert miss_rate([True, True, False], [True, False, False]) == 0.5
    assert recall_precision([True, True, False], [True, False, True]) == (0.5, 0.5)


def test_miss_rate_undefined_without_positive_truth():
    assert miss_rate([False, False], [True, False]) is None


def test_decide_applies_preregistered_thresholds():
    assert decide(
        {"naturalness": 0.80, "pass": 0.79, "factuality": None}, factuality_miss=0.11
    ) == {
        "naturalness": "auto",
        "pass": "human_required",
        "factuality": "human_required",
    }
    assert decide({"factuality": 0.9}, factuality_miss=None)["factuality"] == "auto"
    assert decide({"pass": None}, factuality_miss=None)["pass"] == "undetermined"
