"""프로젝트 인텔리전스 엔진 회귀 테스트.

실제 임시 Git 저장소를 만들어 문서·코드·커밋 전후·측정값을 검증한다.
필수 12개 시나리오(Phase 12)를 고정한다.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from impactnote.core import store as store_module
from impactnote.core.intel import analyze_project
from impactnote.core.intel import ai_stage
from impactnote.core.intel.discovery import is_secret_name
from impactnote.core.intel.models import DocRecord, ProjectAnalysis
from impactnote.core.models import Settings
from impactnote.core.report import build_content
from impactnote.core.service import ImpactService
from impactnote.web.app import create_app
from devfolio.core.ai_service import AIService


@pytest.fixture()
def intel_env(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPACTNOTE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("IMPACTNOTE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("IMPACTNOTE_LEGACY_DATA_DIR", str(tmp_path / "legacy-data"))
    monkeypatch.setenv("IMPACTNOTE_LEGACY_CONFIG_DIR", str(tmp_path / "legacy-config"))
    monkeypatch.setenv("IMPACTNOTE_ANALYZE_ROOTS", str(tmp_path))
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
def test_candidate_edit_validation_merge_and_existing_activity_link(intel_env, repo):
    analysis = _analyze(repo, author_email="me@example.com")
    source, target = analysis.candidates[0], analysis.candidates[1]
    service = ImpactService()

    updated = service.update_project_candidate(
        analysis.id,
        source.id,
        {"title": "수정한 후보", "status": "needs_validation"},
    )
    assert updated.candidates[0].title == "수정한 후보"
    assert updated.candidates[0].status == "needs_validation"

    merged = service.merge_project_candidates(analysis.id, source.id, target.id)
    merged_target = next(item for item in merged.candidates if item.id == target.id)
    merged_source = next(item for item in merged.candidates if item.id == source.id)
    assert merged_source.status == "dismissed"
    assert set(source.evidence_ids).issubset(set(merged_target.evidence_ids))
    assert any("병합" in note for note in merged_target.notes)

    activity = service.create_activity(
        {"title": "기존 업무 기록", "date": "2026-11-15"}
    )
    achievement = service.apply_project_candidate(
        analysis.id, target.id, activity_id=activity.id
    )
    assert achievement.activity_ids == [activity.id]
    assert service.activity(activity.id).evidence_ids


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


# 13. 삭제된 파일의 과거 변경을 현재 성과로 만들지 않는다.
def test_deleted_code_is_not_a_current_candidate(intel_env, tmp_path):
    root = _init(tmp_path / "deleted-project")
    _write(root / "README.md", "# app\n\napp.py 배치 기능\n")
    _write(root / "app.py", "def run():\n    return [x for x in range(3)]\n")
    _commit(root, "initial")
    _write(root / "app.py", "def run():\n    return list(range(3))\n")
    _commit(root, "update")
    (root / "app.py").unlink()
    _commit(root, "remove app")

    analysis = _analyze(root)
    assert not any("app.py" in candidate.title for candidate in analysis.candidates)
    assert not any(item.path == "app.py" for item in analysis.code_files)


# 14. Git 이력을 읽지 못하면 완료가 아니라 partial 로 표시한다.
def test_git_failure_is_partial_with_warning(intel_env, tmp_path):
    root = _init(tmp_path / "broken-git")
    _write(root / "README.md", "# broken\n\n내용\n")
    _commit(root, "initial")
    (root / ".git" / "HEAD").write_text("not a git file\n", encoding="utf-8")

    analysis = _analyze(root)
    assert analysis.status == "partial"
    assert len(analysis.commits) == 0
    assert any("Git 이력" in warning for warning in analysis.warnings)


# 15. 목표/계획 문구는 측정값으로 승격하지 않는다.
def test_goal_sentence_is_not_a_verified_measurement(intel_env, tmp_path):
    root = _init(tmp_path / "goal-project")
    _write(
        root / "docs/performance.md", "# 성능 목표\n\n목표: 응답 시간 1200ms → 200ms\n"
    )
    _write(root / "app.py", "def run():\n    return 1\n")
    _commit(root, "docs")

    analysis = _analyze(root)
    goal = next(item for item in analysis.measurements if item.before == "1200ms")
    assert goal.verified is False
    assert "목표" in goal.note
    assert not any(
        candidate.measurement_id == goal.id for candidate in analysis.candidates
    )


# 16. 측정 신호가 있는 문서만 검증된 측정으로 인정한다.
def test_measured_document_is_still_verified(intel_env, tmp_path):
    root = _init(tmp_path / "measured-project")
    _write(
        root / "docs/performance.md",
        "# 성능 측정\n\n부하 테스트 10회 평균: 1200ms → 400ms\n",
    )
    _write(root / "app.py", "def run():\n    return 1\n")
    _commit(root, "measure")

    analysis = _analyze(root)
    measured = next(item for item in analysis.measurements if item.before == "1200ms")
    assert measured.verified is True
    assert any(
        candidate.measurement_id == measured.id for candidate in analysis.candidates
    )


# 17. 작업 공간 밖을 가리키는 문서 symlink 는 읽지 않는다.
def test_symlink_outside_project_is_not_read(intel_env, tmp_path):
    outside = tmp_path / "outside-secret.md"
    _write(outside, "DATABASE_PASSWORD=VERY_SECRET_VALUE_123\n")
    root = _init(tmp_path / "symlink-project")
    _write(root / "app.py", "x = 1\n")
    (root / "docs").mkdir()
    (root / "docs" / "leak.md").symlink_to(outside)
    _commit(root, "initial")

    analysis = _analyze(root)
    assert not any(item.path == "docs/leak.md" for item in analysis.documents)
    assert all(
        "VERY_SECRET_VALUE_123" not in item.excerpt for item in analysis.documents
    )


# 18. API 는 허용된 작업 공간 밖의 프로젝트 경로를 거부한다.
def test_api_rejects_project_outside_allowed_roots(intel_env, tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    client = TestClient(create_app())
    response = client.post(
        "/api/projects/analyze", json={"project_path": str(outside), "use_ai": False}
    )
    assert response.status_code == 400
    assert "작업 공간" in response.json()["detail"]


# 19. AI 가 인용하지 않은 문서의 수치를 problem 에 남기지 않는다.
def test_ai_sanitizes_problem_and_unattributed_numbers(intel_env, monkeypatch):
    analysis = ProjectAnalysis(
        project_path="/tmp/ai-project",
        project_name="ai-project",
        documents=[
            DocRecord(
                id="d1",
                path="docs/a.md",
                title="a",
                kind="design",
                excerpt="cache added",
            ),
            DocRecord(
                id="d2",
                path="docs/b.md",
                title="b",
                kind="report",
                excerpt="latency 50% faster",
            ),
        ],
    )
    citations, refs = ai_stage._citation_bundle(analysis)
    cited = next(key for key, value in refs.items() if value.path == "docs/a.md")
    payload = {
        "findings": [],
        "candidates": [
            {
                "title": "AI candidate 50%",
                "problem": "latency 50% improved",
                "action": "cache",
                "result": "50% faster",
                "quality": "SUPPORTED_INFERENCE",
                "citations": [cited],
            }
        ],
        "notes": [],
    }

    class FakeStore:
        def settings(self):
            return Settings(external_ai_consent=True)

        def put(self, *args, **kwargs):
            return None

    monkeypatch.setattr(AIService, "_call", lambda *args, **kwargs: json.dumps(payload))
    monkeypatch.setattr(
        ai_stage, "_citation_bundle", lambda _analysis: (citations, refs)
    )
    result = ai_stage.enrich_with_ai(analysis, store=FakeStore())

    assert result.ai.status == "completed"
    candidate = result.candidates[0]
    assert "50%" not in candidate.problem
    assert "[확인 필요]" in candidate.problem
    assert "50%" not in candidate.title
    assert "50%" not in candidate.result
    assert candidate.quality == "HYPOTHESIS"


# 20. 리버트된 변경은 현재 성과 후보로 남기지 않는다.
def test_reverted_change_is_not_a_current_candidate(intel_env, tmp_path):
    root = _init(tmp_path / "reverted-project")
    _write(root / "app.py", "def get_user(uid):\n    return db_query(uid)\n")
    _commit(root, "initial")
    _write(
        root / "app.py",
        "CACHE = {}\ndef get_user(uid):\n"
        "    if uid not in CACHE:\n        CACHE[uid] = db_query(uid)\n"
        "    return CACHE[uid]\n",
    )
    reverted = _commit(root, "performance cache")
    _git(root, "revert", "--no-edit", reverted)
    _write(root / "docs/design.md", "# 설계\n\n캐시 구조를 사용한다.\n")
    _commit(root, "docs")

    analysis = _analyze(root)
    assert not any("app.py" in candidate.title for candidate in analysis.candidates)
    assert any("리버트된 변경" in warning for warning in analysis.warnings)
    assert all(step.sha != reverted for step in analysis.timeline)


# 21. Git rename 이후에도 현재 경로의 이력을 추적한다.
def test_rename_is_normalized_to_current_path(intel_env, tmp_path):
    root = _init(tmp_path / "rename-project")
    _write(root / "src/a.py", "def run():\n    return 1\n")
    _commit(root, "initial")
    _git(root, "mv", "src/a.py", "src/b.py")
    _commit(root, "rename")

    analysis = _analyze(root)
    assert any(item.path == "src/b.py" for item in analysis.code_files)
    assert any("src/b.py" in commit.files for commit in analysis.commits)
    assert all("{" not in path for commit in analysis.commits for path in commit.files)


# 22. PDF 문서도 실제 텍스트를 추출한다.
def test_pdf_document_text_is_extracted(intel_env, tmp_path):
    root = _init(tmp_path / "pdf-project")
    _write(root / "app.py", "x = 1\n")
    stream = b"BT /F1 12 Tf 72 720 Td (PDF evidence) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    (root / "docs").mkdir()
    (root / "docs" / "report.pdf").write_bytes(output)
    _commit(root, "docs")

    analysis = _analyze(root)
    pdf = next(item for item in analysis.documents if item.path == "docs/report.pdf")
    assert "PDF evidence" in pdf.excerpt


# 23. 미확정 분석 성과는 월간 보고서 본문에 들어가지 않는다.
def test_unconfirmed_analysis_achievement_is_excluded_from_report_body(intel_env):
    service = ImpactService()
    activity = service.create_activity(
        {
            "title": "UNCONFIRMED_TITLE_X",
            "description": "unconfirmed work",
            "date": date.today().isoformat(),
            "source": "analysis",
        }
    )
    achievement = service.create_achievement(
        {
            "title": "UNCONFIRMED_TITLE_X",
            "activity_ids": [activity.id],
            "problem": "p",
            "action": "a",
            "result": "r",
            "period_start": date.today().isoformat(),
            "period_end": date.today().isoformat(),
            "source": "analysis",
            "confirmed": False,
            "needs_review": True,
        }
    )
    content, meta = build_content(service, template="monthly", period_kind="month")
    body = content.split("## 근거 및 확인 상태")[0]
    assert "UNCONFIRMED_TITLE_X" not in body
    assert "UNCONFIRMED_TITLE_X" in content
    assert achievement.id in meta["pending_achievement_ids"]
    assert achievement.id not in meta["achievement_ids"]


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


# 22. AI 프로젝트 분석 후보의 근거 없는 정성 효과는 HYPOTHESIS 로 낮아진다.
def test_ai_candidate_without_effect_evidence_is_demoted(monkeypatch):
    from impactnote.core.models import Settings

    analysis = ProjectAnalysis(
        project_path="/tmp/ai-effect-project",
        project_name="ai-effect-project",
        documents=[
            DocRecord(
                id="d1",
                path="docs/a.md",
                title="a",
                kind="design",
                excerpt="cache added",
            ),
            DocRecord(
                id="d2",
                path="docs/b.md",
                title="b",
                kind="report",
                excerpt="load test executed",
            ),
        ],
    )
    citations, refs = ai_stage._citation_bundle(analysis)
    cited = [
        key for key, value in refs.items() if value.path in {"docs/a.md", "docs/b.md"}
    ]
    payload = {
        "findings": [],
        "candidates": [
            {
                "title": "Cache candidate",
                "problem": "latency",
                "action": "cache added",
                "result": "서비스 안정성을 크게 향상시켰다.",
                "quality": "SUPPORTED_INFERENCE",
                "citations": cited,
            }
        ],
        "notes": [],
    }

    class FakeStore:
        def settings(self):
            return Settings(external_ai_consent=True)

        def put(self, *args, **kwargs):
            return None

    monkeypatch.setattr(AIService, "_call", lambda *args, **kwargs: json.dumps(payload))
    monkeypatch.setattr(
        ai_stage, "_citation_bundle", lambda _analysis: (citations, refs)
    )
    result = ai_stage.enrich_with_ai(analysis, store=FakeStore())

    assert result.ai.status == "completed"
    candidate = result.candidates[0]
    assert candidate.result == ""
    assert candidate.quality == "HYPOTHESIS"
