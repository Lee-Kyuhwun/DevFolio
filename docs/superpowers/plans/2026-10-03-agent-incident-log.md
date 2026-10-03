# 에이전트 실수 기록부와 회귀 테스트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실서비스에서 사람이 찾은 장애 8건을 기록부로 남기고, 그중 6건을 회귀 테스트로 고정한다. 테스트는 조치를 되돌리면 실패해야 한다.

**Architecture:** 테스트는 기존 `tests/test_ai_service.py` 방식대로 `litellm`을 `MagicMock`으로 대체해 `AIService`의 실제 분기 코드를 실행한다. 기록부는 git 커밋 diff를 근거로 작성한다.

**Tech Stack:** pytest, unittest.mock, pkgutil

**Spec:** `docs/superpowers/specs/2026-10-03-agent-incident-log-design.md`

## Global Constraints

- 실제 AI API를 호출하지 않는다. 사용자 데이터 폴더에 쓰지 않도록 `devfolio.core.ai_service._write_ai_log`를 patch한다.
- `_set_env_key`가 `os.environ`을 바꾸므로 `patch.dict("os.environ", {}, clear=False)`로 감싼다.
- 테스트 이름은 `test_incNN_`으로 시작한다.
- 커밋 메시지에 `Co-Authored-By` 줄을 넣지 않는다(`CLAUDE.md`). 완료 후 `git push origin main`
- 모든 커밋은 `scripts/check.sh`(pre-commit)를 통과해야 한다.

## Review Focus

1. 테스트가 실제로 대기하면 안 된다 → `time.sleep`을 patch하고 INC-01·INC-02에서 `sleep.assert_not_called()`
2. 한글 보존 → INC-04에서 한글과 영문 기술명이 그대로 남는지 단언
3. INC-03은 코드펜스 없이 설명문 사이에 낀 JSON을 반드시 포함 → 그래야 중괄호 블록 추출을 되돌렸을 때 실패한다
4. INC-05는 provider 체인 수준(`_call_messages`)에서 검증 → 다음 provider의 응답이 반환되어야 한다
5. INC-06은 테스트가 import하지 않는 모듈(`devfolio.web.main`)까지 포함하는지 단언

---

### Task 1: 장애별 회귀 테스트

**Files:**
- Create: `tests/test_incident_regressions.py`

**Interfaces:**
- Consumes:
  - `AIService._call_single_provider(litellm, provider, messages, temperature, max_tokens, json_mode) -> str`
  - `AIService._call_messages(messages, provider_name=None, ...) -> str`
  - `AIService._extract_json(raw: str) -> dict` (staticmethod)
  - `devfolio.core.ai_service._strip_foreign_chars(text: str) -> str`
  - `AIService._runtime_model_candidates(provider) -> list[str]`
- Produces: 테스트 이름 6개. Task 2의 기록부가 이 이름을 인용한다.

공통 헬퍼(파일 상단):
- `_response(text: str)`: `SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])`
- `_error(class_name: str, message: str) -> Exception`: `type(class_name, (Exception,), {})(message)`
- `make_config`는 `tests/test_ai_service.py`에서 import한다.

- [ ] **Step 1: 테스트 6개 작성**

```python
def test_inc01_quota_zero_fails_without_retry():
    # provider "gemini", candidates patch -> ["gemini-2.5-flash"]
    # completion.side_effect = _error("RateLimitError",
    #   "Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 0")
    # with pytest.raises(DevfolioAIError) as exc: service._call_single_provider(...)
    assert fake_litellm.completion.call_count == 1
    assert "결제" in exc.value.hint
    sleep.assert_not_called()

def test_inc02_not_found_model_moves_to_next_candidate_without_wait():
    # candidates patch -> ["retired-model", "current-model"]
    # side_effect = [_error("NotFoundError", "model not found"), _response("정상 응답")]
    assert result == "정상 응답"
    assert "current-model" in fake_litellm.completion.call_args_list[1].kwargs["model"]
    sleep.assert_not_called()

def test_inc03_extracts_json_wrapped_in_fence_or_prose():
    assert AIService._extract_json('네, 아래와 같습니다.\n```json\n{"a": 1}\n```\n참고하세요.') == {"a": 1}
    assert AIService._extract_json('요청하신 결과입니다: {"a": 1} 이상입니다.') == {"a": 1}

def test_inc04_strips_japanese_and_chinese_but_keeps_korean():
    out = _strip_foreign_chars("Redis 캐시를 導入して 응답 시간을 단축했습니다")
    assert not any(0x3040 <= ord(c) <= 0x30FF or 0x4E00 <= ord(c) <= 0x9FFF for c in out)
    assert "Redis" in out and "응답 시간을 단축했습니다" in out

def test_inc05_empty_response_falls_back_to_next_provider():
    # config: default "anthropic" + second provider "openai"(model "gpt-4o"), 두 provider 모두 candidates 1개로 patch
    # side_effect = [_response("   "), _response("다음 provider 응답")]
    assert service._call_messages([{"role": "user", "content": "x"}]) == "다음 provider 응답"
    assert "gpt-4o" in fake_litellm.completion.call_args_list[1].kwargs["model"]

def test_inc06_every_devfolio_module_imports():
    names = [m.name for m in pkgutil.walk_packages(devfolio.__path__, "devfolio.")]
    assert "devfolio.web.main" in names
    failures = {}
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as e:
            failures[name] = f"{type(e).__name__}: {e}"
    assert failures == {}
```

