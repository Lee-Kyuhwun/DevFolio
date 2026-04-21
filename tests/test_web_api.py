"""Portfolio Studio API / UI smoke tests."""

from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from devfolio.core import storage
from devfolio.core.project_manager import ProjectManager
from devfolio.exceptions import DevfolioError
from devfolio.models.config import AIProviderConfig, Config
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
    assert "Home" in response.text
    assert "Compose" in response.text
    assert "Library" in response.text
    assert "Preview" in response.text
    assert "Settings" in response.text
    assert "백엔드 개발자 포트폴리오를 구조화하고 문서까지 완성하는 로컬 우선 스튜디오" in response.text


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


def test_upsert_ai_provider_preserves_display_model_and_exposes_generation_model(client):
    response = client.post(
        "/api/config/ai",
        json={
            "name": "gemini",
            "model": "gemini-2.0-flash-001",
            "api_key": "test-key",
        },
    )

    assert response.status_code == 200, response.text

    listed = client.get("/api/config")
    assert listed.status_code == 200, listed.text
    providers = listed.json()["ai_providers"]
    assert providers[0]["name"] == "gemini"
    assert providers[0]["display_model"] == "gemini-2.0-flash-001"
    assert providers[0]["generation_model"] == "gemini-2.0-flash"
    assert providers[0]["generation_status"] == "fallback"


def test_get_config_keeps_display_model_and_reports_generation_fallback(client):
    cfg = storage.load_config()
    cfg.default_ai_provider = "gemini"
    cfg.upsert_provider(
        AIProviderConfig(
            name="gemini",
            model="gemini-2.0-flash-001",
            key_stored=True,
        )
    )
    storage.save_config(cfg)

    response = client.get("/api/config")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["general"]["default_ai_generation_model"] == "gemini-2.0-flash"
    assert payload["general"]["default_ai_generation_status"] == "fallback"
    assert payload["general"]["default_ai_generation_warning"]
    assert payload["general"]["reasoning_strategy"] == "single"
    assert payload["general"]["reasoning_samples"] == 1
    assert payload["general"]["judge_provider"] == ""
    assert payload["ai_providers"][0]["display_model"] == "gemini-2.0-flash-001"
    assert payload["ai_providers"][0]["generation_model"] == "gemini-2.0-flash"
    assert payload["ai_providers"][0]["generation_warning"]

    reloaded = storage.load_config()
    assert reloaded.ai_providers[0].model == "gemini-2.0-flash-001"


def test_update_general_persists_reasoning_settings(client):
    cfg = storage.load_config()
    cfg.default_ai_provider = "anthropic"
    cfg.upsert_provider(
        AIProviderConfig(
            name="anthropic",
            model="claude-sonnet-4-20250514",
            key_stored=True,
        )
    )
    cfg.upsert_provider(
        AIProviderConfig(
            name="openai",
            model="gpt-4o",
            key_stored=True,
        )
    )
    storage.save_config(cfg)

    response = client.put(
        "/api/config/general",
        json={
            "default_language": "ko",
            "timezone": "Asia/Seoul",
            "default_ai_provider": "anthropic",
            "reasoning_strategy": "single",
            "reasoning_samples": 3,
            "judge_provider": "openai",
        },
    )

    assert response.status_code == 200, response.text

    reloaded = storage.load_config()
    assert reloaded.reasoning.strategy == "best_of_n"
    assert reloaded.reasoning.samples == 3
    assert reloaded.reasoning.judge_provider == "openai"


def test_upsert_ai_provider_exposes_runtime_env_when_keyring_unavailable(client):
    with patch("devfolio.web.routes.api.store_api_key", return_value=False):
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
    assert providers[0]["key_masked"] == "(환경변수 ANTHROPIC_API_KEY)"


