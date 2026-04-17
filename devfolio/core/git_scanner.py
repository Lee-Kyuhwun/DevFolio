"""Git 저장소 스캐너 — 본인 커밋 탐지, 지표 산출, 프로젝트 자동 생성.

[Spring 비교]
  외부 프로세스(git)를 실행해 데이터를 수집하고 가공하는 배치 서비스.
  Spring 에서는 ProcessBuilder + @Scheduled 를 사용하는 것과 유사하다.

  주요 흐름:
    scan_repo() → 커밋 수집(_collect_author_commits) + 파일/언어 분석(_collect_file_stats)
                → ScanResult (데이터 컨테이너)
    build_project_payload() → ScanResult → Project 생성 dict
"""

from __future__ import annotations

import re

# subprocess : 외부 프로세스를 실행하고 stdout/stderr 를 읽는 표준 라이브러리.
# [Spring] ProcessBuilder + Process.waitFor() 와 동일.
import subprocess

# Counter : 요소 개수를 자동으로 세는 dict 서브클래스. Counter("aab") → {'a':2, 'b':1}.
#   [Spring] Map<String, Integer> + computeIfAbsent(k, v->0) + map.merge(k, 1, Integer::sum).
# defaultdict : 키가 없을 때 자동으로 기본값을 만들어주는 dict.
#   defaultdict(list) → 키가 없으면 빈 리스트를 자동 생성.
#   [Spring] map.computeIfAbsent(key, k -> new ArrayList<>()) 와 동일.
from collections import Counter, defaultdict

# dataclass : __init__, __repr__, __eq__ 를 자동 생성해주는 데코레이터.
# [Spring] Lombok @Data (단, 상속, 검증 없는 순수 데이터 컨테이너용).
# field : dataclass 필드에 메타데이터를 붙이는 함수.
#   default_factory=list : 각 인스턴스마다 새 리스트를 생성.
#   [Spring] 필드에 = new ArrayList<>() 로 초기화하는 것과 동일.
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from devfolio.exceptions import DevfolioError
from devfolio.log import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 분류 키워드 / 언어 매핑
# ---------------------------------------------------------------------------

# dict literal : Java Map.of(...) 와 동일. 커밋 메시지를 카테고리로 분류할 키워드 목록.
IMPROVE_KEYWORDS = {
    "perf": ["perf", "performance", "optimize", "optimization", "speed", "faster",
             "성능", "최적화", "속도", "개선"],
    "fix": ["fix", "bug", "hotfix", "patch", "resolve", "버그", "수정", "장애"],
    "refactor": ["refactor", "cleanup", "restructure", "리팩터", "리팩토링", "정리"],
    "feat": ["feat", "feature", "add", "implement", "introduce", "기능", "구현", "추가"],
    "test": ["test", "coverage", "테스트"],
    "security": ["security", "secure", "auth", "vuln", "보안", "취약"],
}

# 확장자 → 언어 이름 매핑. [Spring] Map<String, String> 상수.
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
# 데이터 컨테이너 (dataclass)
# ---------------------------------------------------------------------------

# @dataclass : __init__, __repr__, __eq__ 를 자동 생성.
# [Spring] Lombok @Data — @Getter + @Setter + @ToString + @EqualsAndHashCode.
# 단, @dataclass 는 검증(validation)은 포함하지 않는다 (Pydantic BaseModel 과 다름).
@dataclass
class CommitInfo:
    """커밋 한 건의 정보.

    [Spring 비교]
      DB Entity 없이 메모리에서만 사용하는 VO(Value Object).
      git log 출력 한 줄을 파싱해 담는다.
    """
    sha: str           # 커밋 해시 40자리
    author_name: str
    author_email: str
    date: str          # YYYY-MM-DD 형식
    subject: str       # 커밋 메시지 첫 줄

    # int = 0 : 기본값. @dataclass 에서 기본값이 있는 필드는 뒤에 와야 한다.
    # [Spring] 기본값 있는 생성자 매개변수와 동일.
    insertions: int = 0
    deletions: int = 0
    files_changed: int = 0


