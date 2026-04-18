"""Git 저장소 스캐너 — 본인 커밋 탐지, 코드 구조 분석, 프로젝트 자동 생성.

[Spring 비교]
  외부 프로세스(git)를 실행해 데이터를 수집하고 가공하는 배치 서비스.
  Spring 에서는 ProcessBuilder + @Scheduled 를 사용하는 것과 유사하다.

  주요 흐름:
    scan_repo(analyze=False) → 커밋 수집 + 파일/언어 통계 → ScanResult
    scan_repo(analyze=True)  → 위 + 코드 구조 분석(README/의존성/소스 파일 읽기)
    build_project_payload()  → ScanResult (+ AI 분석 결과) → Project 생성 dict
"""

from __future__ import annotations

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from devfolio.exceptions import DevfolioError
from devfolio.log import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 분류 키워드 / 언어 매핑
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# 코드 구조 분석용 상수
# ---------------------------------------------------------------------------

_README_CANDIDATES = [
    "README.md", "README.rst", "README.txt", "README",
    "Readme.md", "readme.md", "readme.rst",
]
_README_MAX_CHARS = 4000
_FILE_MAX_CHARS = 2000
_TOTAL_MAX_CHARS = 6000

# 이진 파일 확장자 — 읽지 않는다.
_BINARY_EXTENSIONS = {
    ".pyc", ".class", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp",
    ".jar", ".exe", ".so", ".dll", ".wasm", ".zip", ".tar", ".gz",
    ".pdf", ".docx", ".xlsx", ".mp3", ".mp4", ".bin",
}

# entry point 파일 탐지 순서 (glob 패턴 포함).
# 언어 상관없이 순서대로 검색하고 먼저 발견된 파일부터 읽는다.
_ENTRY_POINTS = [
    # Python
    "main.py", "app.py", "server.py", "index.py", "run.py", "manage.py",
    "src/main.py", "src/app.py",
    # JavaScript / TypeScript
    "index.js", "index.ts", "src/index.js", "src/index.ts",
    "app.js", "app.ts", "server.js", "server.ts",
    # Java / Kotlin
    "src/main/java/**/Application.java", "src/main/java/**/Main.java",
    "src/main/kotlin/**/Application.kt",
    # Go
    "main.go", "cmd/main.go",
    # Rust
    "src/main.rs", "src/lib.rs",
    # Ruby
    "app.rb", "config/application.rb",
    # 구조 파악용 설정 파일
    "docker-compose.yml", "docker-compose.yaml", "Makefile",
]


# ---------------------------------------------------------------------------
# 데이터 컨테이너 (dataclass)
# ---------------------------------------------------------------------------

@dataclass
class CommitInfo:
    """커밋 한 건의 정보 (git log 파싱 결과)."""
    sha: str
    author_name: str
    author_email: str
    date: str       # YYYY-MM-DD
    subject: str    # 커밋 메시지 첫 줄
    insertions: int = 0
    deletions: int = 0
    files_changed: int = 0


@dataclass
class ScanResult:
    """저장소 스캔 결과 전체를 담는 컨테이너."""
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
    category_counts: Counter = field(default_factory=Counter)
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    total_commits_repo: int = 0
    # analyze=True 일 때만 채워진다 — README/의존성/소스 파일 내용.
    project_context: dict = field(default_factory=dict)

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


# ---------------------------------------------------------------------------
# Git 명령 실행 헬퍼
# ---------------------------------------------------------------------------

def _run_git(repo_path: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path)] + args,
            capture_output=True, text=True, check=True,
        )
        return result.stdout
    except FileNotFoundError as e:
        raise DevfolioError(
            "git 명령을 찾을 수 없습니다.", hint="git을 설치한 후 다시 시도하세요.",
        ) from e
    except subprocess.CalledProcessError as e:
        raise DevfolioError(
            f"git 명령 실패: git {' '.join(args)}",
            hint=(e.stderr or "").strip()[:200],
        ) from e


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _detect_repo_url(repo_path: Path) -> str:
    try:
        return _run_git(repo_path, ["config", "--get", "remote.origin.url"]).strip()
    except Exception:
        return ""


