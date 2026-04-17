"""Git/GitHub 기반 백업 동기화 서비스."""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from devfolio.core import storage
from devfolio.core.export_engine import ExportEngine
from devfolio.core.template_engine import TemplateEngine
from devfolio.exceptions import DevfolioSyncError, DevfolioSyncNotConfiguredError
from devfolio.log import get_logger
from devfolio.models.config import Config, SyncConfig

logger = get_logger(__name__)

_REPO_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class SyncService:
    def __init__(self, config: Config):
        self.config = config
        self.template_engine = TemplateEngine()
        self.export_engine = ExportEngine()
        self._tz = ZoneInfo(config.timezone)

    @staticmethod
    def normalize_repo_url(value: str) -> str:
        repo = value.strip()
        if not repo:
            raise DevfolioSyncError(
                "GitHub 저장소가 비어 있습니다.",
                hint="`owner/repo` 또는 전체 저장소 URL을 입력하세요.",
            )

        if _REPO_SLUG_PATTERN.match(repo):
            return f"https://github.com/{repo}.git"

        if repo.startswith(("https://", "http://")):
            normalized = repo.rstrip("/")
            if not normalized.endswith(".git"):
                normalized = normalized + ".git"
            return normalized

        if repo.startswith("git@"):
            return repo

        raise DevfolioSyncError(
            f"지원하지 않는 저장소 형식입니다: {repo}",
            hint="예: `owner/repo` 또는 `https://github.com/owner/repo.git`",
        )

    def _sync_config(self) -> SyncConfig:
        if not self.config.sync.enabled or not self.config.sync.repo_url:
            raise DevfolioSyncNotConfiguredError()
        return self.config.sync

    def _run_command(
        self,
        args: list[str],
        cwd: Optional[Path] = None,
        check: bool = True,
        error_message: str = "",
        hint: str = "",
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                args,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise DevfolioSyncError(
                f"필수 명령을 찾을 수 없습니다: {args[0]}",
                hint=hint or f"`{args[0]}` 명령이 설치되어 있는지 확인하세요.",
            ) from exc

        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            message = error_message or detail or "명령 실행에 실패했습니다."
            raise DevfolioSyncError(message, hint=hint)

        return result

    def _current_timestamp(self) -> datetime:
        return datetime.now(self._tz)

    def _update_state(
        self,
        status: str,
        last_commit: Optional[str] = None,
        last_error: str = "",
    ) -> None:
        state = {
            "last_synced_at": self._current_timestamp().isoformat(),
            "last_commit": last_commit or "",
            "last_status": status,
            "last_error": last_error,
        }
        storage.save_sync_state(state)

    def _ensure_git_available(self) -> None:
        self._run_command(
            ["git", "--version"],
            error_message="Git이 설치되어 있지 않습니다.",
            hint="Git을 설치한 뒤 다시 시도하세요.",
        )

    def validate_remote_access(self) -> None:
        sync = self._sync_config()
        self._ensure_git_available()

        gh_error = ""
        gh_installed = shutil.which("gh") is not None
        if gh_installed:
            gh_auth = self._run_command(["gh", "auth", "status"], check=False)
            gh_error = gh_auth.stderr.strip() or gh_auth.stdout.strip()

        remote = self._run_command(
            ["git", "ls-remote", sync.repo_url, "HEAD"],
            check=False,
        )
        if remote.returncode != 0:
            detail = remote.stderr.strip() or remote.stdout.strip()
            hint = (
                "`gh auth login` 또는 Git credential 설정 후 다시 시도하세요."
                if gh_error or gh_installed
                else "저장소 URL과 Git 인증 상태를 확인하세요."
            )
            raise DevfolioSyncError(
                "GitHub 저장소에 접근할 수 없습니다." + (f"\n  {detail}" if detail else ""),
                hint=hint,
            )

    def _local_repo_dir(self) -> Path:
        return storage.SYNC_REPO_DIR

    def _ensure_local_repo(self, sync: SyncConfig) -> Path:
        repo_dir = self._local_repo_dir()
        repo_dir.parent.mkdir(parents=True, exist_ok=True)

        if repo_dir.exists() and not (repo_dir / ".git").exists():
            if any(repo_dir.iterdir()):
                raise DevfolioSyncError(
                    "동기화 작업 디렉터리가 Git 저장소가 아닙니다.",
                    hint=f"`{repo_dir}`를 정리한 뒤 다시 시도하세요.",
                )

        if not (repo_dir / ".git").exists():
            self._run_command(
                ["git", "clone", sync.repo_url, str(repo_dir)],
                error_message="동기화 저장소를 clone할 수 없습니다.",
                hint="저장소 URL과 접근 권한을 확인하세요.",
            )

        remote_url = self._run_command(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_dir,
            error_message="동기화 저장소의 origin 원격을 확인할 수 없습니다.",
        ).stdout.strip()

        if remote_url != sync.repo_url:
            raise DevfolioSyncError(
                "로컬 동기화 저장소의 origin이 현재 설정과 다릅니다.",
                hint="`devfolio sync setup`으로 저장소를 다시 설정하거나 sync_repo를 정리하세요.",
            )

        return repo_dir

    def _ensure_clean_repo(self, repo_dir: Path) -> None:
        status = self._run_command(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            error_message="동기화 저장소 상태를 확인할 수 없습니다.",
        ).stdout.strip()
        if status:
            raise DevfolioSyncError(
                "동기화 저장소에 커밋되지 않은 변경이 있습니다.",
                hint=f"`{repo_dir}`에서 변경 사항을 정리한 뒤 다시 시도하세요.",
            )

    def _prepare_branch(self, repo_dir: Path, sync: SyncConfig) -> None:
        remote_branch = self._run_command(
            ["git", "ls-remote", "--heads", sync.repo_url, sync.branch],
            check=False,
        ).stdout.strip()
        has_head = self._run_command(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=repo_dir,
            check=False,
        ).returncode == 0
        local_branch = self._run_command(
            ["git", "rev-parse", "--verify", sync.branch],
            cwd=repo_dir,
            check=False,
        ).returncode == 0

        if remote_branch:
            self._run_command(
                ["git", "fetch", "origin", sync.branch],
                cwd=repo_dir,
                error_message="원격 브랜치 정보를 가져올 수 없습니다.",
            )
            checkout_args = (
                ["git", "checkout", "--", sync.branch]
                if local_branch
                else ["git", "checkout", "-B", sync.branch, f"origin/{sync.branch}"]
            )
            self._run_command(
                checkout_args,
                cwd=repo_dir,
                error_message="동기화 브랜치를 체크아웃할 수 없습니다.",
            )
            self._run_command(
                ["git", "pull", "--ff-only", "origin", sync.branch],
                cwd=repo_dir,
                error_message="원격 브랜치를 fast-forward로 가져올 수 없습니다.",
                hint="원격 저장소에 충돌되는 변경이 없는지 확인하세요.",
            )
            return

        if has_head:
            self._run_command(
                ["git", "checkout", "-B", sync.branch],
                cwd=repo_dir,
                error_message="동기화 브랜치를 생성할 수 없습니다.",
            )
        else:
            self._run_command(
                ["git", "checkout", "--orphan", sync.branch],
                cwd=repo_dir,
                error_message="빈 저장소에서 브랜치를 생성할 수 없습니다.",
            )

    def _reset_directory(self, directory: Path) -> None:
        if directory.exists():
            for child in directory.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        directory.mkdir(parents=True, exist_ok=True)

    def _write_snapshot(self, repo_dir: Path) -> list[Path]:
        data_dir = repo_dir / "data"
        projects_dir = data_dir / "projects"
        exports_dir = repo_dir / "exports"

        data_dir.mkdir(parents=True, exist_ok=True)
        self._reset_directory(projects_dir)
        self._reset_directory(exports_dir)

        config_path = storage.get_config_path()
        if config_path is None:
            raise DevfolioSyncError(
                "현재 설정 파일을 찾을 수 없습니다.",
                hint="`devfolio init`을 다시 실행해 설정 파일을 생성하세요.",
            )
        shutil.copy2(config_path, data_dir / "config.yaml")

        for project_file in storage.get_project_file_paths():
            shutil.copy2(project_file, projects_dir / project_file.name)

        projects = storage.list_projects()
        config = storage.load_config()
        template_name = config.export.default_template or "default"

        resume_md = self.template_engine.render(
            projects=projects,
            config=config,
            template_name=template_name,
            doc_type="resume",
        )
        portfolio_md = self.template_engine.render(
            projects=projects,
            config=config,
            template_name=template_name,
            doc_type="portfolio",
        )

        (exports_dir / "resume.md").write_text(resume_md, encoding="utf-8")
        (exports_dir / "portfolio.md").write_text(portfolio_md, encoding="utf-8")

        resume_html = self.export_engine.build_html_document(
            self.export_engine._md_to_html_body(resume_md),
            title="DevFolio Resume",
        )
        portfolio_html = self.export_engine.build_html_document(
            self.export_engine._md_to_html_body(portfolio_md),
            title="DevFolio Portfolio",
        )
        (exports_dir / "resume.html").write_text(resume_html, encoding="utf-8")
        (exports_dir / "portfolio.html").write_text(portfolio_html, encoding="utf-8")

        return [
            data_dir / "config.yaml",
            *sorted(projects_dir.glob("*.yaml")),
            exports_dir / "resume.md",
            exports_dir / "resume.html",
            exports_dir / "portfolio.md",
            exports_dir / "portfolio.html",
        ]

    def _current_head(self, repo_dir: Path) -> Optional[str]:
        head = self._run_command(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            check=False,
        )
        if head.returncode != 0:
            return None
        return head.stdout.strip() or None

    def run(self) -> dict[str, Any]:
        sync = self._sync_config()

        try:
            logger.info("동기화 시작: %s (branch: %s)", sync.repo_url, sync.branch)
            self.validate_remote_access()
            repo_dir = self._ensure_local_repo(sync)
            self._ensure_clean_repo(repo_dir)
            self._prepare_branch(repo_dir, sync)
            written_files = self._write_snapshot(repo_dir)

            status_after = self._run_command(
                ["git", "status", "--porcelain"],
                cwd=repo_dir,
                error_message="동기화 저장소 변경 사항을 확인할 수 없습니다.",
            ).stdout.strip()

            current_head = self._current_head(repo_dir)
            if not status_after:
                self._update_state(status="clean", last_commit=current_head, last_error="")
                return {
                    "changed": False,
                    "commit": current_head,
                    "repo_dir": repo_dir,
                    "files": written_files,
                }

            timestamp = self._current_timestamp().strftime("%Y-%m-%d %H:%M KST")
            message = f"sync: {timestamp}"

            self._run_command(
                ["git", "add", "-A"],
                cwd=repo_dir,
                error_message="동기화 파일을 staging할 수 없습니다.",
            )
            self._run_command(
                ["git", "commit", "-m", message],
                cwd=repo_dir,
                error_message="동기화 커밋 생성에 실패했습니다.",
            )
            self._run_command(
                ["git", "push", "-u", "origin", sync.branch],
                cwd=repo_dir,
                error_message="동기화 내용을 원격 저장소에 push할 수 없습니다.",
                hint="GitHub 저장소 권한과 인증 상태를 확인하세요.",
            )

            current_head = self._current_head(repo_dir)
            self._update_state(status="success", last_commit=current_head, last_error="")
            return {
                "changed": True,
                "commit": current_head,
                "repo_dir": repo_dir,
                "files": written_files,
                "message": message,
            }
        except DevfolioSyncError as exc:
            self._update_state(status="error", last_commit="", last_error=exc.message)
            raise

    def get_status(self) -> dict[str, Any]:
        sync = self.config.sync
        state = storage.load_sync_state()
        repo_dir = self._local_repo_dir()
        return {
            "enabled": sync.enabled,
            "repo_url": sync.repo_url,
            "branch": sync.branch,
            "repo_dir": repo_dir,
            "repo_exists": (repo_dir / ".git").exists(),
            "last_synced_at": state.get("last_synced_at", ""),
            "last_commit": state.get("last_commit", ""),
            "last_status": state.get("last_status", ""),
            "last_error": state.get("last_error", ""),
        }
