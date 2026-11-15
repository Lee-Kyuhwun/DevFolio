"""결정론적 프로젝트 분석 엔진.

파이프라인:
  1) 문서 탐색·추출·역할 분류
  2) 코드 인벤토리(심볼·라우트·의존성)
  3) Git 이력·변경 전후 패치 수집
  4) 문서 주장 ↔ 구현 교차 분석
  5) 기능별 진화 타임라인 재구성
  6) 측정 수치 추출·계산
  7) 근거가 연결된 성과 후보 생성(리버트 제외, 개인 기여 분리)
  8) 선택적 AI 보강(동의 시) — AI 는 VERIFIED 를 만들 수 없다.

Git 커밋 메시지는 유형 분류의 단서로만 쓰고, 후보는 실제 diff·코드·문서 근거로 만든다.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Optional

from impactnote.core.intel.discovery import (
    discover_documents,
    doc_fingerprint,
    iter_code_files,
    read_code,
)
from impactnote.core.intel.gitintel import GitRepo
from impactnote.core.intel.models import (
    AIStageInfo,
    Candidate,
    CodeFile,
    DocRecord,
    EvidenceRef,
    Finding,
    GitCommit,
    Measurement,
    ProjectAnalysis,
    TimelineStep,
)
from impactnote.core.store import JsonStore, get_store

LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".h": "C/C++",
    ".cpp": "C++",
    ".cc": "C++",
    ".swift": "Swift",
    ".scala": "Scala",
    ".dart": "Dart",
    ".sql": "SQL",
    ".sh": "Shell",
    ".tf": "Terraform",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
}

_CANDIDATE_WEIGHT = {
    "stability": 5,
    "security": 5,
    "performance": 4,
    "memory": 4,
    "concurrency": 4,
    "error_handling": 3,
    "data": 3,
    "delivery": 3,
    "maintainability": 2,
    "observability": 2,
    "feature": 2,
}


def _is_primary_code_path(path: str) -> bool:
    """성과 후보의 주 근거는 동작 코드여야 한다.

    CI 설정·문서·테스트·개발 스크립트는 근거로는 유용하지만
    그 자체를 성과 후보로 만들면 "파일을 고쳤다"는 수준에 머문다.
    """
    lower = path.lower()
    name = Path(path).name.lower()
    if lower.startswith((".github/", "docs/", "documentation/", "scripts/")):
        return False
    if "/tests/" in lower or lower.startswith("tests/") or "test" in name:
        return False
    if name in {"dockerfile", "makefile", "docker-compose.yml", "docker-compose.yaml"}:
        return True
    return Path(path).suffix.lower() in {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".kt",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".cs",
        ".c",
        ".cpp",
        ".sql",
        ".tf",
    }


CATEGORY_LABELS = {
    "stability": "안정성·장애 대응",
    "performance": "성능·자원 효율",
    "memory": "메모리·대용량 처리",
    "concurrency": "동시성·비동기",
    "error_handling": "예외 처리",
    "security": "보안",
    "testing": "테스트·검증",
    "maintainability": "구조·유지보수성",
    "observability": "관측성",
    "delivery": "배포·자동화",
    "data": "데이터 처리",
    "docs": "문서화",
    "feature": "기능 구현",
}

_CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "stability": (
        "retry",
        "backoff",
        "fallback",
        "circuit",
        "rollback",
        "timeout",
        "health",
    ),
    "performance": ("cache", "lru_cache", "memo", "batch", "index", "fast", "optimiz"),
    "memory": ("yield", "stream", "chunk", "iterator", "generator", "readline"),
    "concurrency": (
        "async ",
        "await ",
        "thread",
        "executor",
        "asyncio",
        "lock",
        "semaphore",
    ),
    "error_handling": ("try:", "except ", "raise ", "finally:", "error"),
    "security": (
        "sanitize",
        "escape",
        "validate",
        "csrf",
        "token",
        "permission",
        "auth",
    ),
    "testing": ("test_", "pytest", "assert ", "mock", "fixture"),
    "maintainability": (
        "refactor",
        "rename",
        "extract",
        "typing",
        "dataclass",
        "protocol",
    ),
    "observability": ("log", "logger", "metric", "trace", "telemetry"),
    "delivery": ("docker", "deploy", "workflow", "ci", "makefile", "release"),
    "data": ("select ", "insert ", "update ", "json", "csv", "schema", "migration"),
    "docs": (".md", "readme", "docs/"),
}

_CLAIM_MARKERS = (
    "추가",
    "개선",
    "도입",
    "지원",
    "자동",
    "검증",
    "차단",
    "전환",
    "리팩터",
    "최적화",
    "구현",
    "제거",
    "방지",
    "보장",
    "구축",
    "강화",
    "introduc",
    "implement",
    "improv",
    "add ",
    "support",
    "reduce",
    "optimi",
    "prevent",
)

_STOPWORDS = {
    "그리고",
    "그러나",
    "또는",
    "위해",
    "대한",
    "통해",
    "있는",
    "없는",
    "한다",
    "했다",
    "합니다",
    "있습니다",
    "때문에",
    "경우",
    "기능",
    "사용",
    "처리",
    "시스템",
    "프로젝트",
    "서비스",
    "코드",
    "문서",
    "변경",
    "개선",
    "추가",
    "구현",
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "using",
    "when",
}

_MEASURE_UNITS = r"ms|초|s|MB|GB|건|회|%|분|시간|개"
_MEASUREMENT_MARKERS = (
    "측정",
    "측정 결과",
    "테스트 결과",
    "실행 결과",
    "벤치마크",
    "benchmark",
    "부하 테스트",
    "평균",
    "p95",
    "latency",
    "throughput",
)
_GOAL_MARKERS = ("목표", "예정", "계획", "기대", "예상", "target", "목표치")
_GENERIC_PATH_TOKENS = {
    "api",
    "app",
    "core",
    "config",
    "index",
    "lib",
    "main",
    "model",
    "models",
    "route",
    "routes",
    "service",
    "services",
    "src",
    "static",
    "test",
    "tests",
    "util",
    "utils",
    "web",
}
_MEASURE_PATTERN = re.compile(
    rf"(?P<before>\d+(?:\.\d+)?)\s*(?P<bunit>{_MEASURE_UNITS})\s*"
    rf"(?:→|->|에서|to|,)\s*(?P<after>\d+(?:\.\d+)?)\s*(?P<aunit>{_MEASURE_UNITS})",
    re.IGNORECASE,
)


def _language(path: Path) -> str:
    return LANGUAGES.get(path.suffix.lower(), path.suffix.lstrip(".").upper())


def _python_symbols(text: str) -> tuple[list[str], list[str], list[str]]:
    functions: list[str] = []
    symbols: list[str] = []
    routes: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            symbols.append(node.name)
            for decorator in node.decorator_list:
                source = ast.unparse(decorator) if hasattr(ast, "unparse") else ""
                if any(
                    token in source
                    for token in (".get(", ".post(", ".put(", ".patch(", ".delete(")
                ):
                    routes.append(f"{node.name}:{source[:120]}")
        elif isinstance(node, ast.ClassDef):
            symbols.append(node.name)
    return symbols[:80], functions[:60], routes[:30]


def _regex_symbols(text: str) -> tuple[list[str], list[str], list[str]]:
    classes = re.findall(
        r"\b(?:class|interface|struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", text
    )
    functions = re.findall(
        r"\b(?:def|function|func|fn)\s+([A-Za-z_][A-Za-z0-9_]*)|"
        r"\b(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(",
        text,
    )
    names = classes + [item for pair in functions for item in pair if item]
    routes = re.findall(
        r"(?:app|router|@app|@router)\.(?:get|post|put|patch|delete)\(\s*[\"']([^\"']+)",
        text,
    )
    return (
        names[:80],
        [item for pair in functions for item in pair if item][:60],
        routes[:30],
    )


def _imports(text: str) -> list[str]:
    names = re.findall(r"^\s*(?:from|import)\s+([A-Za-z0-9_.]+)", text, re.M)
    names += re.findall(r"require\([\"']([^\"']+)[\"']\)", text)
    return list(dict.fromkeys(names))[:40]


def _pattern_present(text: str, pattern: str) -> bool:
    """짧은 영문 패턴은 단어 경계로 매칭한다.

    `ci` 를 단순 substring 으로 찾으면 `asyncio` 가 배포 카테고리로 잘못 분류되고,
    `fast` 가 `breakfast` 에 걸리는 식의 오탐이 생긴다. 한국어·기호 패턴은 그대로 둔다.
    """
    if pattern.isascii() and pattern.isalnum() and len(pattern) <= 5:
        return (
            re.search(rf"(?<![a-z0-9]){re.escape(pattern)}(?![a-z0-9])", text)
            is not None
        )
    return pattern in text


def _categories(text: str) -> list[str]:
    lowered = (text or "").lower()
    found = []
    for category, patterns in _CATEGORY_PATTERNS.items():
        if any(_pattern_present(lowered, pattern) for pattern in patterns):
            found.append(category)
    return found


def _inventory(
    root: Path, commits: list[GitCommit], warnings: list[str]
) -> list[CodeFile]:
    changes: dict[str, int] = {}
    for commit in commits:
        for path in commit.files:
            changes[path] = changes.get(path, 0) + 1
    files: list[CodeFile] = []
    for path in sorted(iter_code_files(root)):
        text = read_code(path)
        if not text:
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() == ".py":
            symbols, functions, routes = _python_symbols(text)
        elif path.suffix.lower() in {
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".vue",
            ".java",
            ".kt",
            ".go",
            ".rs",
            ".rb",
            ".php",
            ".cs",
            ".c",
            ".cpp",
        }:
            symbols, functions, routes = _regex_symbols(text)
        else:
            symbols, functions, routes = [], [], []
        files.append(
            CodeFile(
                path=relative,
                language=_language(path),
                lines=len(text.splitlines()),
                symbols=symbols,
                functions=functions,
                routes=routes,
                imports=_imports(text),
                change_count=changes.get(relative, 0),
                categories=_categories(relative + "\n" + text[:8000]),
                excerpt=text[:1200],
            )
        )
        if len(files) >= 500:
            warnings.append("코드 파일이 많아 500개까지만 인덱싱했습니다.")
            break
    return files


def _diff_categories(patch: str) -> list[str]:
    """추가된 코드 줄에서 변경의 기술적 성격을 점수화한다.

    diff 헤더나 파일 이름만으로 분류하지 않고, 실제로 더해진 동작 코드를 본다.
    """
    scores: dict[str, int] = {}
    for line in (patch or "").splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        lowered = line[1:].lower()
        for category, patterns in _CATEGORY_PATTERNS.items():
            if category in {"docs", "testing"}:
                continue
            for pattern in patterns:
                if _pattern_present(lowered, pattern):
                    weight = (
                        2
                        if pattern
                        in {
                            "retry",
                            "fallback",
                            "circuit",
                            "rollback",
                            "yield",
                            "cache",
                            "lru_cache",
                        }
                        else 1
                    )
                    scores[category] = scores.get(category, 0) + weight
    return [
        category
        for category, _ in sorted(
            scores.items(), key=lambda item: item[1], reverse=True
        )
    ][:3]


def _commit_categories(repo: GitRepo, commits: list[GitCommit]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for commit in commits:
        if commit.is_revert or commit.is_merge:
            continue
        patches = []
        for path in commit.files[:4]:
            if Path(path).suffix.lower() in {".md", ".txt", ".rst"}:
                continue
            patch = repo.patch(commit.sha, path)
            if patch:
                patches.append(patch)
        combined = "\n".join(patches)[:12000]
        categories = _diff_categories(combined)
        if not categories and commit.subject:
            lowered = commit.subject.lower()
            if any(token in lowered for token in ("fix", "bug", "장애", "hotfix")):
                categories = ["stability"]
            elif any(token in lowered for token in ("perf", "성능", "최적화")):
                categories = ["performance"]
            elif any(token in lowered for token in ("test", "테스트")):
                categories = ["testing"]
            elif any(token in lowered for token in ("refactor", "리팩터")):
                categories = ["maintainability"]
            elif any(token in lowered for token in ("feat", "기능", "추가")):
                categories = ["feature"]
        mapping[commit.sha] = categories
    return mapping


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"```.*?```", " ", text, flags=re.S)
    cleaned = re.sub(r"^\s*#{1,6}\s+.*$", " ", cleaned, flags=re.M)
    parts = re.split(r"(?<=[.!?。])\s+|\n\n", cleaned)
    return [re.sub(r"\s+", " ", part).strip(" -*•\t") for part in parts if part.strip()]


def _tokens(text: str) -> list[str]:
    latin = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{3,}", text)
    korean = re.findall(r"[가-힣]{2,}", text)
    merged = [item.lower() for item in latin + korean]
    return [item for item in dict.fromkeys(merged) if item not in _STOPWORDS]


def _claims(documents: list[DocRecord]) -> list[dict]:
    claims: list[dict] = []
    seen: set[str] = set()
    for document in documents:
        if document.kind in {
            "requirements",
            "design",
            "technical_review",
            "implementation",
            "report",
            "performance",
            "incident",
        }:
            for sentence in _sentences(document.excerpt):
                if not 25 <= len(sentence) <= 420:
                    continue
                if sentence.startswith("|") or "---" in sentence:
                    continue
                lowered = sentence.lower()
                if not any(marker in lowered for marker in _CLAIM_MARKERS):
                    continue
                normalized = sentence[:120]
                if normalized in seen:
                    continue
                seen.add(normalized)
                tokens = _tokens(sentence)
                if len(tokens) < 2:
                    continue
                claims.append(
                    {
                        "text": sentence[:400],
                        "doc": document,
                        "tokens": tokens[:12],
                    }
                )
                if len(claims) >= 48:
                    return claims
    return claims


def _match_claims(
    claims: list[dict],
    files: list[CodeFile],
    documents: list[DocRecord],
    evidence_pool: list[EvidenceRef],
) -> tuple[list[Finding], list[dict]]:
    # 문서 요약 문장과 코드 주석이 같은 한국어를 공유할 수 있으므로,
    # 구현 일치는 "심볼·경로·라우트·의존성"에서 확인된 경우만 인정한다.
    corpus = " ".join(
        f"{item.path} {' '.join(item.symbols)} {' '.join(item.functions)} "
        f"{' '.join(item.routes)} {' '.join(item.imports)}"
        for item in files
    ).lower()
    name_corpus = " ".join(
        f"{' '.join(item.symbols)} {' '.join(item.functions)} {' '.join(item.routes)}"
        for item in files
    ).lower()
    test_corpus = " ".join(
        item.path + " " + " ".join(item.symbols) + " " + item.excerpt
        for item in files
        if "test" in item.path.lower()
    ).lower()
    doc_corpus = " ".join(item.excerpt for item in documents).lower()
    findings: list[Finding] = []
    implemented_claims: list[dict] = []
    for claim in claims:
        tokens = claim["tokens"]
        matches = [token for token in tokens if token in corpus]
        name_matches = [token for token in tokens if token in name_corpus]
        test_matches = [token for token in tokens if token in test_corpus]
        doc_matches = [token for token in tokens if token in doc_corpus]
        document = claim["doc"]
        evidence = EvidenceRef(
            kind="claim",
            title=f"문서 주장: {claim['text'][:80]}",
            path=document.path,
            locator="문서 본문",
            excerpt=claim["text"],
            verified=document.git_tracked and not document.deleted,
        )
        evidence_pool.append(evidence)
        # 함수·클래스·라우트 이름이 최소 1개, 코드 토큰이 최소 2개 일치해야 한다.
        # README 의 일반 명사("기간", "설정")만으로 구현을 인정하지 않는다.
        match_ratio = len(matches) / max(1, len(tokens))
        if len(matches) >= 2 and len(name_matches) >= 1 and match_ratio >= 0.4:
            quality = "VERIFIED" if len(test_matches) >= 1 else "SUPPORTED_INFERENCE"
            implemented_claims.append(
                {
                    "claim": claim,
                    "tokens": matches[:6],
                    "quality": quality,
                }
            )
            findings.append(
                Finding(
                    title=f"문서와 구현이 일치: {claim['text'][:70]}",
                    detail=(
                        f"문서({document.path})의 주장과 코드의 심볼/본문이 "
                        f"{', '.join(matches[:5])} 로 연결됩니다."
                        + (
                            " 테스트에서도 확인됩니다."
                            if test_matches
                            else " 테스트 근거는 아직 확인되지 않았습니다."
                        )
                    ),
                    kind="doc_code_match",
                    quality=quality,
                    paths=[document.path],
                    evidence_ids=[evidence.id],
                )
            )
            findings[-1].evidence_ids.append(evidence.id)
        elif len(doc_matches) >= 2 and len(matches) <= 1:
            findings.append(
                Finding(
                    title=f"문서에만 존재하는 기능: {claim['text'][:70]}",
                    detail="문서 주장은 확인되지만 현재 코드에서 구현 근거를 찾지 못했습니다. 성과로 확정하지 않습니다.",
                    kind="doc_only",
                    quality="HYPOTHESIS",
                    paths=[document.path],
                    evidence_ids=[evidence.id],
                )
            )
    return findings, implemented_claims


def _measurements(
    documents: list[DocRecord],
    warnings: list[str],
    evidence_pool: list[EvidenceRef],
) -> list[Measurement]:
    results: list[Measurement] = []
    for document in documents:
        text = document.excerpt
        for match in _MEASURE_PATTERN.finditer(text):
            before = float(match.group("before"))
            after = float(match.group("after"))
            bunit = match.group("bunit").lower()
            aunit = match.group("aunit").lower()
            if bunit != aunit:
                conversions = {
                    ("s", "ms"): (1000.0, 1.0),
                    ("초", "ms"): (1000.0, 1.0),
                    ("ms", "s"): (1.0, 1000.0),
                    ("MB", "GB"): (1.0, 1000.0),
                }
                factor = conversions.get((bunit, aunit))
                if not factor:
                    warnings.append(
                        f"단위가 다른 측정값은 비교하지 않았습니다: {match.group(0)}"
                    )
                    continue
                before *= factor[0]
                after *= factor[1]
                unit = "ms" if "ms" in {bunit, aunit} else aunit
            else:
                unit = bunit
            delta = after - before
            percent = round((delta / before) * 100, 1) if before else None
            start = max(0, match.start() - 120)
            conditions = re.sub(r"\s+", " ", text[start : match.end() + 120]).strip()
            lowered_conditions = conditions.lower()
            looks_like_goal = any(
                marker in lowered_conditions for marker in _GOAL_MARKERS
            )
            has_measurement_signal = any(
                marker in lowered_conditions for marker in _MEASUREMENT_MARKERS
            )
            verified = (
                document.kind in {"performance", "test", "report"}
                and not document.deleted
                and has_measurement_signal
                and not looks_like_goal
            )
            evidence = EvidenceRef(
                kind="measurement",
                title=f"측정: {match.group(0)}",
                path=document.path,
                locator=match.group(0),
                excerpt=conditions[:500],
                verified=verified,
            )
            evidence_pool.append(evidence)
            label = "감소" if delta < 0 else "증가"
            results.append(
                Measurement(
                    id=f"msr_{hashlib.sha256((document.path + match.group(0)).encode()).hexdigest()[:16]}",
                    metric="응답 시간/자원 사용량",
                    before=f"{match.group('before')}{match.group('bunit')}",
                    after=f"{match.group('after')}{match.group('aunit')}",
                    unit=unit,
                    delta=round(delta, 2),
                    change_percent=percent,
                    conditions=conditions[:400],
                    source_path=document.path,
                    evidence_id=evidence.id,
                    verified=verified,
                    note=(
                        f"{abs(percent)}% {label} (문서 기재값)"
                        if percent is not None
                        else "변화율 계산 불가"
                    ),
                )
            )
            if not verified:
                reason = (
                    "목표·계획 문구가 포함되어"
                    if looks_like_goal
                    else "측정 조건이 확인되지 않아"
                )
                results[-1].note += f" — {reason} 참고용"
    return results[:20]


def _timeline(
    repo: GitRepo,
    commits: list[GitCommit],
    files: list[CodeFile],
    category_map: dict[str, list[str]],
    reverted_shas: set[str] | None = None,
) -> list[TimelineStep]:
    reverted_shas = reverted_shas or set()
    hot_files = sorted(
        [
            item
            for item in files
            if item.change_count > 0 and _is_primary_code_path(item.path)
        ],
        key=lambda item: item.change_count,
        reverse=True,
    )[:3]
    steps: list[TimelineStep] = []
    for code_file in hot_files:
        relevant_all = [commit for commit in commits if code_file.path in commit.files]
        # 최근 변경만 보면 최초 구현이 사라진다. 최초 커밋과 최근 커밋을 함께 남긴다.
        selected = relevant_all[:6]
        if relevant_all and relevant_all[-1] not in selected:
            selected.append(relevant_all[-1])
        relevant = list(reversed(selected))
        for commit in relevant:
            if commit.sha in reverted_shas or commit.is_revert or commit.is_merge:
                continue
            patch = repo.patch(commit.sha, code_file.path)
            removed = [
                line[1:].strip()
                for line in patch.splitlines()
                if line.startswith("-") and not line.startswith("---")
            ]
            added = [
                line[1:].strip()
                for line in patch.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            ]
            if not removed and not added:
                continue
            before_text = "\n".join(removed)[:600]
            after_text = "\n".join(added)[:600]
            steps.append(
                TimelineStep(
                    label=f"{code_file.path} · {commit.short}",
                    sha=commit.sha,
                    date=commit.date,
                    summary=commit.subject[:200],
                    before=before_text,
                    after=after_text,
                    change_kind=", ".join(category_map.get(commit.sha, [])[:3]),
                )
            )
            if len(steps) >= 12:
                return steps
    if not steps:
        for commit in commits[:5]:
            steps.append(
                TimelineStep(
                    label=f"{commit.short} · {commit.date}",
                    sha=commit.sha,
                    date=commit.date,
                    summary=commit.subject[:200],
                    change_kind=", ".join(category_map.get(commit.sha, [])[:3]),
                )
            )
    return steps


def _contribution(commits: list[GitCommit], viewer_email: str) -> dict:
    counts: dict[str, dict] = {}
    for commit in commits:
        # 한 커밋의 기여를 작성자와 Co-authored-by 참여자에게 나눈다.
        # 작성자만 세면 pair programming·공동 구현이 단독 성과로 잘못 귀속된다.
        participants = [
            {"name": commit.author, "email": commit.email},
            *[item for item in (commit.co_authors or []) if item.get("email")],
        ]
        seen: set[str] = set()
        unique = []
        for participant in participants:
            key = str(participant.get("email") or participant.get("name") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(participant)
        weight = 1 / max(1, len(unique))
        for participant in unique:
            key = str(participant.get("email") or participant.get("name")).lower()
            entry = counts.setdefault(
                key,
                {
                    "name": participant.get("name") or participant.get("email"),
                    "email": participant.get("email") or "",
                    "commits": 0,
                    "credits": 0.0,
                    "co_authored": bool(
                        participant.get("email")
                        and str(participant.get("email")).lower()
                        != (commit.email or "").lower()
                    ),
                },
            )
            entry["commits"] += 1
            entry["credits"] += weight
    total = sum(item["credits"] for item in counts.values()) or 1
    authors = [
        {**item, "share": round(item["credits"] / total * 100)}
        for item in counts.values()
    ]
    viewer = next(
        (
            item
            for item in authors
            if viewer_email and item["email"].lower().strip() == viewer_email
        ),
        None,
    )
    if len(authors) == 1:
        if viewer:
            role = "단독 작성(커밋 기준)"
        elif viewer_email:
            role = "본인 커밋 없음 · 기여 미확인"
        else:
            role = "단독 작성자(미확인)"
    elif viewer:
        role = f"공동 작업 · 커밋 기여 {viewer['share']}%"
    elif viewer_email:
        role = "본인 커밋 없음 · 기여 미확인"
    else:
        role = "공동 작업(사용자 이메일 미확인)"
    return {
        "authors": sorted(authors, key=lambda item: item["commits"], reverse=True),
        "viewer_email": viewer_email,
        "viewer_share": viewer["share"] if viewer else None,
        "role": role,
    }


def _quality_for(evidence_count: int, measured: bool) -> str:
    if measured:
        return "VERIFIED"
    if evidence_count >= 3:
        return "SUPPORTED_INFERENCE"
    return "HYPOTHESIS"


def _candidates(
    root: Path,
    commits: list[GitCommit],
    code_files: list[CodeFile],
    documents: list[DocRecord],
    category_map: dict[str, list[str]],
    measurements: list[Measurement],
    implemented_claims: list[dict],
    viewer_email: str,
    warnings: list[str],
    evidence_pool: list[EvidenceRef],
    reverted_shas: set[str] | None = None,
) -> list[Candidate]:
    reverted_shas = reverted_shas or set()
    groups: dict[tuple[str, str], dict] = {}
    for commit in commits:
        if commit.sha in reverted_shas or commit.is_revert or commit.is_merge:
            continue
        categories = category_map.get(commit.sha) or []
        if not categories:
            continue
        for path in commit.files[:5]:
            if not _is_primary_code_path(path):
                continue
            for category in categories[:2]:
                if category in {"docs", "testing", "feature"}:
                    continue
                if Path(path).name in {"Dockerfile", "Makefile"} and category not in {
                    "delivery",
                    "security",
                }:
                    continue
                key = (path, category)
                group = groups.setdefault(
                    key,
                    {
                        "commits": [],
                        "path": path,
                        "category": category,
                        "insertions": 0,
                        "deletions": 0,
                    },
                )
                group["commits"].append(commit)
                group["insertions"] += commit.insertions
                group["deletions"] += commit.deletions

    candidates: list[Candidate] = []
    measurement_by_source = {item.source_path: item for item in measurements}
    ordered_groups = sorted(
        groups.items(),
        key=lambda item: (
            _CANDIDATE_WEIGHT.get(item[1]["category"], 1),
            item[1]["insertions"] + item[1]["deletions"],
            len(item[1]["commits"]),
        ),
        reverse=True,
    )
    for (path, category), group in ordered_groups[:40]:
        group_commits = sorted(group["commits"], key=lambda item: item.date)
        files = [item for item in code_files if item.path == path]
        code_file = files[0] if files else None
        current_path = root / path
        if not current_path.is_file() or current_path.is_symlink():
            warnings.append(
                f"현재 HEAD에 없는 파일의 과거 변경은 성과 후보에서 제외했습니다: {path}"
            )
            continue
        changed_lines = group["insertions"] + group["deletions"]
        if changed_lines < 3 and category not in {"security", "stability"}:
            continue
        path_tokens = [
            token for token in _tokens(path) if token not in _GENERIC_PATH_TOKENS
        ]
        symbols = [
            symbol.lower()
            for symbol in (code_file.symbols[:8] if code_file else [])
            if len(symbol) >= 4
        ]
        docs_matching = [
            document
            for document in documents
            if (
                document.kind != "reference"
                or any(symbol in document.excerpt.lower() for symbol in symbols)
            )
            and (
                document.path in path
                or any(symbol in document.excerpt.lower() for symbol in symbols)
                or (
                    len(path_tokens) >= 2
                    and sum(
                        1 for token in path_tokens if token in document.excerpt.lower()
                    )
                    >= 2
                )
            )
        ][:2]
        path_text = (path + " " + " ".join(symbols)).lower()
        claim_link = next(
            (
                item
                for item in implemented_claims
                if item["quality"] in {"VERIFIED", "SUPPORTED_INFERENCE"}
                and any(
                    token in path_text
                    for token in item["tokens"]
                    if token not in _GENERIC_PATH_TOKENS
                )
            ),
            None,
        )
        measurement = measurement_by_source.get(path)
        if measurement is None:
            for item in measurements:
                if any(symbol in item.conditions.lower() for symbol in symbols):
                    measurement = item
                    break
        evidence: list[EvidenceRef] = []
        for commit in group_commits[:3]:
            evidence.append(
                EvidenceRef(
                    kind="commit",
                    title=f"{commit.short} {commit.subject[:80]}",
                    path=path,
                    locator=commit.sha,
                    excerpt=f"{commit.date} · {commit.author} · +{commit.insertions}/-{commit.deletions}",
                    verified=True,
                )
            )
        if code_file:
            evidence.append(
                EvidenceRef(
                    kind="code",
                    title=f"현재 구현: {path}",
                    path=path,
                    locator=", ".join(code_file.symbols[:5]),
                    excerpt=code_file.excerpt[:600],
                    verified=True,
                )
            )
        for document in docs_matching:
            evidence.append(
                EvidenceRef(
                    kind="document",
                    title=f"문서: {document.path}",
                    path=document.path,
                    locator=f"{document.kind}",
                    excerpt=document.summary[:500],
                    verified=not document.deleted,
                )
            )
        if measurement:
            evidence.append(
                EvidenceRef(
                    kind="measurement",
                    title=f"측정 근거: {measurement.before} → {measurement.after}",
                    path=measurement.source_path,
                    locator=measurement.id,
                    excerpt=measurement.conditions,
                    verified=measurement.verified,
                )
            )
        test_file = next(
            (
                item
                for item in code_files
                if "test" in item.path.lower()
                and (
                    Path(path).stem not in _GENERIC_PATH_TOKENS
                    and Path(path).stem.lower() in item.excerpt.lower()
                    or any(symbol in item.excerpt.lower() for symbol in symbols)
                )
            ),
            None,
        )
        if test_file:
            evidence.append(
                EvidenceRef(
                    kind="test",
                    title=f"테스트: {test_file.path}",
                    path=test_file.path,
                    locator=", ".join(test_file.functions[:4]),
                    excerpt=test_file.excerpt[:400],
                    verified=True,
                )
            )

        label = CATEGORY_LABELS.get(category, category)
        problem = {
            "stability": "장애·실패 상황에서 복구 경로가 제한적이었습니다.",
            "performance": "반복 연산·조회 비용이 구조적으로 누적될 수 있었습니다.",
            "memory": "전체 데이터를 한 번에 적재하는 처리 방식이었습니다.",
            "concurrency": "동기 처리로 대기 시간이 길어질 수 있었습니다.",
            "error_handling": "예외 상황이 상위로 전파되거나 누락될 수 있었습니다.",
            "security": "입력 검증·권한 확인이 일관되지 않았습니다.",
            "testing": "변경 동작을 고정하는 검증이 부족했습니다.",
            "maintainability": "중복·결합도로 변경 영향 범위가 컸습니다.",
            "delivery": "배포·검증 절차가 수동에 의존했습니다.",
            "observability": "실패 원인을 사후에 확인하기 어려웠습니다.",
        }.get(category, "기존 구조의 한계를 해소하는 변경이 있었습니다.")
        action = (
            f"{path} 에서 "
            f"{', '.join(dict.fromkeys(commit.subject[:60] for commit in group_commits[:2]))} "
            "변경을 수행했습니다. 파일별 변경 전후는 타임라인과 코드 근거를 참고하세요."
        )
        result = (
            f"{path} 의 {label} 관련 구현이 변경되었습니다."
            if not measurement or not measurement.verified
            else f"{measurement.before} → {measurement.after} ({measurement.note})"
        )
        if claim_link:
            result += " 관련 문서 주장과 구현이 연결됩니다."
            evidence.append(
                EvidenceRef(
                    kind="document",
                    title=f"문서 주장 연결: {claim_link['claim']['text'][:80]}",
                    path=claim_link["claim"]["doc"].path,
                    locator="교차 분석",
                    excerpt=claim_link["claim"]["text"],
                    verified=claim_link["quality"] == "VERIFIED",
                )
            )

        evidence_pool.extend(evidence)
        quality = _quality_for(
            len(evidence), bool(measurement and measurement.verified)
        )
        confidence = {"VERIFIED": 85, "SUPPORTED_INFERENCE": 65, "HYPOTHESIS": 40}.get(
            quality, 30
        )
        contribution = _contribution(group_commits, viewer_email)
        attribution_note = []
        if viewer_email and contribution.get("viewer_share") is None:
            quality = "HYPOTHESIS"
            confidence = min(confidence, 30)
            attribution_note.append(
                "본인 이메일과 일치하는 커밋이 없어 개인 성과로 귀속하지 않습니다."
            )
        categories = list(
            dict.fromkeys(
                [
                    category,
                    *(
                        _categories(
                            path + " " + (code_file.excerpt if code_file else "")
                        )[:2]
                    ),
                ]
            )
        )
        candidates.append(
            Candidate(
                title=f"{label}: {path}",
                problem=problem,
                action=action,
                result=result,
                impact_categories=categories[:3],
                quality=quality,
                confidence=confidence,
                evidence_ids=[item.id for item in evidence],
                measurement_id=measurement.id if measurement else "",
                contribution=contribution,
                notes=[
                    "커밋 메시지가 아니라 실제 변경 파일·diff·문서·테스트를 근거로 생성했습니다.",
                    "성과로 확정하려면 사용자 확인이 필요합니다.",
                    *attribution_note,
                ],
            )
        )
        # 파일×카테고리 그룹 상한. 12개는 서로 다른 파일의 저가중치 후보
        # (배포 설정·관측성)를 잘라 Recall 을 낮췄다(2026-11-15 평가).
        if len(candidates) >= 14:
            break

    # 측정 근거가 있지만 그룹에 연결되지 않은 경우 별도 후보
    for measurement in measurements:
        if measurement.verified and not any(
            item.measurement_id == measurement.id for item in candidates
        ):
            evidence = [
                EvidenceRef(
                    kind="measurement",
                    title=f"측정: {measurement.before} → {measurement.after}",
                    path=measurement.source_path,
                    locator=measurement.id,
                    excerpt=measurement.conditions,
                    verified=True,
                )
            ]
            evidence_pool.extend(evidence)
            candidates.append(
                Candidate(
                    title=f"측정된 개선: {measurement.source_path}",
                    problem="측정 자료에 전후 값이 기록되어 있습니다.",
                    action=measurement.conditions[:300],
                    result=f"{measurement.before} → {measurement.after} ({measurement.note})",
                    impact_categories=["performance"],
                    quality="VERIFIED",
                    confidence=80,
                    evidence_ids=[item.id for item in evidence],
                    measurement_id=measurement.id,
                    contribution={"authors": [], "role": "문서 기반 측정"},
                    notes=["문서에 기록된 측정값입니다. 측정 조건을 확인하세요."],
                )
            )
            if len(candidates) >= 14:
                break

    # 근거 부족 후보는 삭제하지 않고 별도 표시한다.
    for candidate in candidates:
        if candidate.measurement_id:
            continue
        if len(candidate.evidence_ids) <= 1:
            candidate.quality = "INSUFFICIENT_EVIDENCE"
            candidate.confidence = min(candidate.confidence, 30)
            candidate.notes.append("근거가 1건뿐이라 확정하지 않습니다.")
    return candidates


def _merge_evidence(analysis: ProjectAnalysis, candidates: list[Candidate]) -> None:
    # 후보에 연결된 EvidenceRef 를 분석 결과에 모아 UI/적용에서 재사용한다.
    # 저장은 evidence 목록을 analysis 에 직접 넣지 않고 candidate.evidence_ids 로 참조한다.
    return None


def analyze_project(
    project_path: str,
    *,
    author_email: str = "",
    use_ai: bool = True,
    provider: Optional[str] = None,
    force: bool = False,
    store: Optional[JsonStore] = None,
) -> ProjectAnalysis:
    root = Path(project_path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"프로젝트 디렉터리를 찾을 수 없습니다: {project_path}")
    store = store or get_store()
    warnings: list[str] = []
    repo = GitRepo(root)
    documents = discover_documents(root, warnings)
    commits = repo.commits()
    head_sha = repo.head_sha()
    reverted_shas = repo.reverted_shas()
    viewer_email = (author_email.strip() or repo.user_email()).lower()
    fingerprint = (
        f"{head_sha}:{doc_fingerprint(documents)}:{len(commits)}:{viewer_email}"
    )
    git_error = bool(repo.errors)
    if git_error:
        warnings.extend(dict.fromkeys(repo.errors))
        warnings.append(
            "Git 이력을 완전히 읽지 못해 분석 결과가 일부만 완료되었습니다."
        )

    if not force:
        for previous in store.all("project_analyses", ProjectAnalysis):
            if (
                previous.project_path == str(root)
                and previous.fingerprint == fingerprint
                and previous.status == "completed"
                and (not use_ai or previous.ai.status == "completed")
            ):
                previous.incremental = True
                previous.stats = {
                    **previous.stats,
                    "cached": True,
                    "note": "동일한 HEAD·문서 상태라 이전 분석을 재사용했습니다.",
                }
                return previous

    code_files = _inventory(root, commits, warnings)
    category_map = _commit_categories(repo, commits)
    for commit in commits:
        commit.categories = category_map.get(commit.sha, [])

    evidence_pool: list[EvidenceRef] = []
    claims = _claims(documents)
    findings, implemented_claims = _match_claims(
        claims, code_files, documents, evidence_pool
    )
    measurements = _measurements(documents, warnings, evidence_pool)

    # 코드만 존재하고 문서 언급이 없는 주요 변경
    doc_corpus = " ".join(document.excerpt for document in documents).lower()
    for code_file in sorted(
        code_files, key=lambda item: item.change_count, reverse=True
    )[:8]:
        if code_file.change_count < 2 or not code_file.categories:
            continue
        if any(token in doc_corpus for token in _tokens(code_file.path)[:2]):
            continue
        findings.append(
            Finding(
                title=f"문서에 없는 구현 변경: {code_file.path}",
                detail=(
                    f"{code_file.change_count}개 커밋에서 변경되었고 "
                    f"({', '.join(code_file.categories[:3])}) 관련 문서 설명을 찾지 못했습니다."
                ),
                kind="code_only",
                quality="SUPPORTED_INFERENCE",
                paths=[code_file.path],
            )
        )

    timeline = _timeline(repo, commits, code_files, category_map, reverted_shas)
    candidates = _candidates(
        root,
        commits,
        code_files,
        documents,
        category_map,
        measurements,
        implemented_claims,
        viewer_email,
        warnings,
        evidence_pool,
        reverted_shas,
    )
    if reverted_shas or any(commit.is_revert for commit in commits):
        warnings.append(
            f"리버트된 변경 {len(reverted_shas)}건은 현재 코드와 비교해 성과 후보에서 제외했습니다."
        )

    quality_counts = {
        level: 0
        for level in (
            "VERIFIED",
            "SUPPORTED_INFERENCE",
            "HYPOTHESIS",
            "INSUFFICIENT_EVIDENCE",
        )
    }
    for candidate in candidates:
        quality_counts[candidate.quality] = quality_counts.get(candidate.quality, 0) + 1

    stats = {
        "documents": len(documents),
        "documents_deleted": sum(1 for item in documents if item.deleted),
        "doc_chars": sum(len(item.excerpt) for item in documents),
        "code_files": len(code_files),
        "code_lines": sum(item.lines for item in code_files),
        "commits_scanned": len(commits),
        "commit_range": (
            f"{commits[-1].date} ~ {commits[0].date}" if commits else "Git 이력 없음"
        ),
        "claims": len(claims),
        "implemented_claims": len(implemented_claims),
        "candidates": len(candidates),
        "measurements": len(measurements),
        "contributors": len({commit.email for commit in commits}),
    }
    analysis = ProjectAnalysis(
        project_path=str(root),
        project_name=root.name,
        head_sha=head_sha,
        status="partial" if git_error else "completed",
        quality_summary=quality_counts,
        documents=documents,
        code_files=code_files,
        commits=commits[:120],
        timeline=timeline,
        findings=findings[:40],
        measurements=measurements,
        candidates=candidates,
        evidence=evidence_pool,
        warnings=warnings,
        stats=stats,
        fingerprint=fingerprint,
        ai=AIStageInfo(requested=use_ai),
    )

    if use_ai:
        from impactnote.core.intel.ai_stage import enrich_with_ai

        enrich_with_ai(analysis, store=store, provider=provider)
    store.put("project_analyses", analysis)
    return analysis


__all__ = ["analyze_project", "CATEGORY_LABELS", "LANGUAGES", "_is_primary_code_path"]
