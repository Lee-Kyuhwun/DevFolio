# AI 심사 신뢰도 측정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 출력 20개(사례 5개 × 전략 4종)에 대해 심사 모델·결정적 검사기·사람의 판정을 비교하고, 사전에 정한 규칙으로 항목별 "자동 / 사람 필수"를 결정한다.

**Architecture:**
- `evals/` 개발용 스크립트 3개(run → label → report)와 순수 계산 모듈 `metrics.py`로 구성한다.
- 생성은 `AIService`를 그대로 쓰고, 하위 클래스로 호출 수와 지연 시간을 센다.

**Tech Stack:** Python 3.11+, ruamel.yaml, Pydantic v2, pytest

**Spec:** `docs/superpowers/specs/2026-10-03-judge-reliability-eval-design.md`
**Depends on:** `docs/superpowers/plans/2026-10-03-claim-grounding-review.md` Task 1~2 (`check_claims`, `ReviewedCandidate.unsupported`)

> **측정 편향 주의:** `generate_with_review`는 최종 심사에 불합격하면 예외를 던진다. 이를 통해 측정하면 심사 모델이 불합격시킨 출력이 결과에서 빠져 "pass" 일치율이 치우친다. 그래서 Task 2에서 후보 선택 부분을 분리하고, 최종 판정 전의 선택 후보를 기록한다.

## Global Constraints

- 판정 규칙(사전 등록): 일치율 `>= 0.80` → `"auto"`, 미만 → `"human_required"`, 계산 불가 → `"undetermined"`
  - factuality 놓친 비율 `> 0.10` → `"human_required"`
- 전략 설정:
  - `single`(samples=1, refinement_budget=0)
  - `best_of_n`(samples=3, refinement_budget=0)
  - `s1_refine`(samples=1, refinement_budget=2)
  - `hybrid`(samples=3, refinement_budget=1)
- `evals/cases/`, `evals/runs/`는 gitignore. 공개 예시는 `evals/examples/sample_case.yaml` 1개
- 실제 AI 실행 전에는 예상 최대 호출 수를 출력하고 `y` 입력을 받는다(`--yes`로 생략). 기본 provider는 `pollinations`
- YAML은 `ruamel.yaml`로 읽고 `Project.model_validate`로 검증한다.
- `scripts/check.sh`와 CI lint 대상에 `evals/`를 추가한다.
- 커밋에 `Co-Authored-By` 줄을 넣지 않는다. 완료 후 `git push origin main`

## Review Focus

1. 모든 라벨이 같은 값이라 kappa 분모가 0 → `None`, 보고서에 "계산 불가" (Task 1 테스트)
2. 일부만 라벨링된 상태에서 보고서 생성 → 라벨된 항목만 쓰고 n을 표시 (Task 4 테스트)
3. 설정이 다른 전략으로 바뀌어 실행됨(예: hybrid → single) → `resolved_strategy` 기록, 보고서에 경고 (Task 2·4 테스트)
4. 사례 하나의 AI 호출 실패 → `error` 행을 기록하고 나머지 계속 진행 (Task 2 테스트)
5. 라벨링 중단 후 재실행 → 이미 라벨한 항목은 건너뜀 (Task 3 테스트)

---

### Task 1: 통계 함수

**Files:**
- Create: `evals/__init__.py`, `evals/metrics.py`, `tests/test_evals_metrics.py`
- Modify: `scripts/check.sh`, `.github/workflows/ci.yml` (lint 대상에 `evals/`), `.gitignore` (`evals/cases/`, `evals/runs/`)

**Interfaces:**
- Produces:
  - `agreement(pairs: list[tuple[bool, bool]]) -> float | None`
  - `cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None`: 기대 일치도가 1이면 None
  - `miss_rate(truth: list[bool], predicted: list[bool]) -> float | None`: truth가 True인 것 중 predicted가 False인 비율
  - `recall_precision(truth: list[bool], predicted: list[bool]) -> tuple[float | None, float | None]`
  - `decide(agreements: dict[str, float | None], factuality_miss: float | None) -> dict[str, str]`

- [ ] **Step 1: 실패하는 테스트**