def test_list_ai_models_returns_generation_metadata(client):
    fake_response = (
        b'{"models": ['
        b'{"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},'
        b'{"name": "models/gemini-2.5-flash-preview-09-2025", "supportedGenerationMethods": ["generateContent"]}'
        b']}'
    )
    mocked = patch("urllib.request.urlopen")
    with mocked as urlopen:
        response_obj = urlopen.return_value.__enter__.return_value
        response_obj.read.return_value = fake_response
        response = client.get("/api/models", params={"provider": "gemini", "api_key": "AIza-test"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider"] == "gemini"
    assert payload["models"][0]["id"] == "gemini-2.5-flash"
    assert payload["models"][0]["generation_status"] == "ready"
    preview = next(item for item in payload["models"] if item["id"] == "gemini-2.5-flash-preview-09-2025")
    assert preview["generation_model"] == "gemini-2.5-flash"
    assert preview["generation_status"] == "fallback"
    assert preview["warning"]


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


def test_preview_portfolio_renders_ai_generated_task_text(client):
    response = client.post(
        "/api/preview/portfolio",
        json={
            "source": "draft",
            "draft_project": {
                "name": "포트폴리오 프로젝트",
                "type": "company",
                "status": "done",
                "organization": "DevFolio",
                "period": {"start": "2024-01", "end": "2024-02"},
                "role": "백엔드",
                "team_size": 1,
                "tech_stack": ["Python", "FastAPI"],
                "one_line_summary": "구조화된 커리어 데이터를 문서로 전환하는 로컬 우선 스튜디오",
                "summary": "더 긴 포트폴리오 렌더링 테스트",
                "overview": {
                    "background": "포트폴리오 문구가 기능 나열 위주라 문제 맥락이 약했습니다.",
                    "problem": "왜 만들었고 어떤 판단을 했는지 드러나는 문서 구조가 필요했습니다.",
                    "target_users": ["개발자"],
                    "goals": ["케이스 스터디형 문서", "구조화 데이터 재사용"],
                    "non_goals": [],
                },
                "user_flow": [
                    {"step": 1, "title": "입력", "description": "프로젝트 초안을 구조화합니다."},
                    {"step": 2, "title": "검토", "description": "AI 생성 결과를 확인하고 수정합니다."},
                ],
                "tech_stack_detail": {
                    "frontend": [],
                    "backend": [{"name": "Python", "reason": "CLI와 웹 API, 렌더링을 한 언어로 통합하기 위해 사용했습니다."}],
                    "database": [],
                    "infra": [],
                    "tools": [{"name": "Jinja2", "reason": "구조화 데이터를 여러 문서 형식으로 재사용하기 위해 선택했습니다."}],
                },
                "features": [
                    {
                        "name": "케이스 스터디 렌더링",
                        "user_value": "문제 맥락과 설계 판단이 드러나는 포트폴리오 문서를 빠르게 만들 수 있습니다.",
                        "implementation": "구조화 필드와 템플릿 helper를 조합해 구현했습니다.",
                    }
                ],
                "problem_solving_cases": [
                    {
                        "title": "양식 부실 문제 개선",
                        "situation": "무엇을 만들었는지는 보이지만 판단과 결과가 약했습니다.",
                        "cause": "summary와 task 나열만으로는 케이스 스터디 구조를 만들기 어려웠습니다.",
                        "action": "개요, 문제 정의, 사용자 흐름, 문제 해결 사례 구조를 스키마와 템플릿에 추가했습니다.",
                        "decision_reason": "AI 출력과 최종 렌더링이 같은 구조를 공유해야 품질이 안정되기 때문입니다.",
                        "result": "문제, 판단, 결과가 분리된 문서를 렌더링할 수 있게 됐습니다.",
                        "metric": "문서 구조 명시화",
                        "tech_used": ["Python", "Jinja2"],
                    }
                ],
                "results": {
                    "quantitative": [{"metric_name": "구조", "before": "summary 중심", "after": "case study 중심", "impact": "가독성 개선"}],
                    "qualitative": ["프로젝트 목적과 결과가 먼저 읽히는 문서가 되었습니다."],
                },
                "retrospective": {
                    "what_went_well": ["문서 구조를 스키마와 템플릿에 함께 반영했습니다."],
                    "what_was_hard": ["기존 task 중심 구조와의 호환이 필요했습니다."],
                    "what_i_learned": ["좋은 포트폴리오는 기능보다 판단과 결과를 먼저 보여줘야 합니다."],
                    "next_steps": ["링크와 시각 자산 입력 UI를 보강합니다."],
                },
                "tags": ["portfolio"],
                "tasks": [
                    {
                        "name": "AI 문구 작업",
                        "period": {"start": "2024-01", "end": "2024-02"},
                        "problem": "기존 포트폴리오 설명이 너무 짧음",
                        "solution": "AI 생성 문구와 상세 메타를 함께 렌더링",
                        "result": "프로젝트 설명 밀도 개선",
                        "tech_used": ["FastAPI", "Jinja2"],
                        "keywords": ["portfolio"],
                        "ai_generated_text": "- 핵심 작업을 구조화해 설명 밀도를 높였습니다.\n- 구현 선택과 결과를 한 번에 읽히도록 정리했습니다.",
                    }
                ],
            },
            "template": "default",
            "format": "html",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "핵심 작업을 구조화해 설명 밀도를 높였습니다." in payload["markdown"]
    assert "사용 기술" in payload["markdown"]
    assert "문제 정의" in payload["markdown"]
    assert "사용자 흐름" in payload["markdown"]
    assert "기술 스택 및 선정 이유" in payload["markdown"]
    assert "문제 해결 사례" in payload["markdown"]
    assert "회고" in payload["markdown"]
    assert "```mermaid" in payload["markdown"]


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
    exported_html = (storage.EXPORTS_DIR / "portfolio_default.html").read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net/npm/mermaid" in exported_html
    assert "문제 정의" in exported_html


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


def test_scan_git_ai_failure_keeps_basic_scan_result(client, web_store):
    cfg = storage.load_config()
    cfg.default_ai_provider = "gemini"
    cfg.upsert_provider(
        AIProviderConfig(
            name="gemini",
            model="gemini-2.0-flash-001",
            key_stored=True,
        )
    )
    storage.save_config(cfg)

    fake_scan_result = SimpleNamespace(
        commits=["a", "b"],
        languages=Counter({"Python": 90, "HTML": 10}),
        project_context={"readme": "demo"},
    )

    with (
        patch("devfolio.core.git_scanner.scan_repo", return_value=fake_scan_result),
        patch("devfolio.core.git_scanner.build_project_payload", return_value={"repo": "DevFolio"}),
        patch(
            "devfolio.web.routes.api.AIService.analyze_project_from_code",
            side_effect=DevfolioError("AI 실패"),
        ),
    ):
        response = client.post(
            "/api/scan/git",
            json={
                "repo_path": str(web_store),
                "author_email": "user@example.com",
                "refresh": True,
                "analyze": True,
                "lang": "ko",
                "provider": None,
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["analyzed"] is False
    assert payload["payload"] == {"repo": "DevFolio"}
