"""Portfolio Studio API / UI smoke tests."""

from pathlib import Path
from unittest.mock import patch

import pytest

from devfolio.core import storage
from devfolio.core.project_manager import ProjectManager
from devfolio.exceptions import DevfolioError
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


def test_scan_repo_path_candidates_translate_host_home_paths():
    from devfolio.web.routes.api import _scan_repo_path_candidates

    candidates = _scan_repo_path_candidates("/Users/alice/projects/demo")

    assert candidates[0] == Path("/Users/alice/projects/demo")
    assert Path("/home/user/projects/demo") in candidates


def test_list_directories_returns_child_directories_and_git_marker(client, web_store):
    browse_root = web_store / "repos"
    browse_root.mkdir()
    repo_dir = browse_root / "sample-repo"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    nested_dir = browse_root / "notes"
    nested_dir.mkdir()

    with patch("devfolio.web.routes.api._directory_picker_roots", return_value=[browse_root]):
        response = client.get("/api/fs/directories", params={"path": str(browse_root)})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["current_path"] == str(browse_root)
    assert payload["parent_path"] is None
    assert any(entry["name"] == "sample-repo" and entry["is_git_repo"] for entry in payload["entries"])
    assert any(entry["name"] == "notes" and not entry["is_git_repo"] for entry in payload["entries"])


def test_index_renders_portfolio_studio_shell(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Portfolio Studio" in response.text
    assert "Intake" in response.text
    assert "Preview" in response.text
    assert "Settings" in response.text


def test_upsert_ai_provider_uses_default_model_when_omitted(client):
    response = client.post(
        "/api/config/ai",
        json={
            "name": "anthropic",
            "api_key": "test-key",
        },
    )

    assert response.status_code == 200, response.text

    listed = client.get("/api/config")
    assert listed.status_code == 200, listed.text
    providers = listed.json()["ai_providers"]
    assert providers[0]["name"] == "anthropic"
    assert providers[0]["model"] == "claude-sonnet-4-20250514"


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


def test_scan_git_returns_devfolio_error_detail(client, web_store):
    with patch(
        "devfolio.core.git_scanner.scan_repo",
        side_effect=DevfolioError("스캔 실패", hint="git을 확인하세요."),
    ):
        response = client.post(
            "/api/scan/git",
            json={
                "repo_path": str(web_store),
                "author_email": "user@example.com",
                "refresh": True,
                "analyze": False,
            },
        )

    assert response.status_code == 400
    assert "스캔 실패" in response.json()["detail"]


def test_scan_git_rejects_remote_repository_url(client):
    response = client.post(
        "/api/scan/git",
        json={
            "repo_path": "https://github.com/openai/devfolio.git",
            "author_email": "user@example.com",
            "refresh": True,
            "analyze": False,
        },
    )

    assert response.status_code == 400
    assert "원격 Git URL은 바로 스캔할 수 없습니다" in response.json()["detail"]
