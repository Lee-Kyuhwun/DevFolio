"""Git 저장소 스캐너 — 본인 커밋 탐지, 지표 산출, 프로젝트 자동 생성."""

from __future__ import annotations

import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from devfolio.exceptions import DevfolioError
from devfolio.log import get_logger

logger = get_logger(__name__)


# 개선/성과 키워드 (한/영) — 커밋 메시지 분류용
IMPROVE_KEYWORDS = {
    "perf": ["perf", "performance", "optimize", "optimization", "speed", "faster",
             "성능", "최적화", "속도", "개선"],
    "fix": ["fix", "bug", "hotfix", "patch", "resolve", "버그", "수정", "장애"],
    "refactor": ["refactor", "cleanup", "restructure", "리팩터", "리팩토링", "정리"],
    "feat": ["feat", "feature", "add", "implement", "introduce", "기능", "구현", "추가"],
    "test": ["test", "coverage", "테스트"],
    "security": ["security", "secure", "auth", "vuln", "보안", "취약"],
}

LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".jsx": "JavaScript", ".java": "Java", ".kt": "Kotlin", ".go": "Go",
    ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".c": "C",
    ".cpp": "C++", ".cc": "C++", ".h": "C/C++", ".swift": "Swift",
    ".scala": "Scala", ".dart": "Dart", ".vue": "Vue", ".html": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".sql": "SQL", ".sh": "Shell",
    ".yml": "YAML", ".yaml": "YAML", ".md": "Markdown", ".tf": "Terraform",
    ".dockerfile": "Docker",
}


@dataclass
class CommitInfo:
    sha: str
    author_name: str
    author_email: str
    date: str  # YYYY-MM-DD
    subject: str
    insertions: int = 0
    deletions: int = 0
    files_changed: int = 0


@dataclass
class ScanResult:
    repo_path: Path
    repo_url: str
    repo_name: str
    head_sha: str
    author_email: str
    commits: list[CommitInfo] = field(default_factory=list)
    total_insertions: int = 0
    total_deletions: int = 0
    files_touched: set[str] = field(default_factory=set)
    languages: Counter = field(default_factory=Counter)
    category_counts: Counter = field(default_factory=Counter)  # feat/fix/perf/...
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    total_commits_repo: int = 0  # 저장소 전체 커밋 수

    @property
    def authorship_ratio(self) -> float:
        if self.total_commits_repo == 0:
            return 0.0
        return len(self.commits) / self.total_commits_repo

    def to_dict(self) -> dict:
        return {
            "repo_url": self.repo_url,
            "repo_name": self.repo_name,
            "head_sha": self.head_sha,
            "author_email": self.author_email,
            "commit_count": len(self.commits),
            "total_commits_repo": self.total_commits_repo,
            "authorship_ratio": round(self.authorship_ratio, 3),
            "insertions": self.total_insertions,
            "deletions": self.total_deletions,
            "files_touched": len(self.files_touched),
            "languages": dict(self.languages.most_common(10)),
            "categories": dict(self.category_counts),
            "first_date": self.first_date,
            "last_date": self.last_date,
        }


def _run_git(repo_path: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path)] + args,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except FileNotFoundError as e:
        raise DevfolioError(
            "git 명령을 찾을 수 없습니다.",
            hint="git을 설치한 후 다시 시도하세요.",
        ) from e
    except subprocess.CalledProcessError as e:
        raise DevfolioError(
            f"git 명령 실패: git {' '.join(args)}",
            hint=(e.stderr or "").strip()[:200],
        ) from e


def _is_git_repo(path: Path) -> bool:
    if not (path / ".git").exists():
        return False
    return True


def _detect_repo_url(repo_path: Path) -> str:
    try:
        out = _run_git(repo_path, ["config", "--get", "remote.origin.url"]).strip()
        return out
    except Exception:
        return ""


def _categorize(subject: str) -> list[str]:
    lowered = subject.lower()
    hits: list[str] = []
    for category, keywords in IMPROVE_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            hits.append(category)
    return hits


