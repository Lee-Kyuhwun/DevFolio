# 문장별 근거 검사와 사람 승인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** evidence에 없는 숫자·기술명을 결정적 코드로 찾아 refine 피드백과 후보 선택에 쓰고, 웹에서는 사람이 채택해야만 요약이 저장되게 한다.

**Architecture:**
- 순수 함수 모듈 `claim_check.py`가 evidence를 평탄화한 인덱스와 출력 문장을 비교한다.
- `AIService`는 후보마다 근거 없는 claim을 계산해 정렬과 refine에 쓰고, 요약 초안(`SummaryDraft`)을 반환한다.
- 웹 API는 초안만 반환한다. 별도 결정 엔드포인트가 저장하고 `review_decisions.jsonl`에 기록한다.

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI, vanilla JS (`studio_v2.js`)

**Spec:** `docs/superpowers/specs/2026-10-03-claim-grounding-review-design.md`

## Global Constraints

- `claim_check.py`는 `ai_service`를 import하지 않는다(순환 import 방지). evidence는 `pydantic.BaseModel`로 받는다.
- 데이터 모델은 Pydantic `model_validate` / `model_dump`를 사용한다.
- `review_decisions.jsonl` 경로는 호출 시점에 `storage.DEVFOLIO_DATA_DIR / "review_decisions.jsonl"`로 계산한다(테스트의 patch 존중). 파일 권한은 `0o600`
- 화면 HTML은 `escapeHtml()`을 거친 값만 넣는다.
- 테스트에서 실제 AI를 호출하지 않는다.
- 커밋에 `Co-Authored-By` 줄을 넣지 않는다. 모든 커밋은 `scripts/check.sh`를 통과해야 하고, 완료 후 `git push origin main`

## Review Focus

1. 한국어 조사가 붙은 기술명("Redis를", "Kafka로") → claim은 `Redis`, `Kafka`로 추출 (Task 1 테스트)
2. 쉼표·전각·공백 차이("1,000건"과 "1000건", "４０%"와 "40 %") → 지원됨 (Task 1 테스트)
3. 영문자에 붙은 숫자("S3", "EC2", "Java17")는 숫자 claim으로 중복 추출하지 않음 (Task 1 테스트)
4. 빈 출력과 빈 evidence → 예외 없이 빈 보고서 (Task 1 테스트)
5. `accepted`/`edited`인데 `final_text`가 공백 → 422. 없는 경험 id → 404 (Task 3 테스트)

---

### Task 1: `claim_check` 모듈

**Files:**
- Create: `devfolio/core/claim_check.py`, `tests/test_claim_check.py`

**Interfaces:**
- Produces:
  - `class Claim(BaseModel): text: str; kind: Literal["number", "term"]; supported: bool; sources: list[str] = []`
  - `class SentenceCheck(BaseModel): text: str; claims: list[Claim] = []`
  - `class ClaimReport(BaseModel): sentences: list[SentenceCheck] = []`
    - `@property unsupported -> list[Claim]`: 지원되지 않는 claim. 같은 정규화 텍스트는 1회만
  - `@dataclass(frozen=True) class EvidenceIndex: entries: tuple[tuple[str, str], ...]`: (필드 경로, 정규화 텍스트)
  - `build_evidence_index(evidence: BaseModel) -> EvidenceIndex`
  - `check_claims(text: str, index: EvidenceIndex) -> ClaimReport`
  - `normalize(text: str) -> str`

- [ ] **Step 1: 실패하는 테스트 작성**

`PortfolioEvidence`의 기준 사례: `results=["배포 시간 40% 단축", "처리량 1,000건/초"]`, `tech_stack=["Spring Boot", "Redis"]`, `tasks=[EvidenceTask(name="캐시", result="Kafka 도입")]`

