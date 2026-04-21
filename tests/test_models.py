"""Pydantic 모델 단위 테스트 (유효/무효 입력 포함)."""

import pytest
from pydantic import ValidationError

from devfolio.models.config import AIProviderConfig, Config, ExportConfig, ReasoningConfig, SyncConfig, UserConfig
from devfolio.models.draft import DraftPreviewRequest, ProjectDraft, TaskDraft
from devfolio.models.project import Period, Project, Task


# ---------------------------------------------------------------------------
# Period
# ---------------------------------------------------------------------------

class TestPeriod:
    def test_valid_period(self):
        p = Period(start="2024-01", end="2024-06")
        assert p.start == "2024-01"
        assert p.end == "2024-06"

    def test_open_ended(self):
        p = Period(start="2024-01")
        assert p.end is None
        assert "현재" in p.display()

    def test_invalid_start_format(self):
        with pytest.raises(ValidationError):
            Period(start="2024/01")

    def test_invalid_end_format(self):
        with pytest.raises(ValidationError):
            Period(start="2024-01", end="Jan 2024")

    def test_display_with_end(self):
        p = Period(start="2024-01", end="2024-12")
        assert p.display() == "2024-01 ~ 2024-12"

    def test_display_without_end(self):
        p = Period(start="2023-06")
        assert p.display() == "2023-06 ~ 현재"

    def test_empty_end_becomes_none(self):
        p = Period(start="2024-01", end="")
        assert p.end is None


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

class TestTask:
    def test_valid_task(self):
        t = Task(
            id="task_001",
            name="블루그린 배포 구축",
            period=Period(start="2024-02"),
            problem="다운타임 5분",
            solution="Jenkins 블루그린 배포",
            result="다운타임 0",
            tech_used=["Jenkins", "Docker"],
        )
        assert t.name == "블루그린 배포 구축"
        assert len(t.tech_used) == 2

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            Task(id="x", name="")

    def test_default_values(self):
        t = Task(id="x", name="작업")
        assert t.problem == ""
        assert t.ai_generated_text == ""
        assert t.tech_used == []
        assert t.keywords == []


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class TestProject:
    def test_valid_project(self):
        p = Project(
            id="test_proj",
            name="테스트 프로젝트",
            type="company",
            status="done",
            organization="테스트 회사",
            period=Period(start="2024-01", end="2024-06"),
            role="백엔드 개발자",
            team_size=5,
            tech_stack=["Python", "FastAPI"],
            summary="테스트 요약",
            tags=["backend"],
        )
        assert p.type == "company"
        assert p.status == "done"
        assert p.team_size == 5

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            Project(id="x", name="X", type="invalid")

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            Project(id="x", name="X", status="unknown_status")

    def test_negative_team_size_raises(self):
        with pytest.raises(ValidationError):
            Project(id="x", name="X", team_size=0)

    def test_type_display(self):
        p = Project(id="x", name="X", type="side")
        assert p.type_display() == "사이드 프로젝트"

    def test_status_display(self):
        p = Project(id="x", name="X", status="in_progress")
        assert p.status_display() == "진행 중"

    def test_tasks_default_empty(self):
        p = Project(id="x", name="X")
        assert p.tasks == []

    def test_model_dump_round_trip(self):
        """model_dump → model_validate 라운드트립."""
        original = Project(
            id="roundtrip",
            name="라운드트립 테스트",
            type="company",
            period=Period(start="2024-01", end="2024-06"),
            tech_stack=["Python"],
        )
        data = original.model_dump()
        restored = Project.model_validate(data)
        assert restored.name == original.name
        assert restored.period.start == original.period.start


# ---------------------------------------------------------------------------
# Draft models
# ---------------------------------------------------------------------------

class TestDraftModels:
    def test_project_draft_allows_empty_name_before_save(self):
        draft = ProjectDraft()
        assert draft.name == ""
        assert draft.tasks == []

    def test_task_draft_defaults(self):
        task = TaskDraft()
        assert task.name == ""
        assert task.period.start is None
        assert task.ai_generated_text == ""

    def test_preview_request_requires_draft_payload_when_source_is_draft(self):
        with pytest.raises(ValidationError):
            DraftPreviewRequest(source="draft")

    def test_preview_request_accepts_saved_source_without_draft(self):
        request = DraftPreviewRequest(source="saved", project_ids=["alpha"])
        assert request.project_ids == ["alpha"]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_default_config(self):
        c = Config()
        assert c.version == "1.0"
        assert c.default_language == "ko"
        assert c.ai_providers == []
        assert c.reasoning == ReasoningConfig()
        assert c.sync.enabled is False
        assert c.sync.branch == "main"

    def test_invalid_language_raises(self):
        with pytest.raises(ValidationError):
            Config(default_language="ja")

    def test_upsert_new_provider(self):
        c = Config()
        provider = AIProviderConfig(name="anthropic", model="claude-sonnet-4-20250514")
        c.upsert_provider(provider)
        assert len(c.ai_providers) == 1
        assert c.get_provider("anthropic") is not None

    def test_upsert_existing_provider_updates(self):
        c = Config()
        c.upsert_provider(AIProviderConfig(name="openai", model="gpt-4"))
        c.upsert_provider(AIProviderConfig(name="openai", model="gpt-4o"))
        assert len(c.ai_providers) == 1
        assert c.get_provider("openai").model == "gpt-4o"

    def test_get_provider_not_found(self):
        c = Config()
        assert c.get_provider("nonexistent") is None

    def test_config_model_dump(self):
        c = Config(default_language="en")
        c.user = UserConfig(name="홍길동", email="hong@example.com")
        c.sync = SyncConfig(enabled=True, repo_url="https://github.com/example/devfolio.git")
        data = c.model_dump()
        assert data["default_language"] == "en"
        assert data["reasoning"]["strategy"] == "single"
        assert data["user"]["name"] == "홍길동"
        assert data["sync"]["enabled"] is True

    def test_reasoning_config_validates_bounds(self):
        with pytest.raises(ValidationError):
            ReasoningConfig(strategy="best_of_n", samples=0)