@dataclass
class ScanResult:
    """저장소 스캔 결과 전체를 담는 컨테이너.

    [Spring 비교]
      @Service 메서드의 반환 DTO. 여러 데이터를 한 번에 묶어 반환.
    """
    repo_path: Path
    repo_url: str
    repo_name: str
    head_sha: str
    author_email: str

    # field(default_factory=list) : 인스턴스마다 새 빈 리스트 생성.
    # default=[] 로 쓰면 모든 인스턴스가 같은 리스트를 공유하는 버그 발생 (Python 함정).
    # [Spring] 필드 초기화 시 = new ArrayList<>() 를 쓰는 것과 동일한 이유.
    commits: list[CommitInfo] = field(default_factory=list)
    total_insertions: int = 0
    total_deletions: int = 0

    # set[str] : 중복 없는 파일 경로 집합. [Spring] Set<String>.
    files_touched: set[str] = field(default_factory=set)

    # Counter : dict 서브클래스, 언어별 파일 수를 자동 집계.
    languages: Counter = field(default_factory=Counter)
    category_counts: Counter = field(default_factory=Counter)

    # Optional[str] = None : 없으면 None.
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    total_commits_repo: int = 0

    # @property : getter 메서드를 속성처럼 접근하게 해주는 데코레이터.
    #   result.authorship_ratio 처럼 ()없이 접근.
    #   [Spring] Lombok @Getter — getAuthorshipRatio() 를 authorship_ratio 로 읽는 것과 유사.
    @property
    def authorship_ratio(self) -> float:
        """본인 커밋 비율 (0.0 ~ 1.0)."""
        if self.total_commits_repo == 0:
            return 0.0
        # len(list) : 리스트 원소 수. [Spring] list.size().
        return len(self.commits) / self.total_commits_repo

    def to_dict(self) -> dict:
        """스캔 지표를 dict 로 직렬화한다. scan_metrics 캐시에 저장된다.

        [Spring 비교]
          Jackson @JsonSerialize 또는 ObjectMapper.convertValue(this, Map.class).
        """
        return {
            "repo_url": self.repo_url,
            "repo_name": self.repo_name,
            "head_sha": self.head_sha,
            "author_email": self.author_email,
            "commit_count": len(self.commits),
            "total_commits_repo": self.total_commits_repo,
            # round(value, digits) : 반올림. [Spring] Math.round() 와 동일.
            "authorship_ratio": round(self.authorship_ratio, 3),
            "insertions": self.total_insertions,
            "deletions": self.total_deletions,
            "files_touched": len(self.files_touched),
            # Counter.most_common(n) : 빈도 높은 순으로 n개를 (값, 횟수) 튜플 리스트로 반환.
            # dict(...) 으로 감싸 일반 dict 로 변환.
            "languages": dict(self.languages.most_common(10)),
            "categories": dict(self.category_counts),
            "first_date": self.first_date,
            "last_date": self.last_date,
        }


# ---------------------------------------------------------------------------
# Git 명령 실행 헬퍼
# ---------------------------------------------------------------------------

