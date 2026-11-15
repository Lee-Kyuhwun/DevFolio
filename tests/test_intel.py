"""프로젝트 인텔리전스 엔진 회귀 테스트.

실제 임시 Git 저장소를 만들어 문서·코드·커밋 전후·측정값을 검증한다.
필수 12개 시나리오(Phase 12)를 고정한다.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from impactnote.core import store as store_module
from impactnote.core.intel import analyze_project
from impactnote.core.intel.discovery import is_secret_name
from impactnote.core.service import ImpactService
from impactnote.web.app import create_app


@pytest.fixture()
def intel_env(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPACTNOTE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("IMPACTNOTE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("IMPACTNOTE_LEGACY_DATA_DIR", str(tmp_path / "legacy-data"))
    monkeypatch.setenv("IMPACTNOTE_LEGACY_CONFIG_DIR", str(tmp_path / "legacy-config"))
    store_module.reset_store_for_tests()
    yield tmp_path
    store_module.reset_store_for_tests()


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "other@example.com")
    _git(path, "config", "user.name", "Other Dev")
    return path


def _commit(
    repo: Path,
    message: str,
    author: str = "Other Dev",
    email: str = "other@example.com",
) -> str:
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        f"user.name={author}",
        "-c",
        f"user.email={email}",
        "commit",
        "-q",
        "-m",
        message,
    )
    return _git(repo, "rev-parse", "HEAD")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def repo(tmp_path) -> Path:
    root = _init(tmp_path / "company-project")
    _write(
        root / "README.md",
        "# 결제 배치\n\n대용량 주문을 안정적으로 처리하는 배치 서비스입니다.\n",
    )
    _write(
        root / "docs/implemented.md",
        "# 구현 설명\n\nstream_items 와 fallback 경로를 구현했다. 제너레이터로 배치 처리한다.\n",
    )
    _write(
        root / "docs/design.md",
        "# 설계\n\n외부 API 장애가 발생하면 다른 모델 호출로 자동 전환한다.\n",
    )
    _write(
        root / "docs/unimplemented.md",
        "# 요구사항\n\n사용자 알림 Webhook 기능을 추가한다. Slack 과 Teams 로 전송한다.\n",
    )
    _write(
        root / "docs/performance.md",
        "# 성능 측정\n\n부하 테스트 10회 평균 응답 시간 1200ms → 400ms 로 개선되었다.\n",
    )
    _write(
        root / "app.py",
        "def stream_items(items):\n    return [transform(item) for item in items]\n",
    )
    _write(
        root / "tests/test_app.py",
        "from app import stream_items\n\n\ndef test_stream_items():\n    assert list(stream_items([1])) == [1]\n",
    )
    _commit(root, "initial import")

    _write(
        root / "app.py",
        "def stream_items(items):\n"
        "    for item in items:\n"
        "        yield transform(item)\n\n"
        "def transform(item):\n"
        "    return item\n",
    )
    _commit(root, "update", author="Me", email="me@example.com")

    _write(
        root / "app.py",
        "def stream_items(items):\n"
        "    for item in items:\n"
        "        try:\n"
        "            yield transform(item)\n"
        "        except Exception:\n"
        "            yield fallback(item)\n\n"
        "def transform(item):\n    return item\n\n"
        "def fallback(item):\n    return item\n",
    )
    _commit(root, "tune", author="Me", email="me@example.com")

    # 리버트는 별도 실험 파일에만 적용해 현재 app.py 구현은 유지한다.
    _write(root / "experiment.py", "def experiment():\n    return 'try'\n")
    experiment = _commit(root, "experiment", author="Me", email="me@example.com")
    _git(root, "revert", "--no-edit", experiment)
    return root


def _analyze(root: Path, **kwargs):
    kwargs.setdefault("use_ai", False)
    kwargs.setdefault("force", True)
    return analyze_project(str(root), **kwargs)


def _evidence(analysis):
    return {item.id: item for item in analysis.evidence}


# 1. Git 메시지 없이 코드 변경만으로 후보 발견
def test_code_change_without_message_creates_candidate(intel_env, repo):
    analysis = _analyze(repo, author_email="me@example.com")
    assert any("app.py" in candidate.title for candidate in analysis.candidates)
    candidate = next(item for item in analysis.candidates if "app.py" in item.title)
    assert candidate.problem
    assert candidate.evidence_ids
    subjects = [commit.subject for commit in analysis.commits]
    assert "update" in subjects and "tune" in subjects
    assert any(finding.kind == "code_only" for finding in analysis.findings)


# 2. 문서에만 존재하는 미구현 기능 감지
def test_doc_only_feature_is_not_a_candidate(intel_env, repo):
    analysis = _analyze(repo, author_email="me@example.com")
    doc_only = [finding for finding in analysis.findings if finding.kind == "doc_only"]
    assert any(
        "자동 전환" in finding.title or "Webhook" in finding.title
        for finding in doc_only
    )
    assert any("docs/design.md" in finding.paths for finding in doc_only)
    titles = " ".join(candidate.title for candidate in analysis.candidates)
    assert "자동 전환" not in titles
    assert "Webhook" not in titles


# 3. 문서와 코드가 일치하는 기능 식별
def test_doc_code_match_is_verified_by_tests(intel_env, repo):
    analysis = _analyze(repo, author_email="me@example.com")
    matches = [
        finding for finding in analysis.findings if finding.kind == "doc_code_match"
    ]
    target = next(finding for finding in matches if "stream_items" in finding.title)
    assert target.quality == "VERIFIED"
    assert target.quality == "VERIFIED"
    assert any("docs/implemented.md" in path for path in target.paths)


# 4. 과거 코드와 현재 코드의 차이 분석
def test_timeline_contains_before_and_after(intel_env, repo):
    analysis = _analyze(repo, author_email="me@example.com")
    assert analysis.timeline
    step = next(item for item in analysis.timeline if item.before and item.after)
    assert step.before != step.after
    assert "yield" in (step.after + step.before)
    assert step.sha


# 5. 동일 기능에 대한 여러 커밋 연결
def test_multiple_commits_grouped_into_one_candidate(intel_env, repo):
    analysis = _analyze(repo, author_email="me@example.com")
    refs = _evidence(analysis)
    counts = [
        sum(1 for ref_id in candidate.evidence_ids if refs[ref_id].kind == "commit")
        for candidate in analysis.candidates
        if "app.py" in candidate.title
    ]
    assert max(counts) >= 2


# 6. 리버트 및 실패한 설계 변경 구분
def test_revert_is_excluded_and_reported(intel_env, repo):
    analysis = _analyze(repo, author_email="me@example.com")
    reverts = [commit for commit in analysis.commits if commit.is_revert]
    assert reverts
    assert any("리버트" in warning for warning in analysis.warnings)
    refs = _evidence(analysis)
    cited_commits = {
        refs[ref_id].locator
        for candidate in analysis.candidates
        for ref_id in candidate.evidence_ids
        if refs[ref_id].kind == "commit"
    }
    assert reverts[0].sha not in cited_commits


# 7. 실제 측정 결과로 개선율 계산
def test_measurement_change_percent_is_calculated(intel_env, repo):
    analysis = _analyze(repo, author_email="me@example.com")
    measured = next(item for item in analysis.measurements if item.verified)
    assert measured.before == "1200ms"
    assert measured.after == "400ms"
    assert measured.change_percent == pytest.approx(-66.7)
    assert any(
        candidate.quality == "VERIFIED" and candidate.measurement_id
        for candidate in analysis.candidates
    )


# 8. 측정 결과가 없을 때 허위 수치 생성 차단
def test_apply_measurement_candidate_creates_metric(intel_env, repo):
    analysis = _analyze(repo, author_email="me@example.com")
    candidate = next(item for item in analysis.candidates if item.measurement_id)
    service = ImpactService()
    achievement = service.apply_project_candidate(analysis.id, candidate.id)
    metrics = [
        item for item in service.metrics() if item.achievement_id == achievement.id
    ]
    assert metrics
    assert metrics[0].value == "400"
    assert metrics[0].unit == "ms"
    assert metrics[0].verified is True


def test_no_measurement_means_no_fabricated_numbers(intel_env, tmp_path):
    root = _init(tmp_path / "no-measure")
    _write(root / "README.md", "# 도구\n\n응답 속도를 크게 개선했다.\n")
    _write(
        root / "service.py",
        "def load(path):\n    with open(path) as handle:\n        return handle.read()\n",
    )
    _commit(root, "initial")
    _write(
        root / "service.py",
        "def load(path):\n"
        "    with open(path) as handle:\n"
        "        for line in handle:\n"
        "            yield line\n\n"
        "def retry(fn):\n"
        "    try:\n"
        "        return fn()\n"
        "    except Exception:\n"
        "        return None\n",
    )
    _commit(root, "update")
    analysis = _analyze(root, author_email="other@example.com")
    assert analysis.measurements == []
    for candidate in analysis.candidates:
        assert candidate.quality != "VERIFIED"
        assert "%" not in candidate.result
        assert "%" not in candidate.action
        assert not re.search(r"\d+\s*(ms|MB|초|%)", candidate.result)


# 9. 다른 개발자 기여도 오인 방지
def test_other_developer_contribution_is_not_attributed(intel_env):
    root = _init(intel_env / "someone-else")
    _write(root / "legacy.py", "def run():\n    return 1\n")
    _commit(root, "initial")
    _write(
        root / "legacy.py",
        "import time\n\n"
        "def run():\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:\n"
        "        time.sleep(1)\n"
        "        return 0\n",
    )
    _commit(root, "stability work")
    analysis = _analyze(root, author_email="me@example.com")
    candidate = next(item for item in analysis.candidates if "legacy.py" in item.title)
    assert candidate.contribution["viewer_share"] is None
    assert "본인 커밋 없음" in candidate.contribution["role"]
    assert candidate.quality == "HYPOTHESIS"
    assert any("귀속하지 않습니다" in note for note in candidate.notes)


# 10. AI 오류 발생 시 부분 결과 보존
def test_ai_failure_preserves_deterministic_result(intel_env, repo, monkeypatch):
    settings = (
        ImpactService().settings().model_copy(update={"external_ai_consent": True})
    )
    store_module.get_store().save_settings(settings)

    def boom(*args, **kwargs):
        raise RuntimeError("provider quota exceeded")

    monkeypatch.setattr("devfolio.core.ai_service.AIService._call", boom)
    analysis = analyze_project(
        str(repo), author_email="me@example.com", use_ai=True, force=True
    )
    assert analysis.status == "partial"
    assert analysis.ai.status == "failed"
    assert analysis.ai.error
    assert analysis.candidates
    assert any(
        "부분" in warning or "결정론적" in warning for warning in analysis.warnings
    )


# 11. 프로젝트 분석 재실행 시 변경된 내용만 분석
def test_incremental_reuses_unchanged_analysis(intel_env, repo):
    first = _analyze(repo, author_email="me@example.com")
    second = analyze_project(str(repo), author_email="me@example.com", use_ai=False)
    assert second.id == first.id
    assert second.incremental is True

    _write(repo / "docs/new.md", "# 새 문서\n\n배치 크기 조정 내용을 기록했다.\n")
    _commit(repo, "docs update")
    third = analyze_project(str(repo), author_email="me@example.com", use_ai=False)
    assert third.id != first.id
    assert third.fingerprint != first.fingerprint


# 12. 분석한 근거를 사용자 UI에서 확인 + 후보 적용
def test_ui_and_api_expose_evidence_and_apply(intel_env, repo):
    client = TestClient(create_app())
    response = client.post(
        "/api/projects/analyze",
        json={
            "project_path": str(repo),
            "author_email": "me@example.com",
            "use_ai": False,
        },
    )
    assert response.status_code == 200
    analysis = response.json()["analysis"]
    assert analysis["evidence"]
    assert analysis["candidates"]

    detail = client.get(f"/api/projects/analyses/{analysis['id']}").json()["analysis"]
    assert detail["stats"]["documents"] >= 3
    assert detail["timeline"]

    candidate = next(item for item in detail["candidates"] if "app.py" in item["title"])
    applied = client.post(
        f"/api/projects/analyses/{analysis['id']}/candidates/{candidate['id']}/apply"
    )
    assert applied.status_code == 201
    achievement = applied.json()["achievement"]
    assert achievement["source"] == "analysis"
    assert achievement["needs_review"] is True
    assert achievement["confirmed"] is False
    assert achievement["status"] == "needs_review"
    assert achievement["evidence_ids"]

    static = Path(__file__).parent.parent / "impactnote/web/static/app.js"
    script = static.read_text(encoding="utf-8")
    assert "projectsScreen" in script
    assert "근거" in script
    assert "/api/projects/analyses/" in script


def test_secret_files_are_never_indexed(intel_env, repo):
    assert is_secret_name(".env")
    assert is_secret_name(".env.production")
    assert is_secret_name("credentials.json")
    assert is_secret_name("server.pem")
    _write(repo / ".env", "OPENAI_API_KEY=sk-secret-value\n")
    _write(repo / "docs/secrets.md", "token = supersecretvalue123\n")
    analysis = _analyze(repo, author_email="me@example.com")
    assert all(not document.path.startswith(".env") for document in analysis.documents)
    assert all(
        "sk-secret-value" not in document.excerpt for document in analysis.documents
    )
    assert all(
        "supersecretvalue123" not in document.excerpt for document in analysis.documents
    )
