"""성과노트(ImpactNote) 회귀 테스트.

실제 AI API 는 호출하지 않는다. `AIService._call` 을 패치해 성공/실패 응답을 만든다.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from impactnote.core import store as store_module
from impactnote.core.migrate import run_migration
from impactnote.core.models import Activity, Achievement, Evidence, Metric
from impactnote.core.periods import resolve_period
from impactnote.core.report import build_content
from impactnote.core.service import ImpactService
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


def _activity_payload(**overrides) -> dict:
    payload = {
        "title": "배포 자동화 스크립트 수정",
        "description": "배포 실패 시 롤백 절차를 추가했다.",
        "date": _today(),
        "project": "결제 시스템",
        "activity_type": "automation",
        "status": "done",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 1. 브랜드·기본 계약
# ---------------------------------------------------------------------------


def test_health_and_meta_are_impactnote(client):  # noqa: F811
    health = client.get("/api/health").json()
    assert health["app"] == "성과노트"
    assert health["app_en"] == "ImpactNote"

    meta = client.get("/api/meta").json()
    assert meta["templates"]["monthly"] == "월간 업무실적 보고"
    assert "performance" in meta["activity_types"]
    assert "incident" in meta["activity_types"]
    assert meta["settings"]["external_ai_consent"] is False


def test_index_has_no_legacy_brand(note_env):
    html = (
        Path(__file__).parent.parent / "impactnote/web/static/index.html"
    ).read_text(encoding="utf-8")
    assert "성과노트" in html
    assert "DevFolio" not in html
    assert "devfolio" not in html.lower()


def test_app_title_is_branded(note_env):
    app = create_app()
    assert "성과노트" in app.title


# ---------------------------------------------------------------------------
# 2. 업무 기록 CRUD
# ---------------------------------------------------------------------------


def test_activity_crud(client):  # noqa: F811
    created = client.post("/api/activities", json=_activity_payload()).json()[
        "activity"
    ]
    assert created["id"].startswith("act_")

    listed = client.get("/api/activities").json()["activities"]
    assert [item["id"] for item in listed] == [created["id"]]

    updated = client.patch(
        f"/api/activities/{created['id']}",
        json={**created, "title": "배포 자동화 스크립트 개선"},
    ).json()["activity"]
    assert updated["title"] == "배포 자동화 스크립트 개선"

    assert client.delete(f"/api/activities/{created['id']}").status_code == 200
    assert client.get("/api/activities").json()["activities"] == []


def test_quick_record_needs_only_title_and_description(client):  # noqa: F811
    response = client.post(
        "/api/activities",
        json={"title": "주간 회의 정리", "description": "액션 아이템 정리"},
    )
    assert response.status_code == 201
    activity = response.json()["activity"]
    assert activity["date"] == _today()
    assert activity["importance"] == 3


# ---------------------------------------------------------------------------
# 3~5. 성과·근거·지표
# ---------------------------------------------------------------------------


def test_achievement_from_activities_and_evidence_status(client):  # noqa: F811
    first = client.post("/api/activities", json=_activity_payload()).json()["activity"]
    second = client.post(
        "/api/activities",
        json=_activity_payload(title="롤백 리허설", description="복구 절차 검증"),
    ).json()["activity"]

    achievement = client.post(
        "/api/achievements/from-activities",
        json={"activity_ids": [first["id"], second["id"]]},
    ).json()["achievement"]
    assert achievement["status"] == "user_input"
    assert set(achievement["activity_ids"]) == {first["id"], second["id"]}

    evidence = client.post(
        "/api/evidence",
        json={
            "type": "pull_request",
            "title": "배포 롤백 PR",
            "reference": "https://example.com/pr/1",
            "verified": True,
        },
    ).json()["evidence"]
    linked = client.post(
        f"/api/achievements/{achievement['id']}/evidence",
        json={"evidence_ids": [evidence["id"]]},
    ).json()["achievement"]
    assert linked["status"] == "verified"
    assert linked["needs_review"] is False


def test_unverified_evidence_requires_review(client):  # noqa: F811
    activity = client.post("/api/activities", json=_activity_payload()).json()[
        "activity"
    ]
    achievement = client.post(
        "/api/achievements/from-activities", json={"activity_ids": [activity["id"]]}
    ).json()["achievement"]
    evidence = client.post(
        "/api/evidence",
        json={
            "type": "url",
            "title": "관련 문서",
            "reference": "https://example.com/doc",
        },
    ).json()["evidence"]

    linked = client.post(
        f"/api/achievements/{achievement['id']}/evidence",
        json={"evidence_ids": [evidence["id"]]},
    ).json()["achievement"]
    # 연결은 유지하되, 확인되지 않은 근거만으로 "근거 확인됨"이 되지는 않는다.
    assert linked["status"] == "needs_review"
    assert linked["needs_review"] is True
    assert linked["evidence_ids"] == [evidence["id"]]


def test_mixed_evidence_gives_partial_status(client):  # noqa: F811
    activity = client.post("/api/activities", json=_activity_payload()).json()[
        "activity"
    ]
    achievement = client.post(
        "/api/achievements/from-activities", json={"activity_ids": [activity["id"]]}
    ).json()["achievement"]
    verified = client.post(
        "/api/evidence",
        json={
            "type": "jira",
            "title": "티켓",
            "reference": "PAY-1",
            "verified": True,
        },
    ).json()["evidence"]
    pending = client.post(
        "/api/evidence", json={"type": "url", "title": "확인 전 문서"}
    ).json()["evidence"]

    linked = client.post(
        f"/api/achievements/{achievement['id']}/evidence",
        json={"evidence_ids": [verified["id"], pending["id"]]},
    ).json()["achievement"]
    assert linked["status"] == "partially_verified"
    assert linked["needs_review"] is True


def test_metric_without_evidence_is_not_verified(client):  # noqa: F811
    activity = client.post(
        "/api/activities",
        json=_activity_payload(description="배포 시간을 20분에서 12분으로 줄였다."),
    ).json()["activity"]
    achievement = client.post(
        "/api/achievements/from-activities", json={"activity_ids": [activity["id"]]}
    ).json()["achievement"]

    metric = client.post(
        f"/api/achievements/{achievement['id']}/metrics",
        json={"name": "배포 소요 시간", "value": "12", "unit": "분", "verified": True},
    ).json()["metric"]
    assert metric["verified"] is False  # 근거/산출 기준이 없으면 확인되지 않는다


def test_metric_with_basis_and_source_is_verified(client):  # noqa: F811
    activity = client.post(
        "/api/activities",
        json=_activity_payload(description="배포 시간을 20분에서 12분으로 줄였다."),
    ).json()["activity"]
    achievement = client.post(
        "/api/achievements/from-activities", json={"activity_ids": [activity["id"]]}
    ).json()["achievement"]

    metric = client.post(
        f"/api/achievements/{achievement['id']}/metrics",
        json={
            "name": "배포 소요 시간",
            "value": "12",
            "unit": "분",
            "basis": "CI 로그 20회 평균",
            "verified": True,
        },
    ).json()["metric"]
    assert metric["verified"] is True


# ---------------------------------------------------------------------------
# 6. Git 후보 수집
# ---------------------------------------------------------------------------


def test_git_commits_become_review_candidates(client):  # noqa: F811
    commit = SimpleNamespace(
        sha="abc1234567",
        subject="fix: 배포 실패 복구 절차 추가",
        date="2026-11-01",
        author_name="me",
        insertions=10,
        deletions=2,
        files_changed=3,
    )
    scan = SimpleNamespace(repo_name="demo", repo_url="", commits=[commit])
    with patch("devfolio.core.git_scanner.scan_repo", return_value=scan):
        result = client.post(
            "/api/git/import",
            json={"repo_path": str(Path.cwd()), "author_email": "me@company.com"},
        ).json()

    assert result["created_activities"] == 1
    assert result["created_candidates"] == 1
    achievements = client.get("/api/achievements").json()["achievements"]
    assert achievements[0]["status"] == "needs_review"
    assert achievements[0]["source"] == "git"


# ---------------------------------------------------------------------------
# 7~9. AI: 동의·실패 보존·수치 가드레일
# ---------------------------------------------------------------------------


def _consent(client):  # noqa: F811
    client.put("/api/settings", json={"external_ai_consent": True})


def test_ai_requires_external_consent(client):  # noqa: F811
    activity = client.post("/api/activities", json=_activity_payload()).json()[
        "activity"
    ]
    response = client.post("/api/ai/analyze", json={"activity_id": activity["id"]})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EXTERNAL_AI_NOT_ALLOWED"


def test_ai_failure_preserves_original_activity(client):  # noqa: F811
    _consent(client)
    activity = client.post("/api/activities", json=_activity_payload()).json()[
        "activity"
    ]
    with patch(
        "devfolio.core.ai_service.AIService._call",
        side_effect=RuntimeError("429 rate limit exceeded"),
    ):
        response = client.post("/api/ai/analyze", json={"activity_id": activity["id"]})
    assert response.status_code == 200
    analysis = response.json()["analysis"]
    assert analysis["status"] == "failed"
    assert analysis["error_code"] == "RATE_LIMITED"

    stored = client.get(f"/api/activities/{activity['id']}").json()["activity"]
    assert stored["title"] == activity["title"]
    assert stored["description"] == activity["description"]


def test_ai_numbers_without_evidence_are_replaced(client):  # noqa: F811
    _consent(client)
    activity = client.post(
        "/api/activities",
        json=_activity_payload(description="배포 스크립트를 정리했다."),
    ).json()["activity"]
    ai_payload = {
        "title": "배포 안정화",
        "problem": "배포 실패가 반복됐다.",
        "action": "롤백 절차를 추가했다.",
        "result": "배포 실패율 40% 감소",
        "impact_categories": ["stability"],
        "statements": {"weekly": "배포 실패율 40% 감소"},
    }
    with patch(
        "devfolio.core.ai_service.AIService._call",
        return_value=json.dumps(ai_payload, ensure_ascii=False),
    ):
        analysis = client.post(
            "/api/ai/analyze", json={"activity_id": activity["id"]}
        ).json()["analysis"]

    assert analysis["status"] == "completed"
    assert "40%" not in analysis["result"]["result"]
    assert "[확인 필요]" in analysis["result"]["result"]
    assert analysis["result"]["unverified_metrics"]


def test_failed_analysis_cannot_be_applied(client):  # noqa: F811
    _consent(client)
    activity = client.post("/api/activities", json=_activity_payload()).json()[
        "activity"
    ]
    with patch(
        "devfolio.core.ai_service.AIService._call", side_effect=RuntimeError("boom")
    ):
        analysis = client.post(
            "/api/ai/analyze", json={"activity_id": activity["id"]}
        ).json()["analysis"]
    response = client.post(f"/api/ai/analyses/{analysis['id']}/apply")
    assert response.status_code == 400


def test_completed_analysis_can_be_saved_as_candidate(client):  # noqa: F811
    _consent(client)
    activity = client.post("/api/activities", json=_activity_payload()).json()[
        "activity"
    ]
    payload = {
        "title": "배포 안정성 개선",
        "problem": "배포 실패",
        "action": "롤백 절차 추가",
        "result": "복구 절차 문서화",
        "impact_categories": ["stability"],
    }
    with patch(
        "devfolio.core.ai_service.AIService._call",
        return_value=json.dumps(payload, ensure_ascii=False),
    ):
        analysis = client.post(
            "/api/ai/analyze", json={"activity_id": activity["id"]}
        ).json()["analysis"]
    achievement = client.post(f"/api/ai/analyses/{analysis['id']}/apply").json()[
        "achievement"
    ]
    assert achievement["status"] == "needs_review"
    assert achievement["source"] == "ai"


# ---------------------------------------------------------------------------
# 9~12. 기간 집계·보고서·버전
# ---------------------------------------------------------------------------


def test_period_aggregation_is_exact(note_env):
    service = ImpactService()
    service.create_activity(_activity_payload(title="이번 달 업무", date=_today()))
    old_date = (date.today() - timedelta(days=200)).isoformat()
    service.create_activity(_activity_payload(title="지난 분기 업무", date=old_date))

    content, meta = build_content(
        service, template="weekly", period_kind="week", reference=_today()
    )
    assert "이번 달 업무" in content
    assert "지난 분기 업무" not in content
    assert meta["period_start"] <= _today() <= meta["period_end"]


def test_week_and_quarter_ranges():
    start, end = resolve_period("week", reference="2026-11-15")  # 일요일
    assert start == "2026-11-09" and end == "2026-11-15"
    start, end = resolve_period("quarter", reference="2026-11-15")
    assert start == "2026-10-01" and end == "2026-12-31"
    start, end = resolve_period("custom", start="2026-02-10", end="2026-01-05")
    assert start == "2026-01-05" and end == "2026-02-10"


def test_report_uses_only_verified_metrics(client):  # noqa: F811
    # 업무 기록에는 수치가 없다 — 지표만 추가하고, 근거가 없으므로 본문에 쓰이면 안 된다.
    activity = client.post(
        "/api/activities",
        json=_activity_payload(description="배포 스크립트를 정리했다."),
    ).json()["activity"]
    achievement = client.post(
        "/api/achievements/from-activities", json={"activity_ids": [activity["id"]]}
    ).json()["achievement"]
    metric = client.post(
        f"/api/achievements/{achievement['id']}/metrics",
        json={"name": "배포 소요 시간", "value": "12", "unit": "분", "verified": True},
    ).json()["metric"]
    assert metric["verified"] is False

    report = client.post(
        "/api/reports",
        json={"template": "monthly", "period_kind": "month", "format": "md"},
    ).json()["report"]
    content = report["content"]
    body = content.split("확인 필요 항목")[0]
    assert "## 월간 핵심 실적" in body
    assert "12분" not in body
    assert "확인 필요 항목" in content
    assert "12분" in content


def test_report_regeneration_increments_version(client):  # noqa: F811
    client.post("/api/activities", json=_activity_payload())
    first = client.post(
        "/api/reports", json={"template": "monthly", "period_kind": "month"}
    ).json()["report"]
    second = client.post(
        "/api/reports", json={"template": "monthly", "period_kind": "month"}
    ).json()["report"]
    assert (first["version"], second["version"]) == (1, 2)
    assert first["file_name"]


def test_report_download_markdown(client):  # noqa: F811
    client.post("/api/activities", json=_activity_payload())
    report = client.post(
        "/api/reports", json={"template": "weekly", "period_kind": "week"}
    ).json()["report"]
    response = client.get(f"/api/reports/{report['id']}/download?format=md")
    assert response.status_code == 200
    assert "## 주요 업무" in response.text


def test_custom_sections_and_char_limit(client):  # noqa: F811
    client.post("/api/activities", json=_activity_payload())
    report = client.post(
        "/api/reports",
        json={
            "template": "custom",
            "period_kind": "month",
            "custom_sections": ["주요 업무", "개선 효과"],
            "char_limit": 10,
        },
    ).json()["report"]
    assert "## 주요 업무" in report["content"]
    assert "글자 수 제한" in report["content"]


def test_report_status_can_be_updated(client):  # noqa: F811
    report = client.post(
        "/api/reports", json={"template": "monthly", "period_kind": "month"}
    ).json()["report"]
    updated = client.patch(
        f"/api/reports/{report['id']}", json={"status": "submitted"}
    ).json()["report"]
    assert updated["status"] == "submitted"


# ---------------------------------------------------------------------------
# 13. DevFolio 데이터 마이그레이션
# ---------------------------------------------------------------------------


def test_migration_is_idempotent_and_preserves_source(note_env, monkeypatch):
    from impactnote.core import migrate as migrate_module

    legacy_data = note_env / "legacy-data"
    (legacy_data / "projects").mkdir(parents=True)
    original = legacy_data / "projects" / "p1.yaml"
    original.write_text("id: p1\nname: 데모\n", encoding="utf-8")

    projects = [
        {
            "id": "p1",
            "name": "결제 시스템",
            "period": {"start": "2025-01", "end": None},
            "type": "company",
            "one_line_summary": "결제 API 안정화",
            "overview": {"problem": "장애가 잦았다."},
            "repo_url": "https://github.com/example/pay",
            "tasks": [
                {
                    "id": "t1",
                    "name": "재시도 로직 추가",
                    "problem": "간헐적 실패",
                    "solution": "지수 백오프 재시도",
                    "result": "복구 성공",
                }
            ],
        }
    ]
    monkeypatch.setattr(migrate_module, "_legacy_projects", lambda: projects)

    service = ImpactService()
    first = migrate_module.run_migration(service, force=True)
    assert first["status"] == "migrated"
    assert first["migrated_activities"] == 1
    assert first["migrated_achievements"] == 1
    assert first["backup"]

    second = migrate_module.run_migration(ImpactService())
    assert second["status"] == "already_migrated"
    assert len(ImpactService().activities()) == 1
    # 원본 DevFolio YAML 은 그대로 남아 있다.
    assert original.read_text(encoding="utf-8") == "id: p1\nname: 데모\n"


def test_migration_reads_legacy_dir_override(note_env):
    """Docker 처럼 레거시 경로가 마운트된 경우에도 원본 YAML 을 읽어야 한다."""
    from ruamel.yaml import YAML

    from devfolio.models.project import Project

    legacy_projects = note_env / "legacy-data" / "projects"
    legacy_projects.mkdir(parents=True)
    project = Project.model_validate(
        {
            "id": "mounted",
            "name": "마운트된 레거시",
            "period": {"start": "2025-04"},
            "tasks": [{"id": "t1", "name": "레거시 작업", "result": "효과"}],
        }
    )
    parser = YAML()
    with (legacy_projects / "mounted.yaml").open("w", encoding="utf-8") as stream:
        parser.dump(project.model_dump(mode="json"), stream)

    service = ImpactService()
    summary = run_migration(service, force=True)
    assert summary["migrated_activities"] == 1
    assert [item.title for item in service.activities()] == ["레거시 작업"]


def test_migration_converts_tasks_to_activities_and_achievements(note_env, monkeypatch):
    from impactnote.core import migrate as migrate_module

    projects = [
        {
            "id": "p2",
            "name": "검색 개선",
            "period": {"start": "2025-03"},
            "tasks": [
                {
                    "id": "t1",
                    "name": "인덱스 튜닝",
                    "solution": "쿼리 개선",
                    "result": "조회 속도 개선",
                },
                {"id": "t2", "name": "모니터링 추가"},
            ],
        }
    ]
    monkeypatch.setattr(migrate_module, "_legacy_projects", lambda: projects)
    migrate_module.run_migration(ImpactService(), force=True)

    service = ImpactService()
    assert {item.title for item in service.activities()} == {
        "인덱스 튜닝",
        "모니터링 추가",
    }
    achievements = service.achievements()
    assert len(achievements) == 1
    assert achievements[0].result == "조회 속도 개선"


# ---------------------------------------------------------------------------
# 14~17. 저장 호환·민감정보 보호·모델
# ---------------------------------------------------------------------------


def test_models_reject_invalid_dates():
    with pytest.raises(ValueError):
        Activity(title="x", date="2026/01/01")
    with pytest.raises(ValueError):
        Activity(title="x", date="2026-02-01", period_end="2026-01-01")


def test_settings_consent_persists(client):  # noqa: F811
    client.put(
        "/api/settings",
        json={
            "external_ai_consent": True,
            "allowed_providers": ["ollama"],
            "user_name": "이규훈",
        },
    )
    settings = client.get("/api/settings").json()["settings"]
    assert settings["external_ai_consent"] is True
    assert settings["allowed_providers"] == ["ollama"]


def test_store_permissions_are_private(client):  # noqa: F811
    client.post("/api/activities", json=_activity_payload())
    path = Path(store_module.data_dir()) / "activities.json"
    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600


def test_defaults_and_models_are_consistent():
    evidence = Evidence(title="t")
    assert evidence.type == "url" and evidence.verified is False
    metric = Metric(name="m", value="1", unit="건", verified=True)
    assert metric.verified is False  # 근거/기준 없이 verified 요청은 무시
    achievement = Achievement(title="a", impact_categories=["unknown", "quality"])
    assert achievement.impact_categories == ["quality"]
