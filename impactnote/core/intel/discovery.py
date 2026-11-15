"""프로젝트 자료 자동 발견.

- 문서: README/CHANGELOG/docs/design/adr/specs/reports/tests/benchmarks 등
- 형식: md/txt/rst/html/json/yaml/csv + docx/xlsx/pptx/pdf(가능한 경우) + mermaid/plantuml/drawio
- Git 에서 삭제·이동된 문서도 제한적으로 복원해 단서로 사용
- `.env`·키·자격증명·개인정보 파일은 읽지 않는다.
"""

from __future__ import annotations

import hashlib
import os
import re
import zipfile
from pathlib import Path
from typing import Iterable

from impactnote.core.intel.gitintel import GitRepo
from impactnote.core.intel.models import DocRecord

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".next",
    ".nuxt",
    "dist",
    "build",
    "target",
    "out",
    "coverage",
    ".idea",
    ".vscode",
    ".claude",
    ".superpowers",
    "site-packages",
}

SECRET_NAME_PATTERNS = (
    re.compile(r"^\.env", re.IGNORECASE),
    re.compile(r"\.(pem|key|p12|pfx|keystore|jks)$", re.IGNORECASE),
    re.compile(
        r"(^|[._-])(secret|credential|credentials|password|passwd|token)s?([._-]|$)",
        re.IGNORECASE,
    ),
    re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)", re.IGNORECASE),
    re.compile(r"^(\.npmrc|\.pypirc|\.netrc|\.git-credentials)$", re.IGNORECASE),
)

DOC_EXTENSIONS = {
    ".md",
    ".markdown",
    ".mdx",
    ".rst",
    ".txt",
    ".adoc",
    ".asciidoc",
    ".html",
    ".htm",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".tsv",
    ".xml",
    ".drawio",
    ".puml",
    ".plantuml",
    ".mmd",
    ".mermaid",
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
}

CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".svelte",
    ".java",
    ".kt",
    ".kts",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".cs",
    ".c",
    ".h",
    ".cpp",
    ".cc",
    ".hpp",
    ".swift",
    ".scala",
    ".dart",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".tf",
    ".dockerfile",
    ".html",
    ".css",
    ".scss",
}

TEXT_EXTENSIONS = DOC_EXTENSIONS | CODE_EXTENSIONS | {".toml", ".ini", ".cfg", ".conf"}

MAX_DOC_BYTES = 400_000
MAX_DOCS = 160
MAX_EXCERPT = 4000
MAX_TOTAL_CHARS = 400_000

_SECRET_VALUE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd)\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{8,}"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S
)

_DOC_KIND_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "requirements",
        ("requirement", "요구사항", "기획", "prd", "user story", "use case"),
    ),
    (
        "design",
        (
            "architecture",
            "아키텍처",
            "design",
            "설계",
            "adr",
            "decision",
            "의사결정",
            "tradeoff",
            "트레이드오프",
        ),
    ),
    ("technical_review", ("review", "검토", "rfc", "technical", "기술 검토", "대안")),
    ("incident", ("incident", "장애", "postmortem", "포스트모템", "rca", "회고")),
    ("test", ("test", "테스트", "benchmark", "벤치마크", "coverage", "검증")),
    (
        "performance",
        (
            "performance",
            "성능",
            "latency",
            "throughput",
            "memory",
            "응답 시간",
            "처리량",
        ),
    ),
    (
        "deployment",
        ("deploy", "배포", "release", "운영", "runbook", "rollback", "롤백", "ci/cd"),
    ),
    ("report", ("report", "결과", "성과", "실적", "summary", "리포트")),
    (
        "implementation",
        ("implementation", "구현", "usage", "사용법", "guide", "가이드", "how to"),
    ),
]


def is_secret_name(name: str) -> bool:
    return any(pattern.search(name) for pattern in SECRET_NAME_PATTERNS)