INC-01·02·05는 모두 다음으로 감싼다.
- `patch("devfolio.core.ai_service.get_api_key", return_value="sk-test")`
- `patch("devfolio.core.ai_service._write_ai_log")`
- `patch("devfolio.core.ai_service.time.sleep") as sleep`
- `patch.dict("sys.modules", {"litellm": fake_litellm})`
- `patch.dict("os.environ", {}, clear=False)`

- [ ] **Step 2: 실행해 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_incident_regressions.py -v --no-cov`
Expected: 6 passed. 실패하는 테스트가 있으면 그 자체가 새 결함이다. 코드를 고치고 Task 2 기록부에 "회귀 테스트 작성 중 발견"으로 적는다.

- [ ] **Step 3: 되돌림 확인 (테스트가 실제로 잡는지)**

아래 변경을 하나씩 적용 → 해당 테스트 실행 → **FAIL 확인** → 원상 복구(`git checkout -- <file>`)를 반복한다. 결과는 Task 2 기록부에 적는다.

| 테스트 | 임시 변경 (`devfolio/core/ai_service.py`) |
|---|---|
| inc01 | `if "limit: 0" in err_str or "free_tier_requests" in err_str:` 조건을 `if False:`로 |
| inc02 | `"NotFoundError" in err_class` 조건 줄을 `False`로 |
| inc03 | `_extract_json`의 3단계(`brace_match`) 블록 삭제 |
| inc04 | `_strip_foreign_chars` 첫 줄에 `return text` |
| inc05 | `if not content.strip(): raise ValueError(...)` 블록 삭제 |
| inc06 | `devfolio/web/main.py` 끝에 `X = “broken”` 추가 |

Run (각각): `.venv/bin/python -m pytest tests/test_incident_regressions.py::<test> --no-cov -q`
Expected: 임시 변경 중 FAIL, 복구 후 PASS. 마지막에 `git status --short`에 테스트 파일 외 변경이 없어야 한다.

- [ ] **Step 4: 커밋**

```bash
git add tests/test_incident_regressions.py
git commit -m "Add regression tests for incidents found in real model runs"
```

### Task 2: 실수 기록부와 기록 규칙

**Files:**
- Create: `docs/agent-incidents.md`
- Modify: `AGENTS.md`, `CLAUDE.md` (`## 핵심 규칙` 아래 `### ✅ 항상` 목록), `docs/ai-collaboration.md` (개발 Loop 표의 근거 열, 진행 중인 개선 표의 상태)

**Interfaces:**
- Consumes: Task 1의 테스트 이름 6개와 Step 3 되돌림 결과
- Produces: 없음

- [ ] **Step 1: 커밋 diff로 사실 확인**

Run: `git show --stat <commit>` 후 핵심 hunk 확인 (`2063cf6 512fce4 0127349 ed79d24 8756ea9 b8f3327 f7baf34 0ba5137 76bb520 2452b7a`)
Expected: 각 항목의 "원인"과 "조치"를 diff로 뒷받침할 수 있다. 뒷받침되지 않는 칸은 "확인 필요"로 둔다.

- [ ] **Step 2: `docs/agent-incidents.md` 작성**

- 설계 문서 4절의 형식으로 INC-01 ~ INC-08을 쓴다.
- 문서 상단에 기록 규칙과 "테스트 이름 = `test_incNN_*`" 규칙을 적는다.
- 회귀 테스트 칸에는 테스트 이름과 "되돌림 확인: 실패함 ✅"을 함께 적는다.
- INC-07에는 실험 A~E 재현 절차를 적는다(`docs/ai-collaboration.md`의 표 참조).
- INC-08의 "발견"은 "확인 필요"로 둔다.

- [ ] **Step 3: 규칙 추가**

`AGENTS.md`와 `CLAUDE.md`의 `### ✅ 항상` 목록에 아래를 추가한다.
`- 실서비스 장애나 에이전트 실수를 고치면 같은 커밋에서 docs/agent-incidents.md 항목과 test_incNN_ 회귀 테스트를 추가 ("기존 장치가 못 막은 이유" 필수)`

- [ ] **Step 4: 검증 후 커밋·푸시**

Run: `scripts/check.sh`
Expected: 모두 통과

```bash
git add docs/agent-incidents.md AGENTS.md CLAUDE.md docs/ai-collaboration.md docs/superpowers/specs/2026-10-03-agent-incident-log-design.md
git commit -m "Add agent incident log and require regression tests for fixes"
git push origin main
```

설계 문서 상태는 "구현 완료"로 바꾼다.