```python
def test_agreement_and_kappa():
    pairs = [(True, True), (True, False), (False, False), (False, False)]
    assert agreement(pairs) == 0.75
    assert cohen_kappa(pairs) == pytest.approx(0.5)

def test_kappa_undefined_when_all_same():
    assert cohen_kappa([(True, True), (True, True)]) is None

def test_miss_rate_and_recall_precision():
    assert miss_rate([True, True, False], [True, False, False]) == 0.5
    assert recall_precision([True, True, False], [True, False, True]) == (0.5, 0.5)

def test_decide_applies_preregistered_thresholds():
    assert decide({"naturalness": 0.80, "pass": 0.79, "factuality": None}, factuality_miss=0.11) == {
        "naturalness": "auto", "pass": "human_required", "factuality": "human_required"}
    assert decide({"factuality": 0.9}, factuality_miss=None)["factuality"] == "auto"
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_evals_metrics.py --no-cov -q` / Expected: FAIL (`ModuleNotFoundError: evals`)
- [ ] **Step 3: 구현** — `decide`의 factuality 규칙: 일치율 판정 결과와 놓친 비율 판정 중 하나라도 `human_required`면 `human_required`
- [ ] **Step 4: 통과 확인** — Run: `scripts/check.sh` / Expected: 모두 통과
- [ ] **Step 5: 커밋** — `git add evals tests/test_evals_metrics.py scripts/check.sh .github/workflows/ci.yml .gitignore && git commit -m "Add evaluation metrics with preregistered decision rule"`

### Task 2: 생성 실행기 `evals/run.py`

**Files:**
- Create: `evals/run.py`, `evals/examples/sample_case.yaml`, `tests/test_evals_run.py`
- Modify: `devfolio/core/ai_service.py` (`generate_with_review`에서 후보 선택 부분 추출)

**Interfaces:**
- Consumes: `AIService.build_evidence(project=...)`, `Config.reasoning`, `ReviewedCandidate.unsupported`
- Produces:
  - `AIService._select_best_candidate(*, evidence: PortfolioEvidence, profile: GenerationProfile, provider_name: Optional[str], samples: Optional[int]) -> tuple[ReviewedCandidate, ReasoningPlan]`
    - `generate_with_review`의 plan 결정과 전략 실행(`_run_*`) 부분을 그대로 옮긴다. `generate_with_review`는 이 메서드를 호출하도록 바꾸고 동작은 같다(기존 테스트로 확인).
  - 측정용 profile: `GenerationProfile(mode="project_summary", language="ko", max_tokens=2800)`
  - 행 값: `text=candidate.draft`, `judge_scores=candidate.review.scores`, `judge_passed=candidate.review.passed`, `unsupported=list(candidate.unsupported)`, `resolved_strategy=plan.strategy`
  - `STRATEGIES: dict[str, dict[str, int]]` (Global Constraints의 값)
  - `load_cases(directory: Path) -> list[tuple[str, Project]]` (`case_id` = 파일 stem)
  - `class CountingAIService(AIService)`: `_call_messages` override. `self.calls: int`, `self.latency_ms: int` 누적
  - `estimate_max_calls(n_cases: int, strategies: list[str]) -> int`
    - 전략별 상한: single 4, best_of_n 8, s1_refine 8, hybrid 14
  - `run_eval(cases, strategies, config: Config, provider: str, out_dir: Path) -> Path`: `outputs.jsonl` 경로 반환
  - 출력 행: `{output_id: f"{case_id}:{strategy}", case_id, strategy, resolved_strategy, text, judge_scores, judge_passed, unsupported: list[str], calls, latency_ms, error: str | None}`
  - CLI: `python -m evals.run --cases DIR --strategies a,b --provider NAME [--yes]` → `evals/runs/<YYYYMMDD-HHMMSS>/`

- [ ] **Step 1: 실패하는 테스트**

`AIService._call_messages`를 patch해 생성·심사 응답을 돌려준다.

```python
def test_run_eval_writes_row_per_case_and_strategy(tmp_path): ...
    assert [r["output_id"] for r in rows] == ["sample_case:single", "sample_case:best_of_n"]
    assert rows[1]["resolved_strategy"] == "best_of_n" and rows[1]["calls"] >= 2

def test_failed_case_records_error_and_continues(tmp_path): ...
    assert rows[0]["error"] and rows[1]["error"] is None

def test_judge_rejected_candidate_is_still_recorded(tmp_path):
    # 심사 응답을 pass=false, factuality=2로 모킹
    assert rows[0]["judge_passed"] is False and rows[0]["error"] is None and rows[0]["text"]

def test_estimate_max_calls():
    assert estimate_max_calls(5, list(STRATEGIES)) == 170
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/python -m pytest tests/test_evals_run.py --no-cov -q` / Expected: FAIL
- [ ] **Step 3: 구현** — 전략마다 `config.model_copy(deep=True)`로 reasoning을 덮어쓴다. 예외는 `DevfolioError`만 잡아 `error`에 기록한다. sample_case는 가상의 프로젝트(실제 회사명·수치 없음)로 작성한다.
- [ ] **Step 4: 통과 확인** — Run: `scripts/check.sh` / Expected: 모두 통과
- [ ] **Step 5: 커밋** — `git add evals tests/test_evals_run.py && git commit -m "Add evaluation runner for generation strategies"`

### Task 3: 블라인드 라벨링 `evals/label.py`

**Files:**
- Create: `evals/label.py`, `tests/test_evals_label.py`