```python
def test_supported_number_and_term_have_sources():
    r = check_claims("- Redis로 배포 시간 40% 단축", idx)
    claims = {c.text: c for c in r.sentences[0].claims}
    assert claims["Redis"].supported and claims["Redis"].sources == ["tech_stack[1]"]
    assert claims["40%"].supported and claims["40%"].sources == ["results[0]"]

def test_invented_number_and_term_are_unsupported():
    r = check_claims("- MongoDB 도입으로 응답 속도 3배 개선", idx)
    assert {c.text for c in r.unsupported} == {"MongoDB", "3배"}

def test_number_normalization_handles_commas_fullwidth_spaces():
    assert not check_claims("처리량 1000건/초 달성.", idx).unsupported
    assert not check_claims("배포 시간 ４０ % 단축.", idx).unsupported

def test_digits_inside_latin_tokens_are_not_number_claims():
    kinds = [(c.text, c.kind) for c in check_claims("S3와 EC2 사용.", idx).sentences[0].claims]
    assert kinds == [("S3", "term"), ("EC2", "term")]

def test_nested_task_field_path():
    assert check_claims("- Kafka 도입", idx).sentences[0].claims[0].sources == ["tasks[0].result"]

def test_korean_only_sentence_has_no_claims_and_bullets_split():
    r = check_claims("- 협업 방식을 개선했다\n- Redis 적용", idx)
    assert len(r.sentences) == 2 and r.sentences[0].claims == []

def test_empty_inputs_return_empty_report():
    assert check_claims("", idx).sentences == []
    assert check_claims("- MongoDB", build_evidence_index(PortfolioEvidence(name="x"))).unsupported[0].text == "MongoDB"
```

