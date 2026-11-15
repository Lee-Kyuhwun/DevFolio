"""통제된 Git 저장소를 만들어 ImpactNote 분석기를 실제로 실행한다.

평가 데이터와 분석 대상이 섞이지 않도록 저장소는 임시 디렉터리에 매번 새로 만든다.
커밋 작성자·날짜·본문(Co-authored-by)은 Ground Truth 와 함께 고정한다.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Alice",
    "GIT_AUTHOR_EMAIL": "alice@example.com",
    "GIT_COMMITTER_NAME": "Alice",
    "GIT_COMMITTER_EMAIL": "alice@example.com",
}

AUTHORS = {
    "alice": ("Alice", "alice@example.com"),
    "bob": ("Bob", "bob@example.com"),
    "carol": ("Carol", "carol@example.com"),
    "manager": ("Manager", "manager@example.com"),
}


def _run(root: Path, *args: str, author: str = "alice", date: str) -> str:
    name, email = AUTHORS[author]
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_AUTHOR_DATE": f"{date}T09:00:00+09:00",
        "GIT_COMMITTER_DATE": f"{date}T09:00:00+09:00",
    }
    process = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if process.returncode:
        raise RuntimeError(process.stderr.strip() or f"git 실패: {args}")
    return process.stdout


def _write(root: Path, path: str, content: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _commit(
    root: Path,
    message: str,
    *,
    date: str,
    author: str = "alice",
    trailer: str = "",
) -> str:
    body = f"{message}\n\n{trailer}".rstrip() + "\n"
    _run(root, "add", "-A", date=date, author=author)
    _run(root, "commit", "-m", body, date=date, author=author)
    return _run(root, "rev-parse", "HEAD", date=date, author=author).strip()


def build_fixture(root: Path) -> Path:
    """12개 실제 성과 + 8개 비성과 커밋을 가진 저장소를 만든다."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _run(root, "init", "-b", "main", date="2026-01-01")
    _run(root, "config", "user.email", "alice@example.com", date="2026-01-01")
    _run(root, "config", "user.name", "Alice", date="2026-01-01")

    _write(root, "README.md", "# Fixture\n\n통제된 평가용 저장소.\n")
    _commit(root, "chore: fixture 초기화", date="2026-01-01")

    # 1) cache — performance
    _write(
        root,
        "app/cache.py",
        "from functools import lru_cache\n\n"
        "@lru_cache(maxsize=128)\n"
        "def load_rate(currency: str) -> float:\n"
        "    return 1000.0\n",
    )
    _commit(root, "refactor: 환율 조회 경로 정리", date="2026-01-02")

    # 2) retry — stability
    _write(
        root,
        "app/retry.py",
        "import time\n\n"
        "def fetch(call, attempts=3):\n"
        "    for attempt in range(attempts):\n"
        "        try:\n"
        "            return call()\n"
        "        except TimeoutError:\n"
        "            time.sleep(0.1 * (2 ** attempt))\n"
        "    raise RuntimeError('retry exhausted')\n",
    )
    _commit(root, "feat: 외부 호출 실패 경로 보강", date="2026-01-03")

    # 3) auth — security
    _write(
        root,
        "app/auth.py",
        "def validate_token(token: str) -> bool:\n"
        "    if not token or len(token) < 8:\n"
        "        raise ValueError('invalid token')\n"
        "    return token.startswith('Bearer ')\n\n"
        "def check_permission(role: str) -> bool:\n"
        "    return role in {'admin', 'member'}\n",
    )
    _commit(root, "feat: 요청 권한 확인 추가", date="2026-01-04", author="bob")

    # 4) export — memory (streaming)
    _write(
        root,
        "app/export.py",
        "def export_rows(rows):\n"
        "    for row in rows:\n"
        "        yield ','.join(str(value) for value in row)\n",
    )
    _commit(root, "feat: 내보내기 스트리밍", date="2026-01-05")
    _write(
        root,
        "app/export.py",
        "def export_rows(rows, header=None):\n"
        "    if header:\n"
        "        yield ','.join(header)\n"
        "    for row in rows:\n"
        "        yield ','.join(str(value) for value in row)\n",
    )
    _commit(root, "feat: 내보내기 헤더 지원", date="2026-01-06", author="bob")

    # 5) queue — concurrency
    _write(
        root,
        "app/queue.py",
        "import asyncio\n\n"
        "class JobQueue:\n"
        "    def __init__(self):\n"
        "        self._lock = asyncio.Lock()\n\n"
        "    async def put(self, job):\n"
        "        async with self._lock:\n"
        "            return job\n",
    )
    _commit(root, "feat: 작업 큐 직렬화", date="2026-01-07", author="carol")

    # 6) errors — error_handling
    _write(
        root,
        "app/errors.py",
        "def parse(value):\n"
        "    try:\n"
        "        return int(value)\n"
        "    except (TypeError, ValueError) as exc:\n"
        "        raise ValueError('invalid number') from exc\n"
        "    finally:\n"
        "        pass\n",
    )
    _commit(root, "feat: 숫자 파싱 예외 정리", date="2026-01-08")

    # 7) metrics — observability
    _write(
        root,
        "app/metrics.py",
        "import logging\n\n"
        "logger = logging.getLogger(__name__)\n\n"
        "def record_metric(name: str, value: float) -> None:\n"
        "    logger.info('metric=%s value=%s', name, value)\n",
    )
    _commit(root, "feat: 처리 결과 기록", date="2026-01-09")

    # 8) Dockerfile — delivery
    _write(
        root,
        "Dockerfile",
        "FROM python:3.12-slim\n# deploy release image\nCOPY . /app\nWORKDIR /app\n",
    )
    _commit(root, "build: 배포 이미지 추가", date="2026-01-10")

    # 9) session — security, co-authored
    _write(
        root,
        "app/session.py",
        "def create_session(token: str) -> dict:\n"
        "    if not token:\n"
        "        raise ValueError('token required')\n"
        "    return {'token': token, 'active': True}\n",
    )
    _commit(
        root,
        "feat: 세션 토큰 검증",
        date="2026-01-11",
        author="bob",
        trailer="Co-authored-by: Alice <alice@example.com>",
    )

    # 10) pipeline — concurrency, two authors
    _write(
        root,
        "app/pipeline.py",
        "import asyncio\n\n"
        "async def run_all(items):\n"
        "    async def one(item):\n"
        "        await asyncio.sleep(0)\n"
        "        return item\n"
        "    return [await one(item) for item in items]\n",
    )
    _commit(root, "feat: 파이프라인 비동기 처리", date="2026-01-12")
    _write(
        root,
        "app/pipeline.py",
        "import asyncio\n\n"
        "async def run_all(items):\n"
        "    async def one(item):\n"
        "        await asyncio.sleep(0)\n"
        "        return item\n"
        "    return await asyncio.gather(*(one(item) for item in items))\n",
    )
    _commit(root, "feat: 파이프라인 동시 실행", date="2026-01-13", author="carol")

    # 11) report — memory, two authors
    _write(
        root,
        "app/report.py",
        "def iter_report(rows):\n    for row in rows:\n        yield row\n",
    )
    _commit(root, "feat: 보고서 순차 생성", date="2026-01-14")
    _write(
        root,
        "app/report.py",
        "def iter_report(rows, chunk=100):\n"
        "    buffer = []\n"
        "    for row in rows:\n"
        "        buffer.append(row)\n"
        "        if len(buffer) >= chunk:\n"
        "            yield from buffer\n"
        "            buffer = []\n"
        "    yield from buffer\n",
    )
    _commit(root, "feat: 보고서 chunk 처리", date="2026-01-15", author="bob")

    # 12) 문서에 기록된 실제 측정 — measurement
    _write(
        root,
        "docs/performance.md",
        "# 성능 측정\n\n"
        "## 측정 결과\n\n"
        "부하 테스트에서 p95 latency 200ms → 180ms 로 측정되었다.\n"
        "조건: 동일 장비, 100 concurrent requests, 5분 실행.\n",
    )
    _commit(root, "docs: 성능 측정 결과 기록", date="2026-01-16")

    # --- 비성과 8개 ----------------------------------------------------
    _write(
        root,
        "app/format.py",
        "def add(a, b):\n    return a + b\n",
    )
    _commit(root, "style: 파일 추가", date="2026-02-01")
    _write(
        root,
        "app/format.py",
        "def add(a, b):\n    return a  +  b\n",
    )
    _commit(root, "style: 공백 정리", date="2026-02-02")

    _write(
        root,
        "app/comment.py",
        "def total(values):\n    return sum(values)\n",
    )
    _commit(root, "chore: 유틸 추가", date="2026-02-03")
    _write(
        root,
        "app/comment.py",
        "def total(values):\n    # cache 결과를 합산한다\n    return sum(values)\n",
    )
    _commit(root, "docs: 주석 보강", date="2026-02-04")

    _write(
        root,
        "app/legacy.py",
        "def old_feature():\n    return 'cache legacy'\n",
    )
    legacy_sha = _commit(root, "feat: legacy 기능 추가", date="2026-02-05")
    _run(root, "revert", "--no-edit", legacy_sha, date="2026-02-06")

    _write(
        root,
        "app/deleted.py",
        "def gone():\n    return 'cache'\n",
    )
    _commit(root, "feat: 임시 기능 추가", date="2026-02-07")
    (root / "app/deleted.py").unlink()
    _commit(root, "chore: 임시 기능 제거", date="2026-02-08")

    _write(
        root,
        "docs/guide.md",
        "# 가이드\n\nOAuth2 로그인과 PDF 내보내기를 지원한다.\n",
    )
    _commit(root, "docs: 사용 가이드 추가", date="2026-02-09")

    _write(
        root,
        "tests/test_cache.py",
        "def test_cache_placeholder():\n    assert True\n",
    )
    _commit(root, "test: 캐시 테스트 추가", date="2026-02-10")

    _write(root, "app/tiny.py", "VALUE = 1\n")
    _commit(root, "chore: 상수 추가", date="2026-02-11")
    _write(root, "app/tiny.py", "VALUE = 2\n")
    _commit(root, "chore: 상수 변경", date="2026-02-12")

    _write(root, "app/noise.py", "# cache note\nNOISE = 'a'\n")
    _commit(root, "chore: 설정 문자열", date="2026-02-13")

    _write(root, "app/dependency.py", "VERSION = '1.0'\n")
    _commit(root, "chore: 의존성 표기", date="2026-02-14")
    _write(root, "app/dependency.py", "VERSION = '1.0.1'\n")
    _commit(root, "chore: 의존성 패치", date="2026-02-15")

    return root


__all__ = ["AUTHORS", "build_fixture"]