def _collect_author_commits(
    repo_path: Path, author_email: str
) -> tuple[list[CommitInfo], int]:
    """저장소 전체에서 author_email 과 일치하는 커밋을 수집한다."""
    # 전체 커밋 수
    try:
        total_out = _run_git(repo_path, ["rev-list", "--count", "HEAD"]).strip()
        total_commits = int(total_out) if total_out else 0
    except Exception:
        total_commits = 0

    # 본인 커밋 로그 + numstat
    # 포맷: delimiter로 구분
    fmt = "--pretty=format:@@COMMIT@@%H%x00%an%x00%ae%x00%ad%x00%s"
    out = _run_git(
        repo_path,
        [
            "log",
            f"--author={author_email}",
            "--date=short",
            "--numstat",
            fmt,
        ],
    )

    commits: list[CommitInfo] = []
    current: Optional[CommitInfo] = None
    for line in out.split("\n"):
        if not line:
            if current is not None:
                commits.append(current)
                current = None
            continue
        if line.startswith("@@COMMIT@@"):
            if current is not None:
                commits.append(current)
            parts = line[len("@@COMMIT@@"):].split("\x00")
            if len(parts) >= 5:
                current = CommitInfo(
                    sha=parts[0],
                    author_name=parts[1],
                    author_email=parts[2],
                    date=parts[3],
                    subject=parts[4],
                )
        else:
            # numstat line: "<ins>\t<del>\t<path>"
            if current is None:
                continue
            m = re.match(r"^(\S+)\t(\S+)\t(.+)$", line)
            if not m:
                continue
            ins_s, del_s, _path = m.groups()
            try:
                ins = int(ins_s) if ins_s != "-" else 0
                dele = int(del_s) if del_s != "-" else 0
            except ValueError:
                ins, dele = 0, 0
            current.insertions += ins
            current.deletions += dele
            current.files_changed += 1
    if current is not None:
        commits.append(current)

    return commits, total_commits


def _collect_file_stats(
    repo_path: Path, commits: list[CommitInfo]
) -> tuple[set[str], Counter]:
    """본인 커밋들에서 변경된 파일/언어를 집계한다."""
    files: set[str] = set()
    langs: Counter = Counter()
    for commit in commits:
        try:
            out = _run_git(
                repo_path,
                ["show", "--no-renames", "--name-only", "--pretty=format:", commit.sha],
            )
        except DevfolioError:
            continue
        for raw in out.split("\n"):
            path = raw.strip()
            if not path:
                continue
            files.add(path)
            ext = Path(path).suffix.lower()
            if ext in LANG_BY_EXT:
                langs[LANG_BY_EXT[ext]] += 1
    return files, langs


def scan_repo(
    repo_path: Path, author_email: str
) -> ScanResult:
    """주어진 git 저장소에서 author_email 로 본인 커밋/지표를 수집한다."""
    repo_path = repo_path.resolve()
    if not _is_git_repo(repo_path):
        raise DevfolioError(
            f"git 저장소가 아닙니다: {repo_path}",
            hint=".git 이 있는 디렉터리를 지정하세요.",
        )
    if not author_email:
        raise DevfolioError(
            "사용자 email 이 설정되어 있지 않습니다.",
            hint="`devfolio config user set --email ...` 로 이메일을 등록하세요.",
        )

    head_sha = _run_git(repo_path, ["rev-parse", "HEAD"]).strip()
    repo_url = _detect_repo_url(repo_path)
    repo_name = (
        Path(repo_url.rstrip("/").split("/")[-1]).stem
        if repo_url
        else repo_path.name
    )

    commits, total_commits = _collect_author_commits(repo_path, author_email)
    if not commits:
        raise DevfolioError(
            f"'{author_email}' 로 작성된 커밋을 찾을 수 없습니다.",
            hint=(
                "이메일이 올바른지 확인하거나, git log --author=... 로 직접 확인해보세요."
            ),
        )

    files_touched, languages = _collect_file_stats(repo_path, commits)

    category_counts: Counter = Counter()
    for c in commits:
        for cat in _categorize(c.subject):
            category_counts[cat] += 1

    dates = sorted(c.date for c in commits if c.date)
    result = ScanResult(
        repo_path=repo_path,
        repo_url=repo_url,
        repo_name=repo_name,
        head_sha=head_sha,
        author_email=author_email,
        commits=commits,
        total_insertions=sum(c.insertions for c in commits),
        total_deletions=sum(c.deletions for c in commits),
        files_touched=files_touched,
        languages=languages,
        category_counts=category_counts,
        first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
        total_commits_repo=total_commits,
    )
    return result


