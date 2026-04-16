"""프로젝트 관리자 단위 테스트."""

from unittest.mock import patch

import pytest

from devfolio.core.project_manager import ProjectManager
from devfolio.exceptions import DevfolioProjectNotFoundError, DevfolioTaskNotFoundError
from devfolio.models.project import Period, Project, Task


@pytest.fixture
def tmp_devfolio(tmp_path):
    """테스트용 임시 저장소 경로 패치."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    with (
        patch("devfolio.core.storage.DEVFOLIO_CONFIG_DIR", config_dir),
        patch("devfolio.core.storage.DEVFOLIO_DATA_DIR", tmp_path),
        patch("devfolio.core.storage.PROJECTS_DIR", projects_dir),
        patch("devfolio.core.storage.EXPORTS_DIR", exports_dir),
        patch("devfolio.core.storage.TEMPLATES_DIR", templates_dir),
        patch("devfolio.core.template_engine.TEMPLATES_DIR", templates_dir),
        patch("devfolio.core.storage.CONFIG_FILE", config_dir / "config.yaml"),
        patch("devfolio.core.storage._LEGACY_HOME", tmp_path / "legacy"),
        patch("devfolio.core.storage._LEGACY_CONFIG", tmp_path / "legacy" / "config.yaml"),
    ):
        yield tmp_path


@pytest.fixture
def pm(tmp_devfolio):
    return ProjectManager()


# ---------------------------------------------------------------------------
# 프로젝트 생성
# ---------------------------------------------------------------------------

class TestCreateProject:
    def test_basic_create(self, pm):
        project = pm.create_project(
            name="테스트 프로젝트",
            type="company",
            period_start="2024-01",
            period_end="2024-06",
            role="백엔드 개발자",
            tech_stack=["Python", "Django"],
        )
        assert project.name == "테스트 프로젝트"
        assert project.type == "company"
        assert project.period.start == "2024-01"
        assert project.period.end == "2024-06"
        assert "Python" in project.tech_stack

    def test_id_generation_korean(self, pm):
        """한글 이름은 영문 ID로 변환된다."""
        project = pm.create_project(name="my project 2024")
        assert project.id == "my_project_2024"

    def test_in_progress_project(self, pm):
        project = pm.create_project(name="진행 중", period_start="2024-01", period_end=None)
        assert project.period.end is None
        assert project.period.display() == "2024-01 ~ 현재"

    def test_persisted_to_yaml(self, pm, tmp_devfolio):
        pm.create_project(name="저장 테스트", period_start="2024-01")
        from devfolio.core.storage import PROJECTS_DIR
        files = list(PROJECTS_DIR.glob("*.yaml"))
        assert len(files) == 1

    def test_invalid_type_raises(self):
        with pytest.raises(Exception):  # Pydantic ValidationError
            Project(id="x", name="X", type="invalid_type")

    def test_invalid_status_raises(self):
        with pytest.raises(Exception):
            Project(id="x", name="X", status="unknown")


# ---------------------------------------------------------------------------
# 프로젝트 조회
# ---------------------------------------------------------------------------

class TestGetProject:
    def test_get_by_name(self, pm):
        pm.create_project(name="검색 테스트", period_start="2024-01")
        found = pm.get_project("검색 테스트")
        assert found is not None
        assert found.name == "검색 테스트"

    def test_get_by_id(self, pm):
        pm.create_project(name="ID 검색 테스트", period_start="2024-01")
        found = pm.get_project("id_검색_테스트")
        assert found is not None

    def test_partial_name_match(self, pm):
        pm.create_project(name="커넥티드카 게이트웨이 서비스", period_start="2024-01")
        found = pm.get_project("커넥티드카")
        assert found is not None

    def test_not_found_returns_none(self, pm):
        result = pm.get_project("존재하지 않는 프로젝트")
        assert result is None

    def test_get_or_raise_not_found(self, pm):
        with pytest.raises(DevfolioProjectNotFoundError):
            pm.get_project_or_raise("없는 프로젝트")


# ---------------------------------------------------------------------------
# 프로젝트 수정
# ---------------------------------------------------------------------------

class TestUpdateProject:
    def test_update_summary(self, pm):
        pm.create_project(name="수정 테스트", period_start="2024-01", summary="기존 요약")
        updated = pm.update_project("수정 테스트", summary="새 요약")
        assert updated.summary == "새 요약"

    def test_update_persisted(self, pm):
        pm.create_project(name="영속성 테스트", period_start="2024-01", summary="원본")
        pm.update_project("영속성 테스트", summary="수정됨")
        reloaded = pm.get_project("영속성 테스트")
        assert reloaded is not None
        assert reloaded.summary == "수정됨"

    def test_update_nonexistent_raises(self, pm):
        with pytest.raises(DevfolioProjectNotFoundError):
            pm.update_project("없는 프로젝트", summary="...")


# ---------------------------------------------------------------------------
# 프로젝트 삭제
# ---------------------------------------------------------------------------

class TestDeleteProject:
    def test_delete_existing(self, pm, tmp_devfolio):
        pm.create_project(name="삭제 테스트", period_start="2024-01")
        result = pm.delete_project("삭제 테스트")
        assert result is True
        assert pm.get_project("삭제 테스트") is None

    def test_delete_nonexistent_raises(self, pm):
        with pytest.raises(DevfolioProjectNotFoundError):
            pm.delete_project("없는 프로젝트")


# ---------------------------------------------------------------------------
# 프로젝트 목록 및 필터
# ---------------------------------------------------------------------------

class TestListProjects:
    def test_list_all(self, pm):
        pm.create_project(name="A", type="company", period_start="2024-01")
        pm.create_project(name="B", type="side", period_start="2024-02")
        assert len(pm.list_projects()) == 2

    def test_filter_by_type(self, pm):
        pm.create_project(name="회사", type="company", period_start="2024-01")
        pm.create_project(name="사이드", type="side", period_start="2024-02")
        result = pm.list_projects(type_filter="company")
        assert len(result) == 1
        assert result[0].name == "회사"

    def test_filter_by_stack(self, pm):
        pm.create_project(name="A", tech_stack=["Spring Boot", "Java"], period_start="2024-01")
        pm.create_project(name="B", tech_stack=["Django", "Python"], period_start="2024-02")
        result = pm.list_projects(stack_filter="spring")
        assert len(result) == 1
        assert result[0].name == "A"

    def test_filter_by_tag(self, pm):
        pm.create_project(name="C", tags=["backend", "cicd"], period_start="2024-01")
        pm.create_project(name="D", tags=["frontend"], period_start="2024-02")
        result = pm.list_projects(tag_filter="cicd")
        assert len(result) == 1

    def test_empty_list(self, pm):
        assert pm.list_projects() == []


# ---------------------------------------------------------------------------
# 작업 내역 (Task)
# ---------------------------------------------------------------------------

class TestTaskManagement:
    def test_add_task(self, pm):
        pm.create_project(name="태스크 테스트", period_start="2024-01")
        task = pm.add_task(
            project_name="태스크 테스트",
            name="기능 구현",
            problem="문제 설명",
            solution="해결 방법",
            result="성과",
            tech_used=["Python"],
        )
        assert task.name == "기능 구현"
        project = pm.get_project("태스크 테스트")
        assert len(project.tasks) == 1

    def test_add_task_to_nonexistent_project_raises(self, pm):
        with pytest.raises(DevfolioProjectNotFoundError):
            pm.add_task(project_name="없는 프로젝트", name="작업")

    def test_update_task(self, pm):
        pm.create_project(name="태스크 수정", period_start="2024-01")
        pm.add_task(project_name="태스크 수정", name="원래 작업", problem="원래 문제")
        updated = pm.update_task("태스크 수정", "원래 작업", problem="새 문제")
        assert updated.problem == "새 문제"

    def test_update_task_invalidates_ai_cache(self, pm):
        pm.create_project(name="캐시 테스트", period_start="2024-01")
        pm.add_task(project_name="캐시 테스트", name="캐시 작업")
        pm.save_task_ai_text("캐시 테스트", "캐시 작업", "AI 생성 문구")

        project = pm.get_project("캐시 테스트")
        assert project.tasks[0].ai_generated_text == "AI 생성 문구"

        pm.update_task("캐시 테스트", "캐시 작업", problem="변경된 내용")
        project = pm.get_project("캐시 테스트")
        assert project.tasks[0].ai_generated_text == ""

    def test_update_nonexistent_task_raises(self, pm):
        pm.create_project(name="없는 태스크 프로젝트", period_start="2024-01")
        with pytest.raises(DevfolioTaskNotFoundError):
            pm.update_task("없는 태스크 프로젝트", "없는 작업", problem="...")

    def test_delete_task(self, pm):
        pm.create_project(name="태스크 삭제", period_start="2024-01")
        pm.add_task(project_name="태스크 삭제", name="삭제할 작업")
        assert pm.delete_task("태스크 삭제", "삭제할 작업") is True
        project = pm.get_project("태스크 삭제")
        assert len(project.tasks) == 0

    def test_delete_nonexistent_task_returns_false(self, pm):
        pm.create_project(name="없는 삭제", period_start="2024-01")
        assert pm.delete_task("없는 삭제", "없는 작업") is False

    def test_multiple_tasks_ordered(self, pm):
        pm.create_project(name="멀티 태스크", period_start="2024-01")
        pm.add_task(project_name="멀티 태스크", name="작업 1")
        pm.add_task(project_name="멀티 태스크", name="작업 2")
        pm.add_task(project_name="멀티 태스크", name="작업 3")
        project = pm.get_project("멀티 태스크")
        assert len(project.tasks) == 3
        assert project.tasks[0].name == "작업 1"
        assert project.tasks[2].name == "작업 3"
