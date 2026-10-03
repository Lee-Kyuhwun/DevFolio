"""보고서: 라벨된 항목만 비교하고, 사전 등록 규칙으로 판정하고, 전략 변경을 경고한다."""

from evals.report import build_report


def _out(oid, strategy, resolved, passed, factuality=4, naturalness=4, error=None):
    return {
        "output_id": oid,
        "case_id": oid.split(":")[0],
        "strategy": strategy,
        "resolved_strategy": resolved,
        "text": "요약",
        "judge_scores": {"factuality": factuality, "naturalness": naturalness},
        "judge_passed": passed,
        "calls": 4,
        "latency_ms": 1000,
        "error": error,
    }


def _label(oid, has_unsupported=False, naturalness=4, usability="as_is"):
    return {
        "output_id": oid,
        "has_unsupported": has_unsupported,
        "unsupported_text": "",
        "naturalness": naturalness,
        "usability": usability,
    }


def test_report_uses_only_labeled_rows_and_shows_n():
    outputs = [_out(f"c{i}:single", "single", "single", True) for i in range(4)]
    labels = [_label(f"c{i}:single") for i in range(3)]

    md = build_report(outputs, labels)

    assert "라벨 3 / 전체 4" in md
    assert "라벨 누락 1건" in md


def test_report_applies_decision_and_flags_resolved_strategy():
    outputs = [
        _out("a:single", "single", "single", False),
        _out("b:single", "single", "single", False),
        _out("c:hybrid", "hybrid", "single", True),
        _out("d:single", "single", "single", True, error="모든 provider 실패"),
    ]
    labels = [
        _label("a:single", has_unsupported=True),  # 심사 factuality 4 → 놓침
        _label("b:single"),
        _label("c:hybrid"),
    ]

    md = build_report(outputs, labels)

    assert "| pass | human_required |" in md  # 사람 as_is 3건 중 심사 통과 1건
    assert "| factuality | human_required |" in md  # 놓친 비율 100%
    assert "| naturalness | auto |" in md
    assert "hybrid → single" in md
    assert "오류 1건" in md


def test_report_states_selection_bias_limitation():
    md = build_report(
        [_out("a:single", "single", "single", True)], [_label("a:single")]
    )

    assert "심사 모델이 고른 후보" in md


def test_report_handles_factuality_only_labels():
    outputs = [
        _out("a:single", "single", "single", True),
        _out("b:single", "single", "single", True),
    ]
    labels = [
        {"output_id": "a:single", "has_unsupported": True, "unsupported_text": "3배"},
        {"output_id": "b:single", "has_unsupported": False, "unsupported_text": ""},
    ]

    md = build_report(outputs, labels)

    assert "| factuality | human_required |" in md  # 놓친 비율 100%
    assert "| naturalness | undetermined |" in md
    assert "| pass | undetermined |" in md


def test_report_warns_when_labels_are_straight_lined():
    outputs = [_out(f"c{i}:single", "single", "single", True) for i in range(10)]
    labels = [
        _label(f"c{i}:single", naturalness=1, usability="as_is") for i in range(10)
    ]

    md = build_report(outputs, labels)

    assert "같은 답" in md


def test_report_says_auto_is_weak_when_humans_found_no_unsupported_facts():
    outputs = [_out(f"c{i}:single", "single", "single", True) for i in range(3)]
    labels = [
        {"output_id": f"c{i}:single", "has_unsupported": False, "unsupported_text": ""}
        for i in range(3)
    ]

    md = build_report(outputs, labels)

    assert "| factuality | auto |" in md
    assert "측정할 수 없다" in md
