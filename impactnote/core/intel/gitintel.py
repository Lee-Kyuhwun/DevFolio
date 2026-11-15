"""Git 이력 분석 — 읽기 전용 명령만 사용한다.

원본 저장소의 파일·브랜치·인덱스를 변경하지 않는다(checkout/reset/merge 금지).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from impactnote.core.intel.models import GitCommit

MAX_COMMITS = 240
MAX_PATCH_CHARS = 7000
_FIELD = "\x1f"
_RECORD = "\x1e"


class GitError(RuntimeError):
    pass


class GitRepo:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.is_repo = (self.root / ".git").exists()

    # -- 기본 ------------------------------------------------------------
    def _run(self, *args: str, timeout: int = 25) -> str:
        try:
            process = subprocess.run(
                ["git", "-C", str(self.root), *args],
                capture_output=True,
                text=True,
                errors="ignore",
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitError(f"git 실행 실패: {exc}") from exc
        if process.returncode != 0:
            raise GitError(process.stderr.strip()[:300] or "git 명령 실패")
        return process.stdout

    def head_sha(self) -> str:
        if not self.is_repo:
            return ""
        try:
            return self._run("rev-parse", "HEAD").strip()
        except GitError:
            return ""

    def user_email(self) -> str:
        if not self.is_repo:
            return ""
        try:
            return self._run("config", "user.email").strip()
        except GitError:
            return ""

    def tracked_files(self) -> set[str]:
        if not self.is_repo:
            return set()
        try:
            output = self._run("ls-files")
        except GitError:
            return set()
        return {line.strip() for line in output.splitlines() if line.strip()}

    # -- 커밋 ------------------------------------------------------------
    def commits(self, limit: int = MAX_COMMITS) -> list[GitCommit]:
        if not self.is_repo:
            return []
        # 레코드 구분자를 헤더 앞에 두어야 numstat 이 해당 커밋 블록에 속한다.
        fmt = f"{_RECORD}%H{_FIELD}%an{_FIELD}%ae{_FIELD}%ad{_FIELD}%s"
        try:
            output = self._run(
                "log",
                "--all",
                "--date=iso-strict",
                "--numstat",
                f"--pretty=format:{fmt}",
                f"-n{max(1, limit)}",
            )
        except GitError:
            return []
        commits: list[GitCommit] = []
        for raw in output.split(_RECORD):
            block = raw.strip("\n")
            if not block.strip():
                continue
            lines = block.splitlines()
            meta = lines[0].split(_FIELD)
            if len(meta) < 5:
                continue
            sha, author, email, date, subject = meta[:5]
            insertions = deletions = 0
            files: list[str] = []
            for line in lines[1:]:
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                added, removed, path = parts[0], parts[1], parts[2]
                if added.isdigit():
                    insertions += int(added)
                if removed.isdigit():
                    deletions += int(removed)
                if path and path != "-":
                    files.append(path)
            lower = subject.lower()
            commits.append(
                GitCommit(
                    sha=sha,
                    short=sha[:8],
                    date=date[:10],
                    author=author,
                    email=email,
                    subject=subject,
                    insertions=insertions,
                    deletions=deletions,
                    files=files[:80],
                    is_revert=lower.startswith("revert")
                    or "this reverts commit" in lower,
                    is_merge=lower.startswith("merge") and not files,
                )
            )
        return commits

    # -- 파일/패치 --------------------------------------------------------
    def file_at(self, revision: str, path: str) -> str:
        if not self.is_repo:
            return ""
        try:
            return self._run("show", f"{revision}:{path}", timeout=15)
        except GitError:
            return ""

    def parent(self, sha: str) -> str:
        try:
            line = self._run("rev-list", "--parents", "-n", "1", sha).split()
            return line[1] if len(line) > 1 else ""
        except GitError:
            return ""

    def patch(self, sha: str, path: str) -> str:
        if not self.is_repo:
            return ""
        try:
            text = self._run(
                "show", "--format=", "--unified=2", sha, "--", path, timeout=20
            )
        except GitError:
            return ""
        return text[:MAX_PATCH_CHARS]

    def deleted_documents(self, limit: int = 20) -> list[tuple[str, str]]:
        if not self.is_repo:
            return []
        try:
            output = self._run(
                "log",
                "--all",
                "--diff-filter=D",
                "--name-only",
                f"--pretty=format:COMMIT{_FIELD}%H",
                f"-n{max(1, limit)}",
            )
        except GitError:
            return []
        results: list[tuple[str, str]] = []
        current = ""
        for line in output.splitlines():
            if line.startswith(f"COMMIT{_FIELD}"):
                current = line.split(_FIELD, 1)[1].strip()
            elif line.strip() and current:
                results.append((line.strip(), current))
        return results[:limit]

    def changed_files(self, sha: str) -> list[str]:
        for commit in self.commits(limit=MAX_COMMITS):
            if commit.sha == sha:
                return commit.files
        return []


__all__ = ["GitError", "GitRepo", "MAX_COMMITS"]