**Interfaces:**
- Consumes: Task 2의 출력 행
- Produces:
  - `pending_items(outputs: list[dict], labeled_ids: set[str], seed: str) -> list[dict]`: error 행 제외, 라벨된 항목 제외, `random.Random(seed)`로 섞음
  - `label_one(item: dict, evidence_summary: str, ask: Callable[[str], str]) -> dict`
    - 반환: `{output_id, has_unsupported: bool, unsupported_text: str, naturalness: int, usability: "as_is" | "needs_edit" | "unusable"}`
  - 화면에 보이는 것: evidence 요약과 `text`만. 전략과 심사 점수는 보이지 않는다.
  - CLI: `python -m evals.label <run_dir>` → `labels.jsonl`에 한 줄씩 append(중단 후 재개 가능)

- [ ] **Step 1: 실패하는 테스트**

```python
def test_pending_items_skips_labeled_and_errors_and_is_stable(): ...
    assert [i["output_id"] for i in pending_items(rows, {"a:single"}, "run1")] == expected_order
    assert pending_items(rows, set(), "run1") == pending_items(rows, set(), "run1")

def test_label_one_hides_strategy_and_scores():
    shown = []
    answers = iter(["y", "3배", "4", "2"])
    label = label_one(item, "요약", lambda prompt: shown.append(prompt) or next(answers))
    assert label == {"output_id": "a:hybrid", "has_unsupported": True, "unsupported_text": "3배",
                     "naturalness": 4, "usability": "needs_edit"}
    assert not any("hybrid" in p or "factuality" in p for p in shown)
```

- [ ] **Step 2~4**: 실패 확인 → 구현(잘못된 입력은 같은 질문을 다시 묻는다) → `scripts/check.sh` 통과
- [ ] **Step 5: 커밋** — `git commit -m "Add blind labeling script for evaluation outputs"`

### Task 4: 보고서 `evals/report.py`

**Files:**
- Create: `evals/report.py`, `tests/test_evals_report.py`

**Interfaces:**
- Consumes: Task 1의 함수 전부, Task 2·3의 행
- Produces:
  - `build_report(outputs: list[dict], labels: list[dict]) -> str` (Markdown)
  - CLI: `python -m evals.report <run_dir>` → `<run_dir>/report.md`

비교 매핑:
- factuality: 사람 `has_unsupported` ↔ 심사 `judge_scores["factuality"] < 3`
- checker: 사람 `has_unsupported` ↔ `len(unsupported) > 0`
- naturalness: 사람 `naturalness >= 4` ↔ 심사 `judge_scores["naturalness"] >= 4`
- pass: 사람 `usability == "as_is"` ↔ `judge_passed`

보고서 섹션:
1. 표본(라벨 n / 전체 n)
2. 항목별 일치율·kappa
3. 심사 놓친 비율, 검사기 재현율·정밀도
4. 판정 결과(`decide`)
5. 전략별 평균 호출 수·지연·근거 없는 표현 비율·"그대로 사용" 비율
6. 경고(`strategy != resolved_strategy`, 라벨 누락)

- [ ] **Step 1: 실패하는 테스트**

```python
def test_report_uses_only_labeled_rows_and_shows_n(): ...
    assert "라벨 3 / 전체 4" in md

def test_report_applies_decision_and_flags_resolved_strategy(): ...
    assert "| pass | human_required |" in md
    assert "hybrid → single" in md
```

- [ ] **Step 2~4**: 실패 확인 → 구현 → `scripts/check.sh` 통과
- [ ] **Step 5: 커밋·푸시** — `git commit -m "Add evaluation report with decision table" && git push origin main`

### Task 5: 실제 측정과 결과 반영 (사람 참여)

**Files:**
- Modify: `docs/ai-collaboration.md` (측정 결과 섹션, 역할 분담 표)
- Modify: 설계 문서 11절, 상태

- [ ] **Step 1: 사람이 사례 5개 작성** — `evals/cases/*.yaml`(커밋 안 함). 형식은 `evals/examples/sample_case.yaml`
- [ ] **Step 2: 실행 승인 후 실행** — Run: `.venv/bin/python -m evals.run --cases evals/cases --strategies single,best_of_n,s1_refine,hybrid --provider pollinations` / Expected: 예상 호출 수 표시 → 사용자 `y` → `outputs.jsonl`에 20행
- [ ] **Step 3: 사람이 라벨링** — Run: `.venv/bin/python -m evals.label evals/runs/<run_id>` / Expected: `labels.jsonl` 20행
- [ ] **Step 4: 보고서와 반영** — Run: `.venv/bin/python -m evals.report evals/runs/<run_id>`
  - 실측 수치와 판정 결과만 `docs/ai-collaboration.md`에 옮긴다. 원문은 옮기지 않는다.
  - "사람 필수"로 판정된 항목은 검토 패널에 안내 문구로 반영한다.
  - 커밋·푸시
