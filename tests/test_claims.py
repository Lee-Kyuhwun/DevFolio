"""정성 효과 주장 Hard Gate 회귀 테스트.

수치 가드레일이 막지 못한 "안정성 향상"·"비용 절감" 같은 근거 없는 효과 주장이
AI 저장 결과와 최종 보고서에 남지 않는지 고정한다(2026-11-15 감사 결함).
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from impactnote.core import store as store_module
from impactnote.core.claims import gate_result, gate_text, verify_effect_claim
from impactnote.core.report import build_content
from impactnote.core.service import ImpactService
from impactnote.core.store import JsonStore
from impactnote.web.app import create_app


@pytest.fixture()
def note_env(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPACTNOTE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("IMPACTNOTE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("IMPACTNOTE_LEGACY_DATA_DIR", str(tmp_path / "legacy-data"))
    monkeypatch.setenv("IMPACTNOTE_LEGACY_CONFIG_DIR", str(tmp_path / "legacy-config"))
    store_module.reset_store_for_tests()
    yield tmp_path
    store_module.reset_store_for_tests()


@pytest.fixture()
def client(note_env) -> TestClient:
    return TestClient(create_app())


def _today() -> str:
    return date.today().isoformat()


def _payload(**overrides) -> dict:
    payload = {
        "title": "배포 스크립트 정리",
        "description": "배포 실패 시 이전 이미지로 롤백하는 절차를 추가했다.",
        "date": _today(),
        "project": "결제 시스템",
        "activity_type": "automation",
        "status": "done",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 1. Gate 단위 동작 — 근거 없는 정성 효과
# ---------------------------------------------------------------------------


def test_unmeasured_effect_claim_is_blocked():
    cleaned, removed = gate_text(
        "서비스 안정성을 크게 향상시켰다.", ["로그인 기능을 추가했다."]
    )
    assert cleaned == ""
    assert removed[0]["status"] == "UNSUPPORTED"
    assert removed[0]["category"] == "stability"


def test_explicit_no_measurement_is_not_treated_as_support():
    claim = verify_effect_claim(
        "운영 비용을 절감했다.",
        ["백오피스 기능 목록만 있고 비용·운영 지표는 기록되지 않음"],
    )
    assert claim is not None and claim.status == "UNSUPPORTED"


def test_effect_claim_with_matching_measurement_is_kept():
    cleaned, removed = gate_text(
        "배포 소요 시간을 단축했다.",
        ["Jenkins 전환 후 배포 소요 시간 단축 (20분 → 5분, 측정)"],
    )
    assert cleaned == "배포 소요 시간을 단축했다."
    assert removed == []


def test_numeric_effect_without_benchmark_is_blocked():
    claim = verify_effect_claim(
        "응답 시간이 70% 단축되었다.",
        ["cache.py에 lru_cache를 추가했다. 성능 벤치마크 결과는 없다."],
    )
    assert claim is not None and claim.status == "UNSUPPORTED"
    assert "70" in claim.reason


def test_implementation_fact_is_not_stripped():
    text = "외부 API 지연에 대비해 Timeout과 재시도 처리를 구현했다."
    cleaned, removed = gate_text(text, ["Timeout/Retry 처리 추가"])
    assert cleaned == text
    assert removed == []


def test_gate_result_reports_nested_field_paths():
    cleaned, removed = gate_result(
        {
            "result": "운영 안정성을 향상시켰다.",
            "statements": {"monthly": "비용을 40% 절감했다."},
        },
        ["기능 목록만 있고 운영 지표는 기록되지 않음"],
    )
    assert cleaned["result"] == ""
    assert cleaned["statements"]["monthly"] == ""
    assert {item["field"] for item in removed} == {"result", "statements.monthly"}


# ---------------------------------------------------------------------------
# 2. AI 저장 경로 — 결과가 저장되기 전에 차단
# ---------------------------------------------------------------------------


def test_ai_analysis_drops_unsupported_effect_claim(client):  # noqa: F811
    client.put("/api/settings", json={"external_ai_consent": True})
    activity = client.post(
        "/api/activities", json=_payload(description="배포 스크립트를 정리했다.")
    ).json()["activity"]
    ai_payload = {
        "title": "배포 자동화",
        "problem": "수동 배포가 반복됐다.",
        "action": "롤백 절차를 추가했다.",
        "result": "서비스 안정성을 크게 향상시켰다.",
        "statements": {"monthly": "운영 안정성과 가용성을 확보했다."},
        "unverified_fields": [],
    }
    with patch(
        "devfolio.core.ai_service.AIService._call",
        return_value=json.dumps(ai_payload, ensure_ascii=False),
    ):
        analysis = client.post(
            "/api/ai/analyze", json={"activity_id": activity["id"]}
        ).json()["analysis"]

    assert analysis["status"] == "completed"
    assert analysis["result"]["result"] == ""
    assert analysis["result"]["statements"]["monthly"] == ""
    assert analysis["result"]["unverified_effects"]
    assert "result" in analysis["result"]["unverified_fields"]


def test_ai_analysis_keeps_effect_supported_by_recorded_result(client):  # noqa: F811
    client.put("/api/settings", json={"external_ai_consent": True})
    activity = client.post(
        "/api/activities",
        json=_payload(
            result="배포 소요 시간 20분 → 5분 (동일 장비 10회 측정)",
            description="Jenkins 파이프라인으로 배포를 자동화했다.",
        ),
    ).json()["activity"]
    ai_payload = {
        "title": "배포 자동화",
        "problem": "수동 배포가 반복됐다.",
        "action": "Jenkins 파이프라인을 구성했다.",
        "result": "배포 소요 시간을 20분에서 5분으로 단축했다.",
        "unverified_fields": [],
    }
    with patch(
        "devfolio.core.ai_service.AIService._call",
        return_value=json.dumps(ai_payload, ensure_ascii=False),
    ):
        analysis = client.post(
            "/api/ai/analyze", json={"activity_id": activity["id"]}
        ).json()["analysis"]

    assert "단축" in analysis["result"]["result"]
    assert not analysis["result"]["unverified_effects"]


# ---------------------------------------------------------------------------
# 3. 보고서 재환각 — 사용자가 확인한 AI 성과도 근거로 재검증
# ---------------------------------------------------------------------------


def _service(tmp_path) -> ImpactService:
    service = ImpactService(JsonStore(tmp_path / "data"))
    service.save_settings({"external_ai_consent": True})
    return service


def test_report_does_not_reintroduce_confirmed_ai_effect_claim(tmp_path):
    service = _service(tmp_path)
    evidence = service.create_evidence(
        {
            "type": "file",
            "title": "배포 스크립트",
            "reference": "deploy.sh",
            "description": "롤백 스크립트를 정리했다.",
            "verified": True,
        }
    )
    activity = service.create_activity(
        {
            **_payload(),
            "evidence_ids": [evidence.id],
        }
    )
    achievement = service.create_achievement(
        {
            "title": "배포 자동화",
            "activity_ids": [activity.id],
            "problem": "수동 배포가 반복됐다.",
            "action": "롤백 스크립트를 정리했다.",
            "result": "서비스 안정성을 크게 향상시켰다.",
            "evidence_ids": [evidence.id],
            "period_start": _today(),
            "period_end": _today(),
            "source": "ai",
            "confirmed": True,
        }
    )
    assert achievement.status == "verified"

    content, meta = build_content(service, template="monthly", period_kind="month")
    body = content.split("### 확인 필요 항목")[0]
    assert "안정성을 크게 향상" not in body
    assert any("효과 주장 제거" in item for item in meta["unverified"])


def test_report_keeps_effect_claim_with_matching_evidence(tmp_path):
    service = _service(tmp_path)
    evidence = service.create_evidence(
        {
            "type": "report",
            "title": "부하 테스트",
            "reference": "docs/load-test.md",
            "description": "배포 소요 시간 단축: 20분 → 5분 측정",
            "verified": True,
        }
    )
    activity = service.create_activity({**_payload(), "evidence_ids": [evidence.id]})
    service.create_achievement(
        {
            "title": "배포 자동화",
            "activity_ids": [activity.id],
            "action": "Jenkins 파이프라인을 구성했다.",
            "result": "배포 소요 시간을 단축했다.",
            "evidence_ids": [evidence.id],
            "period_start": _today(),
            "period_end": _today(),
            "source": "ai",
            "confirmed": True,
        }
    )
    content, _ = build_content(service, template="monthly", period_kind="month")
    assert "배포 소요 시간을 단축했다." in content


def test_manual_effect_claim_is_not_silently_removed(tmp_path):
    """사용자가 직접 쓴 성과는 사용자 주장으로 유지한다(자동 삭제하지 않는다)."""
    service = _service(tmp_path)
    activity = service.create_activity(_payload())
    service.create_achievement(
        {
            "title": "배포 자동화",
            "activity_ids": [activity.id],
            "action": "롤백 절차를 추가했다.",
            "result": "서비스 안정성을 향상시켰다.",
            "period_start": _today(),
            "period_end": _today(),
            "source": "manual",
        }
    )
    content, _ = build_content(service, template="monthly", period_kind="month")
    assert "서비스 안정성을 향상시켰다." in content


def test_percent_claim_is_not_supported_by_millisecond_value():
    from impactnote.core.metrics import sanitize_claims

    cleaned, dropped = sanitize_claims(
        "응답 시간을 80% 단축했다.", ["p95 200ms → 80ms"]
    )
    assert "80%" not in cleaned
    assert dropped and dropped[0]["raw"] == "80%"


def test_minute_and_m_alias_are_the_same_unit():
    from impactnote.core.metrics import sanitize_claims

    cleaned, dropped = sanitize_claims(
        "빌드 시간이 10분에서 5분으로 단축되었다.",
        ["CI 측정: build before 10m after 5m"],
    )
    assert dropped == []
    assert cleaned == "빌드 시간이 10분에서 5분으로 단축되었다."
