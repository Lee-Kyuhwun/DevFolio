"""Portfolio Studio API / UI smoke tests."""

from unittest.mock import patch

import pytest

from devfolio.core import storage
from devfolio.core.project_manager import ProjectManager
from devfolio.models.config import Config
from devfolio.models.draft import ProjectDraft, TaskDraft

fastapi = pytest.importorskip("fastapi")
TestClient = pytest.importorskip("fastapi.testclient").TestClient


@pytest.fixture
def web_store(tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    projects_dir = data_dir / "projects"
    exports_dir = data_dir / "exports"
    templates_dir = data_dir / "templates"
    legacy_dir = tmp_path / "legacy"

    config_dir.mkdir()
    projects_dir.mkdir(parents=True)
    exports_dir.mkdir(parents=True)
    templates_dir.mkdir(parents=True)

    with (
        patch("devfolio.core.storage.DEVFOLIO_CONFIG_DIR", config_dir),
        patch("devfolio.core.storage.DEVFOLIO_DATA_DIR", data_dir),
        patch("devfolio.core.storage.PROJECTS_DIR", projects_dir),
        patch("devfolio.core.storage.EXPORTS_DIR", exports_dir),
        patch("devfolio.core.storage.TEMPLATES_DIR", templates_dir),
        patch("devfolio.core.template_engine.TEMPLATES_DIR", templates_dir),
        patch("devfolio.core.storage.SYNC_REPO_DIR", data_dir / "sync_repo"),
        patch("devfolio.core.storage.SYNC_STATE_FILE", data_dir / "sync_state.json"),
        patch("devfolio.core.storage.CONFIG_FILE", config_dir / "config.yaml"),
        patch("devfolio.core.storage._LEGACY_HOME", legacy_dir),
        patch("devfolio.core.storage._LEGACY_CONFIG", legacy_dir / "config.yaml"),
        patch("devfolio.core.export_engine.EXPORTS_DIR", exports_dir),
    ):
        storage.save_config(Config())
        yield tmp_path


@pytest.fixture
def client(web_store):
    from devfolio.web.app import create_app

    return TestClient(create_app())


def test_index_renders_portfolio_studio_shell(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Portfolio Studio" in response.text
    assert "Intake" in response.text
    assert "Preview" in response.text
    assert "Settings" in response.text


def test_projects_crud_round_trip(client):
    create = client.post(
        "/api/projects",
        json={
            "name": "웹 프로젝트",
            "type": "company",
            "status": "done",
            "period": {"start": "2024-01", "end": "2024-03"},
            "tasks": [
                {
                    "name": "API 구현",
                    "period": {"start": "2024-01", "end": "2024-02"},
                    "problem": "수동 처리",
                    "solution": "자동화 API 구축",
                    "result": "처리 시간 단축",
                    "tech_used": ["FastAPI"],
                    "keywords": ["api"],
                    "ai_generated_text": "",
                }
            ],
        },
    )

    assert create.status_code == 200, create.text
    project = create.json()["project"]
    assert project["id"] == "웹_프로젝트"

    update = client.put(
        f"/api/projects/{project['id']}",
        json={
            **project,
            "name": "웹 프로젝트 수정",
            "summary": "수정된 요약",
        },
    )
    assert update.status_code == 200, update.text
    updated = update.json()["project"]
    assert updated["name"] == "웹 프로젝트 수정"
    assert updated["summary"] == "수정된 요약"

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    names = [item["name"] for item in listed.json()["projects"]]
    assert "웹 프로젝트 수정" in names

    deleted = client.delete(f"/api/projects/{updated['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/projects").json()["projects"] == []


def test_preview_resume_accepts_unsaved_draft(client):
    response = client.post(
        "/api/preview/resume",
        json={
            "source": "draft",
            "draft_project": {
                "name": "드래프트 프로젝트",
                "type": "company",
                "status": "done",
                "organization": "DevFolio",
                "period": {"start": "2024-01", "end": "2024-02"},
                "role": "백엔드",
                "team_size": 2,
                "tech_stack": ["Python", "FastAPI"],
                "summary": "저장 전 미리보기 테스트",
                "tags": ["preview"],
                "tasks": [
                    {
                        "name": "미리보기 작업",
                        "period": {"start": "2024-01", "end": "2024-02"},
                        "problem": "문서가 분산됨",
                        "solution": "구조화 저장",
                        "result": "재사용 가능",
                        "tech_used": ["FastAPI"],
                        "keywords": ["preview"],
                        "ai_generated_text": "",
                    }
                ],
            },
            "template": "default",
            "format": "html",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_count"] == 1
    assert "드래프트 프로젝트" in payload["markdown"]
    assert "저장 전 미리보기 테스트" in payload["html"]


def test_intake_project_draft_endpoint_returns_structured_draft(client):
    fake_draft = ProjectDraft(
        name="AI 초안 프로젝트",
        summary="AI가 만든 초안",
        tasks=[TaskDraft(name="구조화 작업")],
        raw_text="원본 텍스트",
    )

    with patch(
        "devfolio.web.routes.api.AIService.generate_project_draft",
        return_value=fake_draft,
    ):
        response = client.post(
            "/api/intake/project-draft",
            json={"raw_text": "원본 텍스트", "lang": "ko", "provider": None},
        )

    assert response.status_code == 200, response.text
    payload = response.json()["draft"]
    assert payload["name"] == "AI 초안 프로젝트"
    assert payload["raw_text"] == "원본 텍스트"
    assert payload["tasks"][0]["name"] == "구조화 작업"


def test_export_portfolio_saved_project_creates_html(client, web_store):
    manager = ProjectManager()
    project = manager.create_project(
        name="저장된 프로젝트",
        period_start="2024-01",
        summary="export 테스트",
    )

    response = client.post(
        "/api/export/portfolio",
        json={
            "source": "saved",
            "project_ids": [project.id],
            "template": "default",
            "format": "html",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["format"] == "html"
    assert payload["path"].endswith(".html")
    assert (storage.EXPORTS_DIR / "portfolio_default.html").exists()


def test_saved_project_ai_task_generation_updates_persisted_project(client):
    manager = ProjectManager()
    project = manager.create_project(name="AI 저장 프로젝트", period_start="2024-01")
    manager.add_task(
        project_name=project.name,
        name="초기 작업",
        problem="문제",
        solution="해결",
        result="성과",
        tech_used=["Python"],
    )

    updated_draft = manager.draft_from_project(manager.get_project_or_raise(project.id))
    updated_draft.tasks[0].ai_generated_text = "- 개선된 bullet"

    with patch(
        "devfolio.web.routes.api.AIService.generate_draft_task_texts",
        return_value=updated_draft,
    ):
        response = client.post(
            f"/api/projects/{project.id}/generate-task-bullets",
            json={"lang": "ko", "provider": None},
        )

    assert response.status_code == 200, response.text
    refreshed = manager.get_project_or_raise(project.id)
    assert refreshed.tasks[0].ai_generated_text == "- 개선된 bullet"
