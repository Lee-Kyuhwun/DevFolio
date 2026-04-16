"""CLI 워크플로우 회귀 테스트."""

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from devfolio.core import storage
from devfolio.core.project_manager import ProjectManager
from devfolio.main import app
from devfolio.models.config import Config

runner = CliRunner()


@pytest.fixture
def cli_store(tmp_path):
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


def test_data_import_accepts_yaml(cli_store):
    sample = cli_store / "sample.yaml"
    sample.write_text(
        """id: cli_yaml
name: YAML 프로젝트
type: company
period:
  start: "2024-01"
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["data", "import", str(sample), "--yes"])

    assert result.exit_code == 0, result.stdout
    project = ProjectManager().get_project("YAML 프로젝트")
    assert project is not None
    assert project.id == "cli_yaml"


def test_data_import_accepts_json(cli_store):
    sample = cli_store / "sample.json"
    sample.write_text(
        json.dumps(
            {
                "id": "cli_json",
                "name": "JSON 프로젝트",
                "type": "side",
                "period": {"start": "2024-02"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["data", "import", str(sample), "--yes"])

    assert result.exit_code == 0, result.stdout
    project = ProjectManager().get_project("JSON 프로젝트")
    assert project is not None
    assert project.id == "cli_json"


def test_sync_setup_saves_normalized_repo_url(cli_store):
    with patch("devfolio.commands.sync.SyncService.validate_remote_access", return_value=None):
        result = runner.invoke(
            app,
            ["sync", "setup", "--repo", "openai/devfolio-backup", "--branch", "backup"],
        )

    assert result.exit_code == 0, result.stdout
    config = storage.load_config()
    assert config.sync.enabled is True
    assert config.sync.repo_url == "https://github.com/openai/devfolio-backup.git"
    assert config.sync.branch == "backup"