- [ ] **Step 2: 실행해 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_claim_check.py --no-cov -q`
Expected: FAIL (`ModuleNotFoundError: devfolio.core.claim_check`)

- [ ] **Step 3: 구현**

시그니처와 테스트로 정해지지 않는 결정:
- `normalize`: `unicodedata.normalize("NFKC", s).lower()` → 숫자 사이 쉼표 제거(`(?<=\d),(?=\d)`) → 모든 공백 제거
- 평탄화: `model_dump(exclude_none=True)`를 재귀 순회. dict는 `a.b`, list는 `a[0]` 경로. 문자열 값만 인덱싱
- 숫자 claim: `(?<![A-Za-z0-9.])\d+(?:[.,]\d+)*\s*(?:%|퍼센트|배|x|ms|초|분|시간|일|주|개월|년|명|건|개|회|천|만|억|원|tps|rps|qps|gb|mb|kb)?` (IGNORECASE)
- 기술명 claim: `(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9.+#-]*[A-Za-z0-9+#]`
- 판정: `normalize(claim)`이 인덱스 항목의 정규화 텍스트에 부분 문자열로 있으면 지원. `sources`는 해당 경로 전부(인덱스 순서)
- 문장 분리: `-`, `*`, `•`로 시작하는 줄이 있으면 그 줄들만 문장으로 본다(기호 제거). 없으면 줄바꿈과 `(?<=[.!?])\s+`로 분리. 빈 문장은 버린다.

- [ ] **Step 4: 실행해 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_claim_check.py --no-cov -q`
Expected: 7 passed

- [ ] **Step 5: 커밋**

`git add devfolio/core/claim_check.py tests/test_claim_check.py && git commit -m "Add deterministic claim check against portfolio evidence"`

### Task 2: `AIService` 통합

**Files:**
- Modify: `devfolio/core/ai_service.py`
  - `ReviewedCandidate`
  - `_generate_reviewed_candidate`, `_refine_candidate`, `_candidate_sort_key`
  - `generate_with_review`의 최종 revise 프롬프트
  - `generate_project_summary`
- Modify: `devfolio/commands/ai.py:133` 부근
- Test: `tests/test_ai_service.py`(새 클래스 `TestClaimGrounding`)

**Interfaces:**
- Consumes: Task 1의 `build_evidence_index`, `check_claims`, `ClaimReport`
- Produces:
  - `ReviewedCandidate.unsupported: tuple[str, ...] = ()` (마지막 필드)
  - `AIService._unsupported_claims(evidence: PortfolioEvidence, text: str) -> tuple[str, ...]`: 예외 시 `()`와 `logger.warning`
  - `@dataclass(frozen=True) class SummaryDraft: text: str; review: ReviewResult; claims: Optional[ClaimReport]`
  - `AIService.generate_project_summary_draft(project: Project, lang: str = "ko", provider_name: Optional[str] = None, samples: Optional[int] = None) -> SummaryDraft`
  - `generate_project_summary(...)`는 `generate_project_summary_draft(...).text`를 반환

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_sort_prefers_fewer_unsupported_among_passing_candidates():
    a = ReviewedCandidate(draft="a", review=passing, score=90, is_valid=True, sample_index=1, unsupported=("3배",))
    b = ReviewedCandidate(draft="b", review=passing, score=60, is_valid=True, sample_index=2)
    assert AIService._candidate_sort_key(b) > AIService._candidate_sort_key(a)

def test_refine_prompt_lists_unsupported_claims():
    # previous = ReviewedCandidate(..., unsupported=("MongoDB", "3배"))
    # service._call_messages를 capture로 patch한 뒤 _refine_candidate 호출
    assert "근거에 없는 표현: MongoDB, 3배" in captured_user_prompt

def test_summary_draft_reports_unsupported_claims():
    # 기존 TestGenerate 방식으로 생성/심사 응답 모킹, 생성 응답에 "MongoDB" 포함 (make_project에는 없음)
    draft = service.generate_project_summary_draft(make_project(), lang="ko")
    assert "MongoDB" in {c.text for c in draft.claims.unsupported}
```

- [ ] **Step 2: 실행해 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_ai_service.py -k ClaimGrounding --no-cov -q`
Expected: FAIL (`unexpected keyword 'unsupported'`)

- [ ] **Step 3: 구현**

- 정렬 키: `(is_valid and passed, -len(unsupported), is_valid, passed, score, -len(issues))`
- refine 피드백 문구는 `_refine_candidate`의 revised prompt 끝과 `generate_with_review` 최종 revise 프롬프트(`- evidence 밖의 사실은 추가하지 말 것.` 다음 줄)에 넣는다. unsupported가 있을 때만 추가한다.
  - 정확한 문구: `근거에 없는 표현: {', '.join(unsupported)}. 삭제하거나 evidence에 있는 표현으로 바꿀 것.`
- `generate_project_summary_draft`는 `generate_with_review` 결과 텍스트에 `check_claims`를 한 번 더 실행해 `claims`를 채운다. 예외가 나면 `None`
- CLI(`commands/ai.py`)는 draft 메서드를 쓰고, 근거 없는 표현이 있으면 `console.print(f"[yellow]근거 없는 표현: {...}[/yellow]")`를 출력한다.

- [ ] **Step 4: 전체 테스트 통과 확인**

Run: `scripts/check.sh`
Expected: 모두 통과 (기존 요약 테스트 포함)

- [ ] **Step 5: 커밋**

`git commit -am "Use claim check in candidate ranking and refine feedback"`

### Task 3: 웹 API — 초안 반환과 사람 결정

**Files:**
- Create: `devfolio/core/review_log.py`
- Modify: `devfolio/web/routes/api.py`
  - `generate_project_summary`(:1002), `generate_experience_summary`(:1043), `generate_draft_summary`(:971)
  - 결정 엔드포인트 2개 추가
- Test: `tests/test_web_api.py`

**Interfaces:**
- Consumes: Task 2의 `SummaryDraft`, `generate_project_summary_draft`. Task 1의 `build_evidence_index`, `check_claims`
- Produces:
  - `append_review_decision(*, project_id: str, mode: str, action: str, draft_text: str, final_text: str, unsupported_in_draft: list[str], unsupported_in_final: list[str]) -> None` (`review_log.py`, 실패 시 warning만)
  - `class SummaryDecisionRequest(BaseModel): action: Literal["accepted", "edited", "discarded"]; draft_text: str; final_text: str = ""`
    - accepted/edited에서 `final_text.strip()`이 비면 ValueError → 422
  - 생성 응답: `{"status": "ok", "summary_draft": {"text": str, "claims": dict | None, "review_scores": dict[str, int]}}`
  - `POST /api/experiences/{project_id}/summary/decision` → `{"status": "ok", "experience": ...}`
  - `POST /api/projects/{project_id}/summary/decision` → `{"status": "ok", "project": ...}`
  - `/api/draft/generate-summary`는 기존 응답에 `"claims"` 키만 추가

- [ ] **Step 1: 실패하는 테스트 작성** (`patch("devfolio.web.routes.api.AIService")`로 `generate_project_summary_draft` 반환값 지정, 프로젝트는 `client.post("/api/experiences", ...)`로 생성)

```python
def test_generate_summary_returns_draft_without_saving(client, web_store): ...
    assert resp.json()["summary_draft"]["text"] == "초안"
    assert client.get(f"/api/experiences").json()  # 해당 경험의 summary가 생성 전 값 그대로

def test_summary_decision_edited_saves_and_logs(client, web_store): ...
    assert saved_summary == "사람이 고친 요약"
    rows = (web_store / "data" / "review_decisions.jsonl").read_text().splitlines()
    assert json.loads(rows[0])["action"] == "edited"
    assert oct((web_store / "data" / "review_decisions.jsonl").stat().st_mode & 0o777) == "0o600"

def test_summary_decision_discarded_does_not_save(client, web_store): ...

def test_summary_decision_rejects_blank_final_text(client, web_store):
    assert resp.status_code == 422

def test_summary_decision_unknown_experience_404(client, web_store):
    assert resp.status_code == 404
```

- [ ] **Step 2: 실행해 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_web_api.py -k summary --no-cov -q`
Expected: FAIL (`KeyError: 'summary_draft'`)

- [ ] **Step 3: 구현**

결정 엔드포인트는 다음 순서로 처리한다.
1. 프로젝트 조회(없으면 404)
2. `AIService(cfg).build_evidence(project=project)`로 인덱스 생성
3. `draft_text`와 `final_text` 각각의 unsupported 목록 계산
4. accepted/edited면 `pm.save_project_summary`
5. `append_review_decision`

- [ ] **Step 4: 통과 확인**

Run: `scripts/check.sh`
Expected: 모두 통과

- [ ] **Step 5: 커밋**

`git commit -am "Return summary drafts and save only on human decision"` (`review_log.py`는 `git add` 먼저)

### Task 4: 검토 패널 화면

**Files:**
- Modify: `devfolio/web/static/studio_v2.js`
  - `generateSummaryForForm`(:1191)
  - 액션 switch(:803 부근)
  - 경험 폼 렌더러의 요약 textarea(:2138) 바로 위
- Modify: `devfolio/web/static/studio_v2.css`

**Interfaces:**
- Consumes: Task 3의 응답 형태
- Produces:
  - 상태: `state.ui.summaryReview = { target: "experience" | "draft", draftText, claims }` 또는 `null`
  - `renderSummaryReview(review) -> string`
  - 액션: `summary-review-apply`, `summary-review-discard`
  - textarea name: `summary-review-text`

- [ ] **Step 1: 구현**

- 생성 후 `summaryReview`를 설정하고 폼 요약은 바꾸지 않는다.
- 패널 구성:
  - 문장별 줄. 근거 없는 claim은 `<mark class="claim-unsupported" title="근거 없음">`, 출처는 `<span class="chip">`
  - 상단에 "근거 없는 표현 N개"
  - 편집 textarea, [적용], [버리기]
- 적용:
  - experience → `/summary/decision`에 `action = text === draftText ? "accepted" : "edited"`로 보내고, 응답으로 폼과 목록을 갱신
  - draft → `state.experienceForm.summary = text`
- 버리기: experience면 `discarded`를 전송한다. 두 경우 모두 `summaryReview = null`
- `claims`가 `null`이면 "근거 검사 불가"를 표시한다.

- [ ] **Step 2: 브라우저 확인**

- AI 호출이 발생하므로 실행 전에 사용자 확인을 받는다(무료 pollinations).
- `.venv/bin/devfolio serve`로 실행한 뒤 경험 하나에서 [요약 생성]을 누르고, 패널·강조·적용·버리기를 확인한다.
- 근거 없는 표현이 보이는 화면을 `docs/images/claim-review-panel.png`로 저장한다.

Expected:
- 적용 전에는 요약이 저장되지 않는다.
- 적용 후 `review_decisions.jsonl`에 1줄이 추가된다.

- [ ] **Step 3: 커밋·푸시와 문서 갱신**

- `docs/ai-collaboration.md` 제품 Loop 표의 "결정적 코드 (설계 중)"을 "결정적 코드 (`claim_check.py`)"로 바꾼다.
- 설계 문서 상태를 "구현 완료"로 바꾼다.

```bash
git add devfolio/web/static docs/images docs/ai-collaboration.md docs/superpowers/specs/2026-10-03-claim-grounding-review-design.md
git commit -m "Add summary review panel with claim highlights"
git push origin main
```
