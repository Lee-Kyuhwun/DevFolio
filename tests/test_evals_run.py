"""심사 신뢰도 측정 실행기 (실제 AI 호출 없음)."""

import json
from unittest.mock import patch

from devfolio.core.ai_service import AIService
from devfolio.exceptions import DevfolioAIError
from devfolio.models.config import Config
from evals.run import STRATEGIES, estimate_max_calls, load_cases, run_eval

SUMMARY = (
    "결제 서비스의 배포 자동화를 맡았다. 배포 절차를 스크립트로 정리했다. "
    "장애 대응 문서를 만들었다. 팀의 리뷰 규칙을 정했다. 운영 지표를 매주 공유했다."
)


def _review(passed: bool, factuality: int = 4) -> str:
    scores = {
        "factuality": factuality,
        "specificity": 4,
        "result_orientation": 4,
        "hiring_relevance": 4,
        "redundancy": 4,
        "output_contract": 4,
        "naturalness": 4,
    }
    return json.dumps(
        {"pass": passed, "scores": scores, "issues": []}, ensure_ascii=False
    )


def _fake_ai(review_text: str, fail_on: str | None = None):
    def call(self, messages, *args, **kwargs):
        content = "\n".join(m["content"] for m in messages)
        if fail_on and fail_on in content:
            raise DevfolioAIError("모든 provider 실패")
        return review_text if "factuality" in content else SUMMARY

    return call


def _write_case(directory, stem: str, name: str) -> None:
    (directory / f"{stem}.yaml").write_text(
        f"id: {stem}\nname: {name}\nrole: 백엔드 개발자\n"
        "one_line_summary: 배포 절차 자동화\n",
        encoding="utf-8",
    )


def _rows(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_run_eval_writes_row_per_case_and_strategy(tmp_path):
    _write_case(tmp_path, "sample_case", "샘플 프로젝트")
    with patch.object(AIService, "_call_messages", _fake_ai(_review(True))):
        out = run_eval(
            load_cases(tmp_path),
            ["single", "best_of_n"],
            Config(),
            "pollinations",
            tmp_path / "run",
        )

    rows = _rows(out)
    assert [r["output_id"] for r in rows] == [
        "sample_case:single",
        "sample_case:best_of_n",
    ]
    assert rows[1]["resolved_strategy"] == "best_of_n" and rows[1]["calls"] >= 2
    assert rows[0]["text"] == SUMMARY and rows[0]["judge_scores"]["factuality"] == 4


def test_failed_case_records_error_and_continues(tmp_path):
    _write_case(tmp_path, "a_fail", "실패 프로젝트")
    _write_case(tmp_path, "b_ok", "정상 프로젝트")
    with patch.object(
        AIService, "_call_messages", _fake_ai(_review(True), fail_on="실패 프로젝트")
    ):
        out = run_eval(
            load_cases(tmp_path), ["single"], Config(), "pollinations", tmp_path / "run"
        )

    rows = _rows(out)
    assert rows[0]["error"] and rows[1]["error"] is None


def test_judge_rejected_candidate_is_still_recorded(tmp_path):
    _write_case(tmp_path, "sample_case", "샘플 프로젝트")
    with patch.object(
        AIService, "_call_messages", _fake_ai(_review(False, factuality=2))
    ):
        out = run_eval(
            load_cases(tmp_path), ["single"], Config(), "pollinations", tmp_path / "run"
        )

    rows = _rows(out)
    assert (
        rows[0]["judge_passed"] is False
        and rows[0]["error"] is None
        and rows[0]["text"]
    )


def test_estimate_max_calls():
    assert estimate_max_calls(5, list(STRATEGIES)) == 170


def test_sample_case_is_loadable():
    from pathlib import Path

    cases = load_cases(Path("evals/examples"))
    assert [case_id for case_id, _ in cases] == ["sample_case"]


def test_run_sends_only_to_the_chosen_provider():
    from devfolio.models.config import AIProviderConfig, ReasoningConfig
    from evals.run import _config_for

    config = Config(
        default_ai_provider="anthropic",
        ai_providers=[
            AIProviderConfig(name="anthropic", model="claude-x", key_stored=True)
        ],
        reasoning=ReasoningConfig(judge_provider="anthropic"),
    )

    cfg = _config_for(config, "single", "pollinations")

    chain = AIService(cfg)._provider_fallback_chain("pollinations")
    assert [p.name for p in chain] == ["pollinations"]
    assert cfg.reasoning.judge_provider == ""


def test_row_records_provider(tmp_path):
    _write_case(tmp_path, "sample_case", "샘플 프로젝트")
    with patch.object(AIService, "_call_messages", _fake_ai(_review(True))):
        out = run_eval(
            load_cases(tmp_path), ["single"], Config(), "pollinations", tmp_path / "run"
        )

    assert _rows(out)[0]["provider"] == "pollinations"


def test_run_never_falls_back_to_builtin_pollinations():
    from devfolio.models.config import AIProviderConfig
    from evals.run import CountingAIService, _config_for

    config = Config(
        default_ai_provider="gemini",
        ai_providers=[
            AIProviderConfig(name="gemini", model="gemini-2.5-flash", key_stored=True)
        ],
    )

    service = CountingAIService(_config_for(config, "single", "gemini"))

    assert [p.name for p in service._provider_fallback_chain("gemini")] == ["gemini"]


def test_model_is_pinned_without_silent_model_fallback():
    from devfolio.models.config import AIProviderConfig
    from evals.run import CountingAIService, _config_for

    config = Config(
        default_ai_provider="gemini",
        ai_providers=[
            AIProviderConfig(name="gemini", model="gemini-2.5-flash", key_stored=True)
        ],
    )

    cfg = _config_for(config, "single", "gemini", model="gemini-3-flash-preview")
    service = CountingAIService(cfg)

    assert service._runtime_model_candidates(cfg.ai_providers[0]) == [
        "gemini-3-flash-preview"
    ]
    assert config.ai_providers[0].model == "gemini-2.5-flash"  # 사용자 설정은 그대로


def test_resume_reruns_only_failed_outputs(tmp_path):
    _write_case(tmp_path, "sample_case", "샘플 프로젝트")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "outputs.jsonl").write_text(
        json.dumps(
            {"output_id": "sample_case:single", "error": None, "text": "기존"},
            ensure_ascii=False,
        )
        + "\n"
        + json.dumps(
            {"output_id": "sample_case:best_of_n", "error": "503"}, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )

    with patch.object(AIService, "_call_messages", _fake_ai(_review(True))):
        run_eval(
            load_cases(tmp_path),
            ["single", "best_of_n"],
            Config(),
            "pollinations",
            run_dir,
            resume=True,
        )

    rows = _rows(run_dir / "outputs.jsonl")
    assert [r["output_id"] for r in rows] == [
        "sample_case:single",
        "sample_case:best_of_n",
        "sample_case:best_of_n",
    ]
    assert rows[-1]["error"] is None


def test_latest_row_per_output_wins():
    from evals.label import latest_rows

    rows = [
        {"output_id": "a:single", "error": "503"},
        {"output_id": "b:single", "error": None},
        {"output_id": "a:single", "error": None, "text": "재실행"},
    ]

    assert latest_rows(rows) == [
        {"output_id": "a:single", "error": None, "text": "재실행"},
        {"output_id": "b:single", "error": None},
    ]