def _run_git(repo_path: Path, args: list[str]) -> str:
    """git 명령을 실행하고 stdout 을 문자열로 반환한다.

    [Spring 비교]
      ProcessBuilder.command("git", "-C", repoPath, ...args).start() +
      process.inputStream 읽기 + waitFor() 와 동일.
    """
    try:
        # subprocess.run(cmd_list, ...) : 외부 명령 실행.
        #   capture_output=True : stdout/stderr 를 캡처 (콘솔 출력 안 됨).
        #   text=True : stdout/stderr 를 bytes 대신 str 로 반환.
        #   check=True : 비정상 종료(returncode != 0) 시 CalledProcessError 발생.
        # [Spring] ProcessBuilder.inheritIO() 대신 redirectOutput(PIPE) 사용하는 것과 유사.
        result = subprocess.run(
            ["git", "-C", str(repo_path)] + args,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except FileNotFoundError as e:
        # git 실행 파일을 찾지 못할 때 발생.
        raise DevfolioError(
            "git 명령을 찾을 수 없습니다.",
            hint="git을 설치한 후 다시 시도하세요.",
        ) from e
    except subprocess.CalledProcessError as e:
        # git 명령이 비정상 종료(exit code != 0) 됐을 때.
        # e.stderr : stderr 출력 내용.
        raise DevfolioError(
            f"git 명령 실패: git {' '.join(args)}",
            hint=(e.stderr or "").strip()[:200],
        ) from e


def _is_git_repo(path: Path) -> bool:
    """.git 디렉터리가 있으면 git 저장소로 간주한다."""
    # (path / ".git").exists() : 해당 경로에 .git 이 있는지 확인.
    if not (path / ".git").exists():
        return False
    return True


def _detect_repo_url(repo_path: Path) -> str:
    """remote.origin.url 설정값을 읽어 반환한다. 없으면 빈 문자열."""
    try:
        out = _run_git(repo_path, ["config", "--get", "remote.origin.url"]).strip()
        return out
    except Exception:
        return ""


def _categorize(subject: str) -> list[str]:
    """커밋 메시지(subject)를 분석해 카테고리 목록을 반환한다.

    예: "feat: add login" → ["feat"]
    예: "fix: bug and refactor" → ["fix", "refactor"]
    """
    # str.lower() : 소문자 변환. [Spring] subject.toLowerCase().
    lowered = subject.lower()
    hits: list[str] = []
    # dict.items() : (key, value) 쌍을 순회. [Spring] Map.entrySet() 순회.
    for category, keywords in IMPROVE_KEYWORDS.items():
        # any(kw in lowered for kw in keywords) : keywords 중 하나라도 포함되면 True.
        # [Spring] keywords.stream().anyMatch(kw -> lowered.contains(kw)).
        if any(kw in lowered for kw in keywords):
            hits.append(category)
    return hits


# ---------------------------------------------------------------------------
# 커밋 수집
# ---------------------------------------------------------------------------

def _collect_author_commits(
    repo_path: Path, author_email: str
) -> tuple[list[CommitInfo], int]:
    """저장소 전체에서 author_email 과 일치하는 커밋을 수집한다.

    반환값: (본인 커밋 목록, 저장소 전체 커밋 수)
    tuple[A, B] : 두 값을 하나로 묶어 반환. [Spring] Pair<List<CommitInfo>, Integer>.
    """
    # 전체 커밋 수 — 기여율(authorship_ratio) 계산에 사용.
    try:
        total_out = _run_git(repo_path, ["rev-list", "--count", "HEAD"]).strip()
        # int("123") : 문자열을 정수로 변환. [Spring] Integer.parseInt("123").
        total_commits = int(total_out) if total_out else 0
    except Exception:
        total_commits = 0

    # git log --author=EMAIL --numstat --pretty=format:...
    #   --numstat : 각 커밋에서 변경된 파일의 삽입/삭제 라인 수 출력.
    #   --pretty=format: : 커밋 정보를 커스텀 포맷으로 출력.
    #   %H=커밋해시, %an=작성자이름, %ae=이메일, %ad=날짜, %s=제목.
    #   \x00 : null 바이트를 구분자로 사용 (제목에 공백이 있어도 안전).
    fmt = "--pretty=format:@@COMMIT@@%H%x00%an%x00%ae%x00%ad%x00%s"
    out = _run_git(
        repo_path,
        [
            "log",
            f"--author={author_email}",
            "--date=short",    # 날짜를 YYYY-MM-DD 형식으로 출력.
            "--numstat",
            fmt,
        ],
    )

    commits: list[CommitInfo] = []
    # Optional[CommitInfo] = None : 현재 파싱 중인 커밋. 없으면 None.
    current: Optional[CommitInfo] = None
    # out.split("\n") : 줄 단위로 분할. [Spring] out.split("\\n") (Java 에서는 \\ 필요).
    for line in out.split("\n"):
        if not line:
            # 빈 줄 = 커밋 블록 구분자. current 가 있으면 수집 완료.
            if current is not None:
                commits.append(current)
                current = None
            continue
        if line.startswith("@@COMMIT@@"):
            if current is not None:
                commits.append(current)
            # line[len("@@COMMIT@@"):] : "@@COMMIT@@" 이후 문자열 추출 (슬라이싱).
            # .split("\x00") : null 바이트로 분할.
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
            # numstat 줄: "<삽입>\t<삭제>\t<파일경로>"
            if current is None:
                continue
            # re.match(pattern, line) : 패턴이 줄 처음부터 매칭되는지 확인.
            # \S+ = 공백 아닌 하나 이상, \t = 탭.
            m = re.match(r"^(\S+)\t(\S+)\t(.+)$", line)
            if not m:
                continue
            # m.groups() : 괄호로 묶인 캡처 그룹 값들을 튜플로 반환.
            # [Spring] Matcher.group(1), group(2), group(3).
            ins_s, del_s, _path = m.groups()
            try:
                # "-" 는 이진 파일(binary file)의 경우 출력되는 값 → 0 으로 처리.
                ins = int(ins_s) if ins_s != "-" else 0
                dele = int(del_s) if del_s != "-" else 0
            except ValueError:
                ins, dele = 0, 0
            # += : [Spring] current.setInsertions(current.getInsertions() + ins).
            current.insertions += ins
            current.deletions += dele
            current.files_changed += 1

    # 마지막 커밋 블록 처리 (빈 줄로 끝나지 않는 경우).
    if current is not None:
        commits.append(current)

    return commits, total_commits


def _collect_file_stats(
    repo_path: Path, commits: list[CommitInfo]
) -> tuple[set[str], Counter]:
    """본인 커밋들에서 변경된 파일과 언어를 집계한다.

    반환값: (변경된 파일 경로 집합, 언어별 카운터)
    """
    # set() : 중복 없는 컬렉션. [Spring] Set<String>.
    files: set[str] = set()
    # Counter() : 빈 카운터. 언어명 → 등장 횟수.
    langs: Counter = Counter()
    for commit in commits:
        try:
            # git show --name-only --pretty=format: SHA : 해당 커밋에서 변경된 파일명만 출력.
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
            # Path(path).suffix : 파일 확장자. [Spring] FilenameUtils.getExtension(path).
            # .lower() : 대소문자 통일 (".PY" → ".py").
            ext = Path(path).suffix.lower()
            if ext in LANG_BY_EXT:
                # Counter[key] += 1 : 해당 키의 카운트를 1 증가.
                # [Spring] langs.merge(lang, 1, Integer::sum).
                langs[LANG_BY_EXT[ext]] += 1
    return files, langs


# ---------------------------------------------------------------------------
# 메인 스캔 함수
# ---------------------------------------------------------------------------

def scan_repo(repo_path: Path, author_email: str) -> ScanResult:
    """주어진 git 저장소에서 author_email 로 본인 커밋/지표를 수집한다.

    [Spring 비교]
      @Service 메서드 — 여러 내부 함수를 조합해 하나의 결과 DTO 를 만드는 파사드.

    Args:
        repo_path: git 저장소 루트 경로
        author_email: 본인 커밋 작성자 이메일

    Returns:
        ScanResult: 커밋 목록, 지표, 언어 분포 등을 담은 결과 객체

    Raises:
        DevfolioError: git 저장소 아님, 이메일 없음, 커밋 없음 등
    """
    # Path.resolve() : 상대 경로를 절대 경로로 변환.
    # [Spring] path.toAbsolutePath().normalize() 와 동일.
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

    # HEAD 커밋 SHA 를 캐시 키로 사용 (이미 스캔한 버전인지 확인용).
    head_sha = _run_git(repo_path, ["rev-parse", "HEAD"]).strip()
    repo_url = _detect_repo_url(repo_path)

    # Path.rstrip("/").split("/")[-1] : URL 마지막 세그먼트 추출.
    # Path(...).stem : .git 확장자 제거.
    # 예: "https://github.com/user/my-project.git" → "my-project"
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

    # Counter() : 카테고리별 커밋 수 집계.
    category_counts: Counter = Counter()
    for c in commits:
        for cat in _categorize(c.subject):
            category_counts[cat] += 1

    # sorted(...) : 날짜 오름차순 정렬. [Spring] list.stream().sorted().collect(toList()).
    dates = sorted(c.date for c in commits if c.date)

    result = ScanResult(
        repo_path=repo_path,
        repo_url=repo_url,
        repo_name=repo_name,
        head_sha=head_sha,
        author_email=author_email,
        commits=commits,
        # sum(c.insertions for c in commits) : 전체 삽입 라인 합계.
        # [Spring] commits.stream().mapToInt(CommitInfo::getInsertions).sum().
        total_insertions=sum(c.insertions for c in commits),
        total_deletions=sum(c.deletions for c in commits),
        files_touched=files_touched,
        languages=languages,
        category_counts=category_counts,
        # dates[0] : 가장 오래된 날짜, dates[-1] : 가장 최근 날짜.
        # [Spring] dates.get(0), dates.get(dates.size()-1).
        first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
        total_commits_repo=total_commits,
    )
    return result


# ---------------------------------------------------------------------------
# Project 모델 생성 헬퍼
# ---------------------------------------------------------------------------

def _to_yyyymm(date_str: Optional[str]) -> Optional[str]:
    """YYYY-MM-DD 날짜 문자열에서 YYYY-MM 만 추출한다."""
    if not date_str:
        return None
    # re.match(r"^(\d{4})-(\d{2})", ...) : YYYY-MM 패턴 매칭.
    m = re.match(r"^(\d{4})-(\d{2})", date_str)
    # m.group(1), m.group(2) : 첫 번째, 두 번째 캡처 그룹.
    # [Spring] Matcher.group(1), Matcher.group(2).
    return f"{m.group(1)}-{m.group(2)}" if m else None


def _group_commits_into_tasks(
    commits: list[CommitInfo], max_tasks: int = 6
) -> list[dict]:
    """커밋을 카테고리 + 연월로 묶어 Task 후보 dict 목록을 만든다.

    [Spring 비교]
      stream().collect(Collectors.groupingBy(...)) — 그룹화 후 집계.
    """
    # defaultdict(list) : 키가 없으면 빈 리스트를 자동 생성.
    # key = (category, month) tuple : [Spring] Pair<String, String> 으로 그룹화.
    buckets: dict[tuple[str, str], list[CommitInfo]] = defaultdict(list)
    for c in commits:
        # _categorize 결과가 없으면 기본값 "feat" 사용.
        cats = _categorize(c.subject) or ["feat"]
        month = _to_yyyymm(c.date) or "unknown"
        # 주 카테고리(첫 번째)만 사용해 그룹 키를 만든다.
        buckets[(cats[0], month)].append(c)

    # buckets.items() : dict 의 (키, 값) 쌍을 순회.
    # sorted(..., key=lambda kv: (...), reverse=True) : 변경량 큰 순으로 정렬.
    # [Spring] .stream().sorted(Comparator.comparingInt(...).reversed()).
    ranked = sorted(
        buckets.items(),
        key=lambda kv: (
            # 각 버킷의 총 변경 라인 수 (삽입+삭제) + 커밋 수 순으로 정렬.
            sum(x.insertions + x.deletions for x in kv[1]),
            len(kv[1]),
        ),
        reverse=True,
    )[:max_tasks]  # 상위 max_tasks 개만 유지.

    tasks: list[dict] = []
    # 카테고리 코드 → 한국어 레이블.
    cat_label = {
        "feat": "기능 개발",
        "fix": "버그 수정 및 안정화",
        "perf": "성능 최적화",
        "refactor": "리팩터링",
        "test": "테스트 보강",
        "security": "보안 강화",
    }
    for (category, month), bucket in ranked:
        # set comprehension : 버킷 내 커밋의 연월 집합.
        months = sorted({_to_yyyymm(c.date) for c in bucket if _to_yyyymm(c.date)})
        ins = sum(c.insertions for c in bucket)
        dels = sum(c.deletions for c in bucket)
        files_n = sum(c.files_changed for c in bucket)
        name = f"{cat_label.get(category, category)} ({month})"
        # 대표 커밋 제목 3개 — bucket 은 list 이므로 [:3] 으로 앞 3개 슬라이싱.
        top_subjects = [c.subject for c in bucket[:3]]
        problem = ""
        # "\n".join(iterable) : 요소를 줄바꿈으로 이음. [Spring] String.join("\n", list).
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
    """ScanResult 를 Project 생성에 필요한 dict 로 변환한다.

    [Spring 비교]
      @Mapper / ModelMapper — VO(ScanResult) → DTO(create dict) 변환.
      이 dict 는 ProjectManager.create_project() 또는 scan_git API 에서 사용된다.
    """
    period_start = _to_yyyymm(scan.first_date)
    period_end = _to_yyyymm(scan.last_date)

    # most_common(6) : 상위 6개 언어만 추출. [Spring] stream().limit(6).collect(toList()).
    top_langs = [lang for lang, _ in scan.languages.most_common(6)]

    summary_lines = [
        f"{scan.repo_name} — 본인 커밋 {len(scan.commits)}건"
        f" ({scan.authorship_ratio*100:.0f}% 기여)",
        # :.0f : 소수점 없이 반올림해서 포맷. [Spring] String.format("%.0f%%", ratio*100).
        f"+{scan.total_insertions} / -{scan.total_deletions} LOC,"
        f" {len(scan.files_touched)} 파일 변경",
    ]
    if scan.category_counts:
        # category_counts.most_common() : 모든 항목을 빈도 높은 순으로 반환.
        cats = ", ".join(
            f"{k}:{v}" for k, v in scan.category_counts.most_common()
        )
        summary_lines.append(f"커밋 분류: {cats}")
    # " · ".join(list) : " · " 구분자로 이음.
    summary = " · ".join(summary_lines)

    tasks = _group_commits_into_tasks(scan.commits)

    return {
        "name": scan.repo_name,
        "type": "side",
        # 마지막 커밋이 있으면 in_progress, 없으면 done.
        "status": "in_progress" if scan.last_date else "done",
        "organization": "",
        "period_start": period_start or "",
        "period_end": period_end,
        "role": "개발자",
        "team_size": 1,
        "tech_stack": top_langs,
        "summary": summary,
        # dict.keys() : 카테고리 이름 목록을 태그로 사용.
        "tags": list(scan.category_counts.keys()),
        "tasks": tasks,
        # 캐시용 필드: 다음 스캔 시 HEAD SHA 비교로 재분석 여부 판단.
        "repo_url": scan.repo_url,
        "last_commit_sha": scan.head_sha,
        "scan_metrics": scan.to_dict(),
    }