def _categorize(subject: str) -> list[str]:
    lowered = subject.lower()
    return [
        cat for cat, keywords in IMPROVE_KEYWORDS.items()
        if any(kw in lowered for kw in keywords)
    ]


# ---------------------------------------------------------------------------
# 코드 구조 분석 함수들 (딥 분석)
# ---------------------------------------------------------------------------

def _read_readme(repo_path: Path) -> str:
    """README 파일을 읽어 최대 4000자 반환한다. 없으면 빈 문자열."""
    for name in _README_CANDIDATES:
        p = repo_path / name
        if p.exists() and p.is_file():
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                if len(text) > _README_MAX_CHARS:
                    return text[:_README_MAX_CHARS] + "\n...[truncated]"
                return text
            except OSError:
                return ""
    return ""


def _parse_toml_safe(path: Path) -> dict:
    """TOML 파일을 파싱한다. tomllib(3.11+) → tomli 순서로 폴백."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            tomllib = None  # type: ignore[assignment]

    if tomllib is not None:
        try:
            return tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    # 폴백: 정규식으로 패키지명만 추출
    result: dict = {}
    try:
        text = path.read_text(encoding="utf-8")
        # 값 없이 키만 있는 라인 (name = "...") 패턴으로 대략적 추출
        result["_raw"] = re.findall(r'^\s*(\w[\w.-]*)\s*[=\[]', text, re.MULTILINE)
    except OSError:
        pass
    return result


def _parse_dependencies(repo_path: Path) -> dict:
    """의존성 파일에서 패키지 목록을 추출한다.

    지원 형식: package.json, pyproject.toml, requirements.txt, pom.xml, go.mod, Cargo.toml
    반환: {"package.json": ["react", "axios", ...], ...}
    """
    deps: dict = {}
    _MAX_PKGS = 20  # 각 파일에서 최대 20개만

    # package.json (Node.js / Bun / Deno)
    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            pkgs: list[str] = []
            pkgs += list((data.get("dependencies") or {}).keys())
            pkgs += list((data.get("devDependencies") or {}).keys())
            # name/description 도 포함 (프로젝트 파악용)
            meta: dict = {}
            if data.get("name"):
                meta["name"] = data["name"]
            if data.get("description"):
                meta["description"] = data["description"]
            deps["package.json"] = pkgs[:_MAX_PKGS]
            if meta:
                deps["package.json.meta"] = meta
        except Exception:
            pass

    # pyproject.toml (Python — Poetry, Hatch, PDM, setuptools)
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        try:
            data = _parse_toml_safe(pyproject)
            pkgs = []
            # PEP 517 / setuptools
            pkgs += list(data.get("project", {}).get("dependencies", []))
            # Poetry
            pkgs += list(data.get("tool", {}).get("poetry", {}).get("dependencies", {}).keys())
            # _raw 폴백
            pkgs += data.get("_raw", [])
            # "python" 제거
            pkgs = [p for p in pkgs if p.lower() != "python"]
            deps["pyproject.toml"] = pkgs[:_MAX_PKGS]
        except Exception:
            pass

    # requirements.txt (Python — pip)
    req_txt = repo_path / "requirements.txt"
    if req_txt.exists():
        try:
            lines = req_txt.read_text(encoding="utf-8", errors="replace").splitlines()
            pkgs = []
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                # "requests>=2.0.0" → "requests"
                pkg_name = re.split(r"[>=<!;\s]", line)[0].strip()
                if pkg_name:
                    pkgs.append(pkg_name)
            deps["requirements.txt"] = pkgs[:_MAX_PKGS]
        except Exception:
            pass

    # pom.xml (Java — Maven)
    pom = repo_path / "pom.xml"
    if pom.exists():
        try:
            tree = ET.parse(pom)
            root = tree.getroot()
            ns = re.match(r'\{.*\}', root.tag)
            ns_prefix = ns.group(0) if ns else ""
            pkgs = []
            for dep in root.iter(f"{ns_prefix}dependency"):
                artifact = dep.find(f"{ns_prefix}artifactId")
                if artifact is not None and artifact.text:
                    pkgs.append(artifact.text)
            deps["pom.xml"] = pkgs[:_MAX_PKGS]
        except Exception:
            pass

    # go.mod (Go)
    go_mod = repo_path / "go.mod"
    if go_mod.exists():
        try:
            text = go_mod.read_text(encoding="utf-8", errors="replace")
            pkgs = []
            in_require = False
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("require ("):
                    in_require = True
                    continue
                if in_require:
                    if line == ")":
                        in_require = False
                        continue
                    parts = line.split()
                    if parts:
                        # 마지막 세그먼트만 (github.com/gin-gonic/gin → gin)
                        pkgs.append(parts[0].split("/")[-1])
                elif line.startswith("require "):
                    pkgs.append(line.split()[1].split("/")[-1])
            deps["go.mod"] = pkgs[:_MAX_PKGS]
        except Exception:
            pass

    # Cargo.toml (Rust)
    cargo = repo_path / "Cargo.toml"
    if cargo.exists():
        try:
            data = _parse_toml_safe(cargo)
            pkgs = list(data.get("dependencies", {}).keys())
            pkgs += list(data.get("dev-dependencies", {}).keys())
            # _raw 폴백
            if not pkgs:
                pkgs = data.get("_raw", [])
            deps["Cargo.toml"] = pkgs[:_MAX_PKGS]
        except Exception:
            pass

    return deps


def _find_and_read_key_files(repo_path: Path, languages: Counter) -> dict[str, str]:
    """entry point 파일을 자동 탐지해 내용을 읽는다.

    - 파일당 최대 2000자, 전체 합산 최대 6000자
    - 이진 파일(.pyc, .png 등) 제외
    - glob 패턴(**) 포함 경로는 첫 번째 결과만 사용
    """
    results: dict[str, str] = {}
    total_chars = 0

    # 언어 상위 순으로 entry point 재정렬 — 주 언어 관련 파일을 먼저 읽는다.
    top_lang = languages.most_common(1)[0][0] if languages else ""
    lang_priority = {
        "Python": ["main.py", "app.py", "server.py", "manage.py"],
        "JavaScript": ["index.js", "app.js", "server.js"],
        "TypeScript": ["index.ts", "app.ts", "src/index.ts"],
        "Java": ["src/main/java/**/Application.java", "src/main/java/**/Main.java"],
        "Go": ["main.go", "cmd/main.go"],
        "Rust": ["src/main.rs", "src/lib.rs"],
        "Kotlin": ["src/main/kotlin/**/Application.kt"],
    }
    priority_first = lang_priority.get(top_lang, [])
    rest = [p for p in _ENTRY_POINTS if p not in priority_first]
    ordered = priority_first + rest

    for pattern in ordered:
        if total_chars >= _TOTAL_MAX_CHARS:
            break

        # glob 패턴 여부에 따라 경로 탐색 방식 분기
        if "**" in pattern or (pattern.count("*") > 0):
            found = list(repo_path.glob(pattern))[:1]
            paths = found
        else:
            p = repo_path / pattern
            paths = [p] if p.exists() and p.is_file() else []

        for p in paths:
            if total_chars >= _TOTAL_MAX_CHARS:
                break
            # 이진 파일 제외
            if p.suffix.lower() in _BINARY_EXTENSIONS:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                truncated = text[:_FILE_MAX_CHARS]
                if len(text) > _FILE_MAX_CHARS:
                    truncated += "\n...[truncated]"
                rel = str(p.relative_to(repo_path))
                results[rel] = truncated
                total_chars += len(truncated)
            except OSError:
                continue

    return results


def analyze_project_structure(repo_path: Path, languages: Counter) -> dict:
    """README, 의존성, 주요 소스 파일을 읽어 project_context dict 를 반환한다.

    이 결과를 AIService.analyze_project_from_code() 에 넘기면
    AI 가 "어떤 프로젝트인지" 분석해 problem/solution/summary 를 생성한다.
    """
    logger.debug("프로젝트 구조 분석 시작: %s", repo_path)
    context = {
        "readme": _read_readme(repo_path),
        "dependencies": _parse_dependencies(repo_path),
        "key_files": _find_and_read_key_files(repo_path, languages),
        "languages": dict(languages.most_common(10)),
    }
    logger.debug(
        "구조 분석 완료 — readme=%d자, deps=%s, key_files=%s",
        len(context["readme"]),
        list(context["dependencies"].keys()),
        list(context["key_files"].keys()),
    )
    return context


# ---------------------------------------------------------------------------
# 커밋 수집
# ---------------------------------------------------------------------------

def _collect_author_commits(
    repo_path: Path, author_email: str
) -> tuple[list[CommitInfo], int]:
    try:
        total_out = _run_git(repo_path, ["rev-list", "--count", "HEAD"]).strip()
        total_commits = int(total_out) if total_out else 0
    except Exception:
        total_commits = 0

    fmt = "--pretty=format:@@COMMIT@@%H%x00%an%x00%ae%x00%ad%x00%s"
    out = _run_git(
        repo_path,
        ["log", f"--author={author_email}", "--date=short", "--numstat", fmt],
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
                    sha=parts[0], author_name=parts[1], author_email=parts[2],
                    date=parts[3], subject=parts[4],
                )
        else:
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


# ---------------------------------------------------------------------------
# 메인 스캔 함수
# ---------------------------------------------------------------------------

def scan_repo(
    repo_path: Path,
    author_email: str,
    analyze: bool = False,
) -> ScanResult:
    """git 저장소에서 본인 커밋/지표를 수집한다.

    Args:
        repo_path: git 저장소 루트 경로
        author_email: 본인 커밋 작성자 이메일
        analyze: True 이면 README/의존성/소스 파일까지 읽어 project_context 를 채운다.

    Returns:
        ScanResult — analyze=True 이면 project_context 포함.
    """
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
        Path(repo_url.rstrip("/").split("/")[-1]).stem if repo_url else repo_path.name
    )

    commits, total_commits = _collect_author_commits(repo_path, author_email)
    if not commits:
        raise DevfolioError(
            f"'{author_email}' 로 작성된 커밋을 찾을 수 없습니다.",
            hint="이메일이 올바른지 확인하거나, git log --author=... 로 직접 확인해보세요.",
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

    # 딥 분석: README / 의존성 / 소스 파일 읽기
    if analyze:
        result.project_context = analyze_project_structure(repo_path, result.languages)

    return result


# ---------------------------------------------------------------------------
# Project 모델 생성 헬퍼
# ---------------------------------------------------------------------------

def _to_yyyymm(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    m = re.match(r"^(\d{4})-(\d{2})", date_str)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def _group_commits_into_tasks(
    commits: list[CommitInfo], max_tasks: int = 6
) -> list[dict]:
    """커밋을 카테고리 + 연월로 묶어 Task 후보 dict 목록을 만든다."""
    buckets: dict[tuple[str, str], list[CommitInfo]] = defaultdict(list)
    for c in commits:
        cats = _categorize(c.subject) or ["feat"]
        month = _to_yyyymm(c.date) or "unknown"
        buckets[(cats[0], month)].append(c)

    ranked = sorted(
        buckets.items(),
        key=lambda kv: (
            sum(x.insertions + x.deletions for x in kv[1]),
            len(kv[1]),
        ),
        reverse=True,
    )[:max_tasks]

    cat_label = {
        "feat": "기능 개발", "fix": "버그 수정 및 안정화",
        "perf": "성능 최적화", "refactor": "리팩터링",
        "test": "테스트 보강", "security": "보안 강화",
    }
    tasks: list[dict] = []
    for (category, month), bucket in ranked:
        months = sorted({_to_yyyymm(c.date) for c in bucket if _to_yyyymm(c.date)})
        ins = sum(c.insertions for c in bucket)
        dels = sum(c.deletions for c in bucket)
        files_n = sum(c.files_changed for c in bucket)
        top_subjects = [c.subject for c in bucket[:3]]
        tasks.append({
            "name": f"{cat_label.get(category, category)} ({month})",
            "period_start": months[0] if months else None,
            "period_end": months[-1] if months else None,
            "problem": "",
            "solution": "\n".join(f"- {s}" for s in top_subjects),
            "result": f"커밋 {len(bucket)}건 / +{ins} -{dels} LOC / {files_n}개 파일 변경",
            "keywords": [category],
        })
    return tasks


def _merge_ai_tasks(
    git_tasks: list[dict],
    ai_tasks: list[dict],
) -> list[dict]:
    """git 통계 기반 tasks 에 AI 분석 tasks 의 problem/solution/tech_used 를 주입한다.

    AI tasks 가 더 많으면 AI 것을 우선 사용하고,
    git tasks 가 더 많으면 남은 것은 원본 유지.
    매칭은 인덱스 순서 기반.
    """
    merged: list[dict] = []
    for i, git_task in enumerate(git_tasks):
        if i < len(ai_tasks):
            ai_task = ai_tasks[i]
            merged.append({
                **git_task,
                # AI 가 생성한 필드를 우선 적용 (빈 값이면 기존 유지)
                "name": ai_task.get("name") or git_task["name"],
                "problem": ai_task.get("problem") or git_task["problem"],
                "solution": ai_task.get("solution") or git_task["solution"],
                "tech_used": ai_task.get("tech_used") or [],
            })
        else:
            merged.append(git_task)
    # AI tasks 가 git tasks 보다 많으면 나머지 추가
    for i in range(len(git_tasks), len(ai_tasks)):
        ai_t = ai_tasks[i]
        merged.append({
            "name": ai_t.get("name", f"작업 {i+1}"),
            "period_start": None,
            "period_end": None,
            "problem": ai_t.get("problem", ""),
            "solution": ai_t.get("solution", ""),
            "result": "",
            "keywords": [],
            "tech_used": ai_t.get("tech_used", []),
        })
    return merged


def build_project_payload(
    scan: ScanResult,
    ai_analysis: Optional[dict] = None,
) -> dict:
    """ScanResult (+ AI 분석 결과) 를 Project 생성에 필요한 dict 로 변환한다.

    ai_analysis 가 있으면:
      - summary: AI 생성 요약 우선
      - tech_stack: AI 감지 + git 통계 언어 합산 (AI 우선, 최대 10개)
      - tasks: problem/solution/tech_used 에 AI 결과 주입
    """
    period_start = _to_yyyymm(scan.first_date)
    period_end = _to_yyyymm(scan.last_date)
    top_langs = [lang for lang, _ in scan.languages.most_common(6)]

    # 기본 summary (통계 기반)
    summary_lines = [
        f"{scan.repo_name} — 본인 커밋 {len(scan.commits)}건"
        f" ({scan.authorship_ratio*100:.0f}% 기여)",
        f"+{scan.total_insertions} / -{scan.total_deletions} LOC,"
        f" {len(scan.files_touched)} 파일 변경",
    ]
    if scan.category_counts:
        cats = ", ".join(f"{k}:{v}" for k, v in scan.category_counts.most_common())
        summary_lines.append(f"커밋 분류: {cats}")
    summary = " · ".join(summary_lines)

    git_tasks = _group_commits_into_tasks(scan.commits)

    # AI 분석 결과 반영
    if ai_analysis:
        ai_tech = ai_analysis.get("tech_stack") or []
        # dict.fromkeys 로 중복 제거하면서 AI 기술 스택 우선 순서 유지
        merged_tech = list(dict.fromkeys(ai_tech + top_langs))[:10]

        ai_summary = ai_analysis.get("summary") or ""
        final_summary = ai_summary if ai_summary else summary

        ai_tasks = ai_analysis.get("tasks") or []
        final_tasks = _merge_ai_tasks(git_tasks, ai_tasks) if ai_tasks else git_tasks

        # 전체 프로젝트 problem 이 있고 첫 task 에 problem 이 없으면 주입
        project_problem = ai_analysis.get("problem") or ""
        if final_tasks and project_problem and not final_tasks[0].get("problem"):
            final_tasks[0]["problem"] = project_problem
    else:
        merged_tech = top_langs
        final_summary = summary
        final_tasks = git_tasks

    return {
        "name": scan.repo_name,
        "type": "side",
        "status": "in_progress" if scan.last_date else "done",
        "organization": "",
        "period_start": period_start or "",
        "period_end": period_end,
        "role": "개발자",
        "team_size": 1,
        "tech_stack": merged_tech,
        "summary": final_summary,
        "tags": list(scan.category_counts.keys()),
        "tasks": final_tasks,
        "repo_url": scan.repo_url,
        "last_commit_sha": scan.head_sha,
        "scan_metrics": {
            **scan.to_dict(),
            "ai_analysis": ai_analysis or {},
        },
    }
