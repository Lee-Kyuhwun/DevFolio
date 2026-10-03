"""블라인드 라벨링: 전략명·심사 점수를 숨기고, 중단 후 이어서 할 수 있어야 한다."""

from evals.label import label_one, pending_items

ROWS = [
    {"output_id": "a:single", "text": "가", "error": None},
    {"output_id": "a:hybrid", "text": "나", "error": None},
    {"output_id": "b:single", "text": "다", "error": None},
    {"output_id": "c:single", "text": "", "error": "모든 provider 실패"},
]

ITEM = {
    "output_id": "a:hybrid",
    "strategy": "hybrid",
    "resolved_strategy": "hybrid",
    "text": "배포 시간을 3배 줄였다.",
    "judge_scores": {"factuality": 2},
    "judge_passed": False,
    "error": None,
}


def _asker(answers: list[str], shown: list[str]):
    it = iter(answers)
    return lambda prompt: shown.append(prompt) or next(it)


def test_pending_items_skips_labeled_and_errors_and_is_stable():
    pending = pending_items(ROWS, {"a:single"}, "run1")

    assert sorted(i["output_id"] for i in pending) == ["a:hybrid", "b:single"]
    assert pending == pending_items(ROWS, {"a:single"}, "run1")


def test_label_one_hides_strategy_scores_and_id():
    shown: list[str] = []
    label = label_one(ITEM, "요약", _asker(["y", "3배", "4", "2"], shown))

    assert label == {
        "output_id": "a:hybrid",
        "has_unsupported": True,
        "unsupported_text": "3배",
        "naturalness": 4,
        "usability": "needs_edit",
    }
    assert "배포 시간을 3배 줄였다." in shown[0]
    assert not any("hybrid" in p or "factuality" in p or "a:" in p for p in shown)


def test_label_one_reasks_invalid_answers_and_skips_text_when_no():
    shown: list[str] = []
    label = label_one(ITEM, "요약", _asker(["maybe", "n", "9", "5", "0", "1"], shown))

    assert label["has_unsupported"] is False and label["unsupported_text"] == ""
    assert label["naturalness"] == 5 and label["usability"] == "as_is"


def test_evidence_summary_shows_what_the_models_saw():
    from devfolio.models.project import Project
    from evals.label import evidence_summary

    # team_size=1 is the model default; the generation prompt still includes it
    summary = evidence_summary(Project(id="p", name="프로젝트", team_size=1))

    assert '"team_size": 1' in summary


def test_naturalness_prompt_states_scale_direction():
    shown: list[str] = []
    label_one(ITEM, "요약", _asker(["n", "4", "1"], shown))

    assert any("1=매우 어색" in p and "5=매우 자연스러움" in p for p in shown)


def test_unsupported_text_is_required_when_yes():
    label = label_one(ITEM, "요약", _asker(["y", "", "3배", "4", "2"], []))

    assert label["unsupported_text"] == "3배"


def test_factuality_only_mode_asks_one_question():
    label = label_one(ITEM, "요약", _asker(["y", "3배"], []), only="factuality")

    assert label == {
        "output_id": "a:hybrid",
        "has_unsupported": True,
        "unsupported_text": "3배",
    }
