"""보고된 결함 회귀 테스트.

각 테스트는 발견된 버그가 수정되었음을 확인한다.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from devfolio.core.project_manager import ProjectManager
from devfolio.core.template_engine import TemplateEngine
from devfolio.exceptions import DevfolioError, DevfolioTemplateError
from devfolio.models.config import Config, UserConfig
from devfolio.models.project import Period, Project, Task


# ---------------------------------------------------------------------------
# 공용 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_store(tmp_path):
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    with (
        patch("devfolio.core.storage.DEVFOLIO_CONFIG_DIR", tmp_path / "config"),
        patch("devfolio.core.storage.DEVFOLIO_DATA_DIR", tmp_path),
        patch("devfolio.core.storage.PROJECTS_DIR", projects_dir),
        patch("devfolio.core.storage.EXPORTS_DIR", tmp_path / "exports"),
        patch("devfolio.core.storage.TEMPLATES_DIR", templates_dir),
        patch("devfolio.core.template_engine.TEMPLATES_DIR", templates_dir),
        patch("devfolio.core.storage.CONFIG_FILE", tmp_path / "config" / "config.yaml"),
        patch("devfolio.core.storage._LEGACY_HOME", tmp_path / "legacy"),
        patch("devfolio.core.storage._LEGACY_CONFIG", tmp_path / "legacy" / "config.yaml"),
    ):
        (tmp_path / "config").mkdir()
        (tmp_path / "exports").mkdir()
        yield tmp_path


@pytest.fixture
def pm(tmp_store):
    return ProjectManager()


# ---------------------------------------------------------------------------
# 결함 1: JSON import/export — from_dict/to_dict 미존재 오류
# ---------------------------------------------------------------------------

class TestDefect1JSONSerialization:
    """Project에 from_dict/to_dict가 없어도 model_validate/model_dump로 동작해야 한다."""

    def test_model_dump_produces_json_serializable_dict(self):
        project = Project(
            id="test",
            name="테스트 프로젝트",
            period=Period(start="2024-01"),
            tech_stack=["Python"],
        )
        data = project.model_dump()
        # JSON 직렬화 가능 여부
        serialized = json.dumps(data, ensure_ascii=False)
        assert "테스트 프로젝트" in serialized

    def test_model_validate_round_trip(self):
        project = Project(
            id="roundtrip",
            name="라운드트립",
            period=Period(start="2024-01", end="2024-06"),
            tech_stack=["Java", "Spring"],
            tasks=[
                Task(id="t1", name="작업 1", period=Period(start="2024-02"))
            ],
        )
        data = project.model_dump()
        restored = Project.model_validate(data)

        assert restored.name == project.name
        assert restored.period.start == project.period.start
        assert len(restored.tasks) == 1
        assert restored.tasks[0].name == "작업 1"

    def test_project_has_no_from_dict(self):
        """from_dict가 없음을 명시적으로 검증 — 호출 시 AttributeError."""
        project = Project(id="x", name="X")
        assert not hasattr(project, "from_dict")
        assert not hasattr(project, "to_dict")

    def test_json_list_roundtrip(self):
        """복수 프로젝트 JSON 직렬화/역직렬화."""
        projects = [
            Project(id=f"p{i}", name=f"프로젝트 {i}", period=Period(start="2024-01"))
            for i in range(3)
        ]
        raw = json.dumps([p.model_dump() for p in projects], ensure_ascii=False)
        restored = [Project.model_validate(d) for d in json.loads(raw)]
        assert [p.name for p in restored] == [p.name for p in projects]


# ---------------------------------------------------------------------------
# 결함 2: Period — 빈 start 문자열이 ValidationError를 일으켜서는 안 됨
# ---------------------------------------------------------------------------

class TestDefect2PeriodEmptyString:
    """Period(start="")는 start=None으로 정규화되어야 한다."""

    def test_empty_start_becomes_none(self):
        p = Period(start="")
        assert p.start is None

    def test_none_start_is_valid(self):
        p = Period(start=None)
        assert p.start is None

    def test_empty_end_becomes_none(self):
        p = Period(start="2024-01", end="")
        assert p.end is None

    def test_whitespace_start_becomes_none(self):
        p = Period(start="   ")
        assert p.start is None

    def test_task_default_period_does_not_raise(self):
        """Task의 period 기본값(Period())이 ValidationError 없이 생성되어야 한다."""
        t = Task(id="x", name="테스트 작업")
        assert t.period.start is None

    def test_project_default_period_does_not_raise(self):
        """Project의 period 기본값(Period())이 ValidationError 없이 생성되어야 한다."""
        p = Project(id="x", name="테스트 프로젝트")
        assert p.period.start is None

    def test_period_manager_empty_start(self, pm):
        """period_start="" 전달 시 ProjectManager가 예외 없이 저장해야 한다."""
        project = pm.create_project(name="빈 기간 프로젝트", period_start="")
        assert project.period.start is None

    def test_period_display_with_none_start(self):
        p = Period()
        assert p.display() == "? ~ 현재"

    def test_valid_period_unchanged(self):
        p = Period(start="2024-01", end="2024-12")
        assert p.start == "2024-01"
        assert p.end == "2024-12"
        assert p.display() == "2024-01 ~ 2024-12"

    def test_invalid_format_still_raises(self):
        with pytest.raises(ValidationError):
            Period(start="2024/01")


# ---------------------------------------------------------------------------
# 결함 3: 중복 프로젝트 ID 충돌 — 같은 이름 생성 시 명시적 오류
# ---------------------------------------------------------------------------

class TestDefect3DuplicateProjectID:
    def test_same_name_raises_error(self, pm):
        pm.create_project(name="중복 테스트 프로젝트", period_start="2024-01")
        with pytest.raises(DevfolioError, match="이미 같은 이름"):
            pm.create_project(name="중복 테스트 프로젝트", period_start="2024-02")

    def test_different_name_same_id_gets_suffix(self, pm):
        """정규화 후 같은 ID가 나오는 다른 이름은 suffix로 구별된다."""
        # "A B"와 "a b"는 정규화 시 "a_b"로 같은 ID
        p1 = pm.create_project(name="a b", period_start="2024-01")
        p2 = pm.create_project(name="A B", period_start="2024-02")

        assert p1.id != p2.id
        assert p2.id.startswith(p1.id)  # "a_b" vs "a_b_2"

    def test_no_silent_overwrite(self, pm, tmp_store):
        """같은 이름으로 두 번 생성해도 첫 번째 데이터가 유실되지 않는다."""
        pm.create_project(name="원본 프로젝트", period_start="2024-01", summary="원본 요약")
        with pytest.raises(DevfolioError):
            pm.create_project(name="원본 프로젝트", period_start="2024-06", summary="덮어쓴 요약")
        # 원본 데이터가 보존되어야 함
        existing = pm.get_project("원본 프로젝트")
        assert existing.summary == "원본 요약"


# ---------------------------------------------------------------------------
# 결함 4: 프로젝트 rename — 구 파일 삭제 및 ID 갱신
# ---------------------------------------------------------------------------

class TestDefect4ProjectRename:
    def test_rename_updates_id(self, pm):
        old = pm.create_project(name="구 이름 프로젝트", period_start="2024-01")
        old_id = old.id

        # model_copy로 id/name 모두 갱신
        from devfolio.core.storage import delete_project_file, project_id_from_name, save_project

        new_name = "새 이름 프로젝트"
        new_id = project_id_from_name(new_name)
        updated = old.model_copy(update={"name": new_name, "id": new_id})
        save_project(updated)
        delete_project_file(old_id)

        # 새 이름으로 조회 가능
        found = pm.get_project(new_name)
        assert found is not None
        assert found.id == new_id

    def test_old_file_deleted_after_rename(self, pm, tmp_store):
        old = pm.create_project(name="삭제될 구파일", period_start="2024-01")
        old_id = old.id

        from devfolio.core.storage import (
            PROJECTS_DIR,
            delete_project_file,
            project_id_from_name,
            save_project,
        )

        new_name = "새 파일명 프로젝트"
        new_id = project_id_from_name(new_name)
        updated = old.model_copy(update={"name": new_name, "id": new_id})
        save_project(updated)
        delete_project_file(old_id)

        # 구 파일이 남아 있지 않아야 함
        old_file = PROJECTS_DIR / f"{old_id}.yaml"
        assert not old_file.exists()

        # 새 파일 생성 확인
        new_file = PROJECTS_DIR / f"{new_id}.yaml"
        assert new_file.exists()

    def test_rename_does_not_duplicate_records(self, pm, tmp_store):
        """rename 후 조회 시 두 개의 레코드가 생기면 안 된다."""
        from devfolio.core.storage import (
            PROJECTS_DIR,
            delete_project_file,
            project_id_from_name,
            save_project,
        )

        old = pm.create_project(name="중복 방지 원본", period_start="2024-01")
        old_id = old.id
        new_name = "중복 방지 신규"
        new_id = project_id_from_name(new_name)

        updated = old.model_copy(update={"name": new_name, "id": new_id})
        save_project(updated)
        delete_project_file(old_id)

        all_projects = pm.list_projects()
        assert len(all_projects) == 1
        assert all_projects[0].name == new_name


# ---------------------------------------------------------------------------
# 결함 5: 템플릿 오류 — TemplateNotFound는 폴백, 렌더링 오류는 전파
# ---------------------------------------------------------------------------

class TestDefect5TemplateErrors:
    def _make_config(self) -> Config:
        config = Config()
        config.user = UserConfig(name="테스트 유저", email="test@example.com")
        return config

    def _make_projects(self) -> list[Project]:
        return [
            Project(
                id="t1",
                name="테스트 프로젝트",
                period=Period(start="2024-01"),
                tech_stack=["Python"],
                summary="요약",
            )
        ]

    def test_missing_template_falls_back_to_builtin(self):
        """존재하지 않는 템플릿명 → 내장 폴백으로 정상 렌더링."""
        engine = TemplateEngine()
        result = engine.render(
            projects=self._make_projects(),
            config=self._make_config(),
            template_name="nonexistent_xyz",
            doc_type="resume",
        )
        assert "테스트 유저" in result
        assert "테스트 프로젝트" in result

    def test_portfolio_fallback_is_not_resume(self):
        """portfolio doc_type은 resume 내장 템플릿으로 폴백되면 안 된다."""
        engine = TemplateEngine()
        resume_result = engine.render(
            projects=self._make_projects(),
            config=self._make_config(),
            template_name="nonexistent_xyz",
            doc_type="resume",
        )
        portfolio_result = engine.render(
            projects=self._make_projects(),
            config=self._make_config(),
            template_name="nonexistent_xyz",
            doc_type="portfolio",
        )
        # portfolio는 "포트폴리오"가 포함된 다른 내용이어야 함
        assert portfolio_result != resume_result
        assert "포트폴리오" in portfolio_result

    def test_template_render_error_raises_devfolio_error(self, tmp_path):
        """템플릿 파일은 있지만 렌더링 오류 → DevfolioTemplateError 전파."""
        from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

        # 렌더링 오류를 일으키는 악성 템플릿 생성
        broken_dir = tmp_path / "broken_templates"
        broken_dir.mkdir()
        (broken_dir / "resume_default.md.j2").write_text(
            "{{ undefined_var.nonexistent_method() }}", encoding="utf-8"
        )

        engine = TemplateEngine()
        # 내부 _env를 broken env로 교체
        engine._env = Environment(
            loader=FileSystemLoader(str(broken_dir)),
            autoescape=select_autoescape([]),
            undefined=StrictUndefined,
        )

        with pytest.raises(DevfolioTemplateError):
            engine.render(
                projects=self._make_projects(),
                config=self._make_config(),
                template_name="default",
                doc_type="resume",
            )

    def test_project_single_fallback(self):
        """project_single 템플릿 없을 때도 내장 폴백으로 정상 렌더링."""
        engine = TemplateEngine()
        # 파일 시스템 템플릿 없는 환경 시뮬레이션
        engine._env = None

        result = engine.render_project(
            project=self._make_projects()[0],
            config=self._make_config(),
        )
        assert "테스트 프로젝트" in result

    def test_builtin_fallback_map_has_all_doc_types(self):
        """_BUILTIN_FALLBACK에 resume/portfolio 모두 있어야 한다."""
        from devfolio.core.template_engine import _BUILTIN_FALLBACK

        assert "resume" in _BUILTIN_FALLBACK
        assert "portfolio" in _BUILTIN_FALLBACK
        assert _BUILTIN_FALLBACK["resume"] != _BUILTIN_FALLBACK["portfolio"]
