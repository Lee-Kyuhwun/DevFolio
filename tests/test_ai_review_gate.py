"""Generation must return the exact draft that passed both review and format checks."""

import json
from unittest.mock import Mock

import pytest

from devfolio.core.ai_service import AIService, GenerationProfile, PortfolioEvidence
from devfolio.exceptions import DevfolioAIError
from devfolio.models.config import Config


def review_payload(*, passed=True, score=5, **overrides):
    scores = {
        "factuality": score,
        "specificity": score,
        "result_orientation": score,
        "hiring_relevance": score,
        "redundancy": score,
        "output_contract": score,
        "naturalness": max(4, score),
    }
    scores.update(overrides)
    return json.dumps(
        {"pass": passed, "scores": scores, "issues": []}, ensure_ascii=False
    )


ORIGINAL = "- 초안 하나\n- 초안 둘\n- 초안 셋\n- 초안 넷"
REVISED = "- 수정 하나\n- 수정 둘\n- 수정 셋\n- 수정 넷"


def generate(service):
    return service.generate_with_review(
        evidence=PortfolioEvidence(name="검증 프로젝트"),
        profile=GenerationProfile(mode="resume_bullets"),
    )


def test_final_revision_is_reviewed_and_returns_its_own_review():
    service = AIService(Config())
    service._call_messages = Mock(
        side_effect=[
            ORIGINAL,
            review_payload(passed=False, score=2),
            REVISED,
            review_payload(score=4),
        ]
    )

    text, review = generate(service)

    assert text == REVISED
    assert review.passed
    assert review.scores["factuality"] == 4
    assert REVISED in service._call_messages.call_args.args[0][1]["content"]


@pytest.mark.parametrize(
    "final_review", [review_payload(passed=False), '{"pass": true}']
)
def test_final_revision_that_fails_review_is_not_returned_as_success(final_review):
    service = AIService(Config())
    service._call_messages = Mock(
        side_effect=[
            ORIGINAL,
            review_payload(passed=False),
            REVISED,
            final_review,
        ]
    )

    with pytest.raises(DevfolioAIError, match="심사"):
        generate(service)


@pytest.mark.parametrize(
    ("rejected_text", "rejected_review"),
    [
        ("- 형식 위반", review_payload()),
        (ORIGINAL, review_payload(passed=False)),
        (ORIGINAL, review_payload(factuality=1)),
        (ORIGINAL, review_payload(naturalness=3)),
    ],
)
def test_passing_candidate_wins_over_higher_scoring_rejected_candidate(
    rejected_text, rejected_review
):
    service = AIService(Config())
    service.config.reasoning.strategy = "best_of_n"
    service.config.reasoning.samples = 2
    service._call_messages = Mock(
        side_effect=[
            rejected_text,
            rejected_review,
            REVISED,
            review_payload(score=3),
            ORIGINAL,
            review_payload(),
        ]
    )

    text, review = generate(service)

    assert text == REVISED
    assert review.passed


@pytest.mark.parametrize(
    "malformed_review",
    [
        '{"pass": true, "scores": {"factuality": 5}}',
        review_payload(factuality=99),
        review_payload(factuality=0),
        review_payload(factuality="5"),
        review_payload(factuality=True),
        review_payload().replace('"pass": true', '"pass": "true"'),
    ],
)
def test_malformed_review_is_reported_as_an_ai_error(malformed_review):
    service = AIService(Config())
    service._call_messages = Mock(side_effect=[ORIGINAL, malformed_review])

    with pytest.raises(DevfolioAIError, match="심사"):
        generate(service)


def test_invalid_final_format_is_not_returned():
    service = AIService(Config())
    service._call_messages = Mock(
        side_effect=[ORIGINAL, review_payload(passed=False), "- 한 줄만"]
    )

    with pytest.raises(DevfolioAIError, match="출력 형식"):
        generate(service)