# ---------------------------------------------------------------------------
# Project 모델 생성
# ---------------------------------------------------------------------------

def _to_yyyymm(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    m = re.match(r"^(\d{4})-(\d{2})", date_str)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def _group_commits_into_tasks(
    commits: list[CommitInfo], max_tasks: int = 6
) -> list[dict]:
    """커밋을 카테고리 + 연월로 묶어 Task 후보로 만든다."""
    buckets: dict[tuple[str, str], list[CommitInfo]] = defaultdict(list)
    for c in commits:
        cats = _categorize(c.subject) or ["feat"]
        month = _to_yyyymm(c.date) or "unknown"
        # 주 카테고리 1개만 사용
        buckets[(cats[0], month)].append(c)

    # 사이즈 큰 순으로 정렬, 상위 max_tasks 개만
    ranked = sorted(
        buckets.items(),
        key=lambda kv: (
            sum(x.insertions + x.deletions for x in kv[1]),
            len(kv[1]),
        ),
        reverse=True,
    )[:max_tasks]

    tasks: list[dict] = []
    cat_label = {
        "feat": "기능 개발",
        "fix": "버그 수정 및 안정화",
        "perf": "성능 최적화",
        "refactor": "리팩터링",
        "test": "테스트 보강",
        "security": "보안 강화",
    }
    for (category, month), bucket in ranked:
        months = sorted({_to_yyyymm(c.date) for c in bucket if _to_yyyymm(c.date)})
        ins = sum(c.insertions for c in bucket)
        dels = sum(c.deletions for c in bucket)
        files_n = sum(c.files_changed for c in bucket)
        name = f"{cat_label.get(category, category)} ({month})"
        # 대표 커밋 제목 3개
        top_subjects = [c.subject for c in bucket[:3]]
        problem = ""
        solution = "\n".join(f"- {s}" for s in top_subjects)
        result = (
            f"커밋 {len(bucket)}건 / +{ins} -{dels} LOC / {files_n}개 파일 변경"
        )
        tasks.append(
            {
                "name": name,
                "period_start": months[0] if months else None,
                "period_end": months[-1] if months else None,
                "problem": problem,
                "solution": solution,
                "result": result,
                "keywords": [category],
            }
        )
    return tasks


def build_project_payload(scan: ScanResult) -> dict:
    """ScanResult → create_project/add_task 에 전달할 dict."""
    period_start = _to_yyyymm(scan.first_date)
    period_end = _to_yyyymm(scan.last_date)

    top_langs = [lang for lang, _ in scan.languages.most_common(6)]

    summary_lines = [
        f"{scan.repo_name} — 본인 커밋 {len(scan.commits)}건"
        f" ({scan.authorship_ratio*100:.0f}% 기여)",
        f"+{scan.total_insertions} / -{scan.total_deletions} LOC,"
        f" {len(scan.files_touched)} 파일 변경",
    ]
    if scan.category_counts:
        cats = ", ".join(
            f"{k}:{v}" for k, v in scan.category_counts.most_common()
        )
        summary_lines.append(f"커밋 분류: {cats}")
    summary = " · ".join(summary_lines)

    tasks = _group_commits_into_tasks(scan.commits)

    return {
        "name": scan.repo_name,
        "type": "side",
        "status": "in_progress" if scan.last_date else "done",
        "organization": "",
        "period_start": period_start or "",
        "period_end": period_end,
        "role": "개발자",
        "team_size": 1,
        "tech_stack": top_langs,
        "summary": summary,
        "tags": list(scan.category_counts.keys()),
        "tasks": tasks,
        "repo_url": scan.repo_url,
        "last_commit_sha": scan.head_sha,
        "scan_metrics": scan.to_dict(),
    }
