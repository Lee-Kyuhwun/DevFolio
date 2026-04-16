"""GitHub sync 서비스 단위 테스트."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

from devfolio.core import storage
from devfolio.core.project_manager import ProjectManager
from devfolio.core.sync_service import SyncService
from devfolio.exceptions import DevfolioSyncError
from devfolio.models.config import Config, SyncConfig, UserConfig


@dataclass
class FakeCompletedProcess:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class FakeGitRunner:
    def __init__(
        self,
        repo_url: str,
        status_outputs: list[str],
        *,
        gh_auth_returncode: int = 0,
        gh_auth_stderr: str = "",
        remote_access_returncode: int = 0,
        remote_access_stderr: str = "",
        remote_branch_exists: bool = True,
        has_head: bool = True,
        local_branch_exists: bool = False,
        head: str = "base123",
    ):
        self.repo_url = repo_url
        self.status_outputs = iter(status_outputs)
        self.gh_auth_returncode = gh_auth_returncode
        self.gh_auth_stderr = gh_auth_stderr
        self.remote_access_returncode = remote_access_returncode
        self.remote_access_stderr = remote_access_stderr
        self.remote_branch_exists = remote_branch_exists
        self.has_head = has_head
        self.local_branch_exists = local_branch_exists
        self.head = head
        self.commands: list[tuple[list[str], Optional[Path]]] = []

    def __call__(self, args, cwd=None, check=True, error_message="", hint=""):
        cwd_path = Path(cwd) if cwd else None
        self.commands.append((list(args), cwd_path))

        if args == ["git", "--version"]:
            return FakeCompletedProcess(stdout="git version 2.40.0\n")

        if args[:3] == ["gh", "auth", "status"]:
            return FakeCompletedProcess(
                returncode=self.gh_auth_returncode,
                stderr=self.gh_auth_stderr,
            )

        if args[:2] == ["git", "ls-remote"] and len(args) == 4:
            return FakeCompletedProcess(
                returncode=self.remote_access_returncode,
                stderr=self.remote_access_stderr,
            )

        if args[:3] == ["git", "ls-remote", "--heads"]:
            stdout = "abc refs/heads/main\n" if self.remote_branch_exists else ""
            return FakeCompletedProcess(stdout=stdout)

        if args[:2] == ["git", "clone"]:
            repo_dir = Path(args[-1])
            repo_dir.mkdir(parents=True, exist_ok=True)
            (repo_dir / ".git").mkdir(exist_ok=True)
            return FakeCompletedProcess()

        if args[:4] == ["git", "remote", "get-url", "origin"]:
            return FakeCompletedProcess(stdout=self.repo_url + "\n")

        if args[:3] == ["git", "status", "--porcelain"]:
            return FakeCompletedProcess(stdout=next(self.status_outputs, ""))

        if args[:4] == ["git", "rev-parse", "--verify", "HEAD"]:
            return FakeCompletedProcess(returncode=0 if self.has_head else 1)

        if args[:3] == ["git", "rev-parse", "HEAD"]:
            if not self.head:
                return FakeCompletedProcess(returncode=1)
            return FakeCompletedProcess(stdout=self.head + "\n")

        if args[:3] == ["git", "rev-parse", "--verify"]:
            return FakeCompletedProcess(returncode=0 if self.local_branch_exists else 1)

        if args[:2] == ["git", "commit"]:
            self.head = "new123"
            self.has_head = True
            return FakeCompletedProcess(stdout="[main new123] sync\n")

        if args[:2] == ["git", "push"]:
            return FakeCompletedProcess(stdout="pushed\n")

        if args[:2] == ["git", "add"]:
            return FakeCompletedProcess()

        if args[:2] == ["git", "fetch"]:
            return FakeCompletedProcess()

        if args[:2] == ["git", "checkout"]:
            return FakeCompletedProcess()

        if args[:2] == ["git", "pull"]:
            return FakeCompletedProcess()

        raise AssertionError(f"unexpected command: {args}")


@pytest.fixture
def sync_store(tmp_path):
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
        config = Config()
        config.user = UserConfig(name="홍길동", github="https://github.com/hong")
        config.sync = SyncConfig(
            enabled=True,
            repo_url="https://github.com/example/devfolio-backup.git",
            branch="main",
        )
        storage.save_config(config)
        ProjectManager().create_project(
            name="동기화 테스트 프로젝트",
            period_start="2024-01",
            summary="동기화 테스트 요약",
            tech_stack=["Python"],
        )
        yield tmp_path


def test_sync_run_first_clone_commits_and_writes_files(sync_store):
    service = SyncService(storage.load_config())
    runner = FakeGitRunner(
        repo_url=service.config.sync.repo_url,
        status_outputs=["", " M data/config.yaml\n"],
        remote_branch_exists=True,
        local_branch_exists=False,
        has_head=True,
    )
    service._run_command = runner

    with patch("devfolio.core.sync_service.shutil.which", return_value=None):
        result = service.run()

    sync_repo = storage.SYNC_REPO_DIR
    assert result["changed"] is True
    assert result["commit"] == "new123"
    assert (sync_repo / ".git").exists()
    assert (sync_repo / "data" / "config.yaml").exists()
    assert (sync_repo / "exports" / "resume.md").exists()
    assert (sync_repo / "exports" / "resume.html").exists()
    assert any(cmd[:2] == ["git", "commit"] for cmd, _ in runner.commands)

    state = storage.load_sync_state()
    assert state["last_status"] == "success"
    assert state["last_commit"] == "new123"


def test_sync_run_no_changes_skips_commit_and_push(sync_store):
    service = SyncService(storage.load_config())
    runner = FakeGitRunner(
        repo_url=service.config.sync.repo_url,
        status_outputs=["", ""],
        remote_branch_exists=True,
        local_branch_exists=True,
        has_head=True,
        head="existing123",
    )
    service._run_command = runner

    with patch("devfolio.core.sync_service.shutil.which", return_value=None):
        result = service.run()

    assert result["changed"] is False
    assert result["commit"] == "existing123"
    assert not any(cmd[:2] == ["git", "commit"] for cmd, _ in runner.commands)
    assert not any(cmd[:2] == ["git", "push"] for cmd, _ in runner.commands)

    state = storage.load_sync_state()
    assert state["last_status"] == "clean"
    assert state["last_commit"] == "existing123"


def test_sync_run_stops_when_local_repo_is_dirty(sync_store):
    service = SyncService(storage.load_config())
    runner = FakeGitRunner(
        repo_url=service.config.sync.repo_url,
        status_outputs=[" M stray.txt\n"],
        remote_branch_exists=True,
        has_head=True,
    )
    service._run_command = runner

    with patch("devfolio.core.sync_service.shutil.which", return_value=None):
        with pytest.raises(DevfolioSyncError):
            service.run()

    state = storage.load_sync_state()
    assert state["last_status"] == "error"
    assert "커밋되지 않은 변경" in state["last_error"]


def test_validate_remote_access_reports_auth_failure(sync_store):
    service = SyncService(storage.load_config())
    runner = FakeGitRunner(
        repo_url=service.config.sync.repo_url,
        status_outputs=[],
        gh_auth_returncode=1,
        gh_auth_stderr="not logged in",
        remote_access_returncode=128,
        remote_access_stderr="fatal: could not read Username",
    )
    service._run_command = runner

    with patch("devfolio.core.sync_service.shutil.which", return_value="/usr/bin/gh"):
        with pytest.raises(DevfolioSyncError) as exc_info:
            service.validate_remote_access()

    assert "GitHub 저장소에 접근할 수 없습니다." in exc_info.value.message
    assert "gh auth login" in exc_info.value.hint
