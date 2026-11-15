"""ImpactNote AI 평가 하네스와 평가에서 발견한 회귀 결함."""

from __future__ import annotations

import tempfile
from pathlib import Path

from evals.impact import judge
from evals.impact.fixture import build_fixture
from evals.impact.metrics import (
    classify_metrics,
    hallucination_metrics,
    proportion_ci,
)
from evals.impact.run import (
    _load_dataset,
    classify_claim_deterministic,
)
from impactnote.core.intel.engine import _pattern_present, analyze_project
from impactnote.core.store import JsonStore


def test_dataset_has_enough_units_and_valid_labels():
    dataset = _load_dataset()
    total = (
        len(dataset["claim_units"])
        + len(dataset["doc_code_units"])
        + len(dataset["achievement_units"])
        + len(dataset["attribution_units"])
    )
    assert total >= 50
    assert len(dataset["claim_units"]) == 42
    assert all(item["label"] in judge.SINGLE_LABELS for item in dataset["claim_units"])
    assert all(item["label"] in judge.DOC_LABELS for item in dataset["doc_code_units"])


def test_classification_metrics_do_not_invent_perfect_score_without_samples():
    result = classify_metrics(["ENTAILMENT"], ["ENTAILMENT"])
    assert result["accuracy"] == 1.0
    assert result["per_class"]["CONTRADICTION"]["precision"] is None
    assert result["per_class"]["CONTRADICTION"]["recall"] is None
    assert proportion_ci(0, 0) is None


def test_hallucination_separates_contradiction_and_unsupported():
    result = hallucination_metrics(
        [
            "ENTAILMENT",
            "CONTRADICTION",
            "NEUTRAL",
            "INSUFFICIENT_EVIDENCE",
        ]
    )
    assert result["contradiction_rate"] == 0.25
    assert result["unsupported_claim_rate"] == 0.5
    assert result["combined_unsupported_or_contradicted_rate"] == 0.75


def test_numeric_guardrail_reaches_nested_statements():
    from impactnote.core.metrics import sanitize_ai_result

    cleaned, removed = sanitize_ai_result(
        {
            "result": "p95 200ms → 80ms",
            "statements": {"monthly": "응답 시간을 60% 개선했다."},
            "contribution": {"decisions": ["TTL을 60분으로 설정"]},
        },
        ["p95 200ms → 80ms", "TTL 5분"],
    )
    assert cleaned["result"] == "p95 200ms → 80ms"
    assert cleaned["statements"]["monthly"] == "응답 시간을 [확인 필요] 개선했다."
    assert cleaned["contribution"]["decisions"] == ["TTL을 [확인 필요]으로 설정"]
    assert {item["field"] for item in removed} == {
        "statements.monthly",
        "contribution.decisions[0]",
    }


def test_deterministic_claim_flags_number_without_benchmark_as_unsupported():
    assert (
        classify_claim_deterministic(
            "캐싱으로 응답 시간이 70% 단축되었다.",
            "cache.py에 lru_cache를 추가했다. 성능 벤치마크는 없다.",
        )
        == "NEUTRAL"
    )
    assert (
        classify_claim_deterministic(
            "API rate limit은 100 rpm이다.",
            "config.py의 RATE_LIMIT은 50 rpm이다.",
        )
        == "CONTRADICTION"
    )


def test_category_short_patterns_do_not_match_inside_asyncio():
    assert _pattern_present("import asyncio", "ci") is False
    assert _pattern_present("path: .github/workflows/ci.yml", "ci") is True


def test_nvidia_model_prefix_is_added_once():
    from devfolio.core.ai_service import (
        AIService,
        normalize_provider_model_name,
    )

    assert (
        AIService._provider_model_string("nvidia_nim", "openai/gpt-oss-20b")
        == "nvidia_nim/openai/gpt-oss-20b"
    )
    assert (
        AIService._provider_model_string("nvidia_nim", "nvidia_nim/openai/gpt-oss-20b")
        == "nvidia_nim/openai/gpt-oss-20b"
    )
    assert (
        normalize_provider_model_name("nvidia_nim", "nvidia_nim/openai/gpt-oss-20b")
        == "openai/gpt-oss-20b"
    )


def test_fixture_extracts_achievements_and_coauthor_attribution():
    temp = Path(tempfile.mkdtemp(prefix="impactnote-eval-test-"))
    repo = temp / "repo"
    try:
        build_fixture(repo)
        analysis = analyze_project(
            str(repo),
            author_email="alice@example.com",
            use_ai=False,
            force=True,
            store=JsonStore(temp / "data"),
        )
    finally:
        import shutil

        shutil.rmtree(temp, ignore_errors=True)

    titles = {candidate.title for candidate in analysis.candidates}
    assert "배포·자동화: Dockerfile" in titles
    assert "관측성: app/metrics.py" in titles
    assert not any("legacy" in title for title in titles)

    session = next(
        candidate
        for candidate in analysis.candidates
        if "app/session.py" in candidate.title
    )
    emails = {author["email"] for author in session.contribution["authors"]}
    assert emails == {"alice@example.com", "bob@example.com"}


def test_wilson_interval_does_not_collapse_at_zero():
    from evals.impact.metrics import wilson_interval

    low, high = wilson_interval(0, 12)
    assert low == 0.0
    assert 0.2 < high < 0.3
    low, high = wilson_interval(12, 12)
    assert 0.7 < low < 0.8
    assert high == 1.0
    assert wilson_interval(0, 0) is None