def redact(text: str) -> str:
    text = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text or "")
    return _SECRET_VALUE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp949", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _strip_xml(raw: str) -> str:
    raw = re.sub(r"<w:p[ >]", "\n<w:p ", raw)
    raw = re.sub(r"</a:p>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = (
        raw.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    return re.sub(r"[ \t]+", " ", raw)


def _binary_document_text(path: Path, suffix: str) -> str:
    """docx/xlsx/pptx 를 외부 의존성 없이 XML 로 추출한다."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if suffix == ".docx":
                targets = [name for name in names if name == "word/document.xml"]
            elif suffix == ".pptx":
                targets = [
                    name
                    for name in names
                    if re.match(r"ppt/slides/slide\d+\.xml$", name)
                ]
            elif suffix == ".xlsx":
                targets = [name for name in names if name == "xl/sharedStrings.xml"]
            else:
                targets = []
            texts = []
            for name in targets[:60]:
                try:
                    texts.append(
                        _strip_xml(archive.read(name).decode("utf-8", errors="ignore"))
                    )
                except Exception:
                    continue
            return "\n".join(texts)
    except (zipfile.BadZipFile, OSError):
        return ""


def extract_text(path: Path) -> tuple[str, str]:
    """(text, warning) 을 반환한다."""
    suffix = path.suffix.lower()
    if path.stat().st_size > MAX_DOC_BYTES:
        return "", f"파일이 커서 건너뜀: {path.name}"
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(path))
            pages = [(page.extract_text() or "") for page in reader.pages[:60]]
            return "\n".join(pages), ""
        except Exception:
            return "", f"PDF 텍스트를 추출하지 못함: {path.name}"
    if suffix in {".docx", ".xlsx", ".pptx"}:
        text = _binary_document_text(path, suffix)
        return text, "" if text else f"문서에서 텍스트를 찾지 못함: {path.name}"
    try:
        raw = path.read_bytes()
    except OSError:
        return "", f"파일을 읽지 못함: {path.name}"
    if b"\x00" in raw[:2000]:
        return "", f"바이너리로 판단해 건너뜀: {path.name}"
    return _decode(raw), ""


def classify_document(path: Path, text: str) -> str:
    """파일 이름과 실제 내용을 함께 보고 역할을 분류한다."""
    haystack = f"{path.as_posix().lower()} {text[:6000].lower()}"
    scores: dict[str, int] = {}
    for kind, keywords in _DOC_KIND_RULES:
        score = 0
        for keyword in keywords:
            if keyword in haystack:
                score += 3 if keyword in path.as_posix().lower() else 1
        scores[kind] = score
    best = max(scores, key=scores.get) if scores else "reference"
    return best if scores.get(best, 0) > 0 else "reference"


def _headings(text: str, suffix: str) -> list[str]:
    headings: list[str] = []
    if suffix in {".md", ".markdown", ".mdx", ".rst", ".adoc"}:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                if title:
                    headings.append(title[:120])
            elif stripped and set(stripped) <= {"=", "-", "~"} and len(stripped) >= 3:
                continue
    return headings[:20]


def _summary(text: str) -> str:
    for block in re.split(r"\n\s*\n", text):
        cleaned = re.sub(r"\s+", " ", block).strip(" #*->`")
        if len(cleaned) >= 40 and not cleaned.startswith(("!", "[!", "|")):
            return cleaned[:600]
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:300]


def _walk_documents(root: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        dirs[:] = [
            name for name in dirs if name not in SKIP_DIRS and not name.startswith(".")
        ]
        for name in files:
            if is_secret_name(name) or name.startswith("~$"):
                continue
            path = Path(current) / name
            if path.suffix.lower() in DOC_EXTENSIONS:
                yield path


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def discover_documents(root: Path, warnings: list[str]) -> list[DocRecord]:
    repo = GitRepo(root)
    tracked = repo.tracked_files() if repo.is_repo else set()
    documents: list[DocRecord] = []
    total_chars = 0

    candidates = sorted(
        _walk_documents(root), key=lambda item: item.stat().st_mtime, reverse=True
    )
    for path in candidates:
        if len(documents) >= MAX_DOCS or total_chars >= MAX_TOTAL_CHARS:
            warnings.append("문서가 많아 일부만 분석했습니다(최대 160개).")
            break
        try:
            text, warning = extract_text(path)
        except OSError:
            warnings.append(f"문서를 읽지 못함: {path.name}")
            continue
        if warning:
            warnings.append(warning)
        if not text.strip():
            if path.suffix.lower() in {
                ".json",
                ".yaml",
                ".yml",
                ".csv",
                ".tsv",
                ".xml",
                ".drawio",
            }:
                continue
            continue
        relative = path.relative_to(root).as_posix()
        # 절대 경로에는 임시 디렉터리 이름 등 우연한 키워드가 섞이므로 상대 경로로 분류한다.
        document_kind = classify_document(Path(relative), text)
        excerpt = redact(text[:MAX_EXCERPT])
        total_chars += len(excerpt)
        documents.append(
            DocRecord(
                id=f"doc_{_content_hash(relative + excerpt)}",
                path=relative,
                title=path.stem,
                kind=document_kind,
                chars=len(text),
                headings=_headings(text, path.suffix.lower()),
                summary=redact(_summary(text)),
                excerpt=excerpt,
                git_tracked=relative in tracked if tracked else False,
                modified_at=str(int(path.stat().st_mtime)),
            )
        )

    # Git 에서 삭제된 문서도 단서로 복원한다(내용은 마지막 버전 일부).
    if repo.is_repo:
        for path, sha in repo.deleted_documents(limit=20):
            relative = path
            if any(part.startswith(".") for part in Path(relative).parts):
                continue
            if any(item.path == relative for item in documents):
                continue
            if Path(relative).suffix.lower() not in DOC_EXTENSIONS or is_secret_name(
                Path(relative).name
            ):
                continue
            text = repo.file_at(f"{sha}^", relative) or ""
            if not text.strip():
                continue
            documents.append(
                DocRecord(
                    id=f"doc_{_content_hash(relative + sha)}",
                    path=relative,
                    title=Path(relative).stem,
                    kind=classify_document(Path(relative), text),
                    chars=len(text),
                    headings=_headings(text, Path(relative).suffix.lower()),
                    summary=redact(_summary(text)),
                    excerpt=redact(text[:MAX_EXCERPT]),
                    git_tracked=True,
                    deleted=True,
                    modified_at="",
                )
            )
            warnings.append(f"Git 이력에서 삭제된 문서를 참고했습니다: {relative}")
    return documents


def iter_code_files(root: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        dirs[:] = [
            name for name in dirs if name not in SKIP_DIRS and not name.startswith(".")
        ]
        for name in files:
            if is_secret_name(name):
                continue
            path = Path(current) / name
            if path.suffix.lower() in CODE_EXTENSIONS or name in {
                "Dockerfile",
                "Makefile",
            }:
                yield path


def read_code(path: Path) -> str:
    try:
        if path.stat().st_size > 300_000:
            return ""
        return _decode(path.read_bytes())
    except OSError:
        return ""


def doc_fingerprint(documents: list[DocRecord]) -> str:
    digest = hashlib.sha256()
    for document in sorted(documents, key=lambda item: item.path):
        digest.update(document.path.encode())
        digest.update(str(document.chars).encode())
        digest.update(document.summary.encode())
    return digest.hexdigest()[:20]


__all__ = [
    "CODE_EXTENSIONS",
    "DOC_EXTENSIONS",
    "SKIP_DIRS",
    "classify_document",
    "discover_documents",
    "doc_fingerprint",
    "extract_text",
    "is_secret_name",
    "iter_code_files",
    "read_code",
    "redact",
]
