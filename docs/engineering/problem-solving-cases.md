# 기술 문제 해결 사례

작성일: 2026-11-16
형식: Situation → Problem → Alternatives → Decision → Implementation → Result →
Trade-off → Evidence

> 실제로 검토한 대안과 사후 분석에서 비교한 대안을 구분한다. 측정하지 않은 개선율은
> 쓰지 않는다.

---

## Case 1. 중첩 JSON 필드가 수치 가드레일을 우회한 문제

### Situation

AI 분석 결과는 `result`, `statements.weekly/monthly`, `contribution.decisions`처럼
중첩 구조를 가진다. 초기 가드레일은 최상위 문자열만 검사했다.

### Problem

`statements.monthly`에 들어간 파생 수치 `60%`가 근거에 없는데도 저장됐다.
사용자는 "AI가 근거와 대조했다"고 오해할 수 있었다.

### Alternatives

1. 프롬프트에서 중첩 필드를 금지한다. → 출력 계약이 깨지고 UI가 영향받는다.
2. 최상위 필드만 검사하고 중첩은 신뢰한다. → 같은 결함이 재발한다.
3. 모든 문자열을 재귀 검사한다. → 최소 변경, 기존 스키마 유지.

### Decision

3번. `_sanitize_value()`가 `str/list/dict`를 재귀하며 필드 경로를 기록한다.

### Implementation

```python
if isinstance(value, dict):
    return {
        key: _sanitize_value(entry, sources, removed, f"{field}.{key}")
        for key, entry in value.items()
    }
```

차단 항목에는 `field`가 붙어 `statements.monthly`처럼 추적된다.

### Result

- `tests/test_impact_eval.py::test_numeric_guardrail_reaches_nested_statements` 통과.
- `tests/test_impactnote.py::test_ai_numbers_without_evidence_are_replaced` 유지.

### Trade-off

재귀 비용은 무시할 수준이지만, 숫자처럼 보이는 ID·버전까지 검사 대상이 될 수 있다.
현재는 단위가 붙은 숫자만 claim으로 보므로 오탐을 제한한다.

### Evidence

- `impactnote/core/metrics.py`
- Commit `f05691d`
- 테스트: `tests/test_impact_eval.py`, `tests/test_impactnote.py`

---

## Case 2. `80ms`를 근거로 `80%`를 승인한 단위 불일치

### Situation

실제 NVIDIA 호출에서 Redis 캐시 활동의 결과는 `p95 200ms → 80ms`였다.
AI는 `응답 시간을 80% 이상 단축했습니다`라고 썼다.

### Problem

수치 검증이 숫자 값만 비교해 `80`이 근거에 있다는 이유로 `80%`를 통과시켰다.
값은 같지만 단위가 다른 **파생 수치**다.

### Alternatives

1. `%` 주장은 항상 차단한다. → 실제로 측정된 `50%`도 잃는다.
2. 단위를 정규화해 `(값, 단위)` 쌍으로 비교한다. → `10m`/`10분` 같은 표기 차이는 허용.
3. LLM에게 단위 변환을 맡긴다. → 비용·비결정성.

### Decision

2번. `normalize_unit()`으로 표기를 통일하고, 근거에 같은 `(값, 단위)`가 있을 때만
통과시킨다.

### Implementation

```python
_UNIT_ALIASES = {"퍼센트": "%", "m": "분", "min": "분", "h": "시간", ...}
def _measurements(text):
    return {(c["value"], c["normalized_unit"]) for c in find_claims(text)}
```

### Result

- `80%` vs `80ms` 차단.
- `10분` vs `10m` 보존.
- 첫 live 실행에서 발견 → 수정 → 두 번째 실행에서 재확인.

### Trade-off

근거에 단위 없이 숫자만 있으면 차단된다. 보수적이며, 사용자가 근거를 보완해야 한다.

### Evidence

- `impactnote/core/metrics.py`
- `tests/test_claims.py::test_percent_claim_is_not_supported_by_millisecond_value`
- `tests/test_claims.py::test_minute_and_m_alias_are_the_same_unit`
- Commit `f05691d`

---

## Case 3. 근거 없는 "안정성 향상"을 저장 전에 차단

### Situation

기존 프롬프트는 "기록에 없으면 result를 비워라"고 지시했지만 강제력이 없었다.
42개 Historical claim 중 12개가 근거 없는 정성 효과였다.

### Problem

숫자가 없는 효과 문장은 어떤 검사도 받지 않았다. 저장 후 사용자가 확인하면
보고서 본문에 들어갔다.

### Alternatives

1. 프롬프트만 강화한다. → live 3건 중 2건에서 여전히 효과 주장이 생성됐다.
2. LLM Judge를 저장 경로에 넣는다. → 호출 비용·지연, 오탐 캘리브레이션 필요.
3. 결정론 효과 Gate를 저장 직전에 둔다. → 비용 0, 사유 기록 가능.
4. 모든 결과를 보류한다. → 유용한 결과 제공률이 0이 될 수 있다.

### Decision

3번. 효과 술어+대상+수치+부정 표현을 근거와 대조하고, 근거 없는 문장만 삭제한다.
효과 주장이 아닌 구현·설계 문장은 건드리지 않는다.

### Implementation

```python
claim = verify_effect_claim(sentence, sources)
if claim and not claim.supported:
    removed.append(claim.as_dict())
    continue  # 문장 삭제
```

`ai.py`, `intel/ai_stage.py`, `report.py`에 연결했다.

### Result

- 효과 claim 22개 중 12개 차단, 10개 보존.
- False accept 0/12 (Wilson 95% CI 0–24.3%).
- 실제 NVIDIA 3건: Baseline 저장 4건 → Variant 0건 (2회 실행 모두).

### Trade-off

문장을 통째로 지우므로 사실 절이 함께 사라질 수 있다. 문장을 재작성하면 새 주장을
만들 위험이 있어 삭제를 선택했다. 사용자 수동 성과에는 적용하지 않는다.

### Evidence

- `impactnote/core/claims.py`
- `tests/test_claims.py` (13 tests)
- `evals/impact/results/effect-gate-2026-11-16.json`
- `evals/impact/results/live-ab-2026-11-16.json`
- Commit `f05691d`

---

## Case 4. "확인" 후 보고서에서 검증이 우회된 문제

### Situation

AI 후보는 `confirmed=False`일 때 보고서 본문에서 제외된다. 사용자가 확인하면
`confirmed=True`가 되고 `_achievement_lines`가 `result`를 그대로 실었다.

### Problem

확인은 "이 후보를 성과로 쓰겠다"는 뜻이지 "효과가 입증됐다"는 뜻이 아니다.
확인 후에는 수치만 재검증하고 정성 효과는 재검증하지 않았다.

### Alternatives

1. 확인 후에는 검증하지 않는다. → 현재 결함.
2. 확인 시점에 한 번만 검증한다. → 이후 근거가 삭제·변경되면 다시 뚫린다.
3. 보고서 생성 시점에 외부 근거로 재검증한다. → 매번 최신 근거 반영.

### Decision

3번. AI·분석·Git 성과만 대상으로 하고, Evidence+Activity를 외부 근거로 사용한다.
성과 자신의 `result`는 자기 지지가 되므로 제외한다.

### Implementation

```python
effect_sources = (
    [*evidence_sources, *activity_sources]
    if achievement.source in {"ai", "analysis", "git"}
    else None
)
```

### Result

- `test_report_does_not_reintroduce_confirmed_ai_effect_claim` 통과.
- `test_report_keeps_effect_claim_with_matching_evidence` 통과.
- 수동 성과는 유지.

### Trade-off

근거가 오래되거나 삭제되면 이전에 통과한 문장도 다시 차단된다. 이는 의도된 동작이다.

### Evidence

- `impactnote/core/report.py`
- `tests/test_claims.py`
- Commit `f05691d`

---

## Case 5. 커밋 작성자만 세어 공동 기여가 사라진 문제

### Situation

Git 기여도는 커밋 author만 집계했다.

### Problem

pair programming·co-authored-by로 만든 커밋이 한 사람의 단독 성과로 표시됐다.
팀 성과를 개인 성과로 쓰는 문제와 같은 뿌리다.

### Alternatives

1. author만 유지한다. → 공동 기여 누락.
2. 커밋 수를 단순 합산한다. → 한 커밋을 여러 명이 나눠 갖는다는 사실을 무시.
3. author + co-author에게 균등 분배한다. → 최소 변경, 설명 가능.

### Decision

3번. merge/revert 커밋은 제외하고, 참여자별 `credits`와 `share`를 계산한다.

### Implementation

```python
participants = [{"name": commit.author, "email": commit.email}, *commit.co_authors]
weight = 1 / max(1, len(unique))
```

### Result

- 귀속 exact 100% (8 통제 단위), wrong-solo 0%.
- `tests/test_impact_eval.py::test_fixture_extracts_achievements_and_coauthor_attribution`와
  `tests/test_intel.py::test_other_developer_contribution_is_not_attributed`가 고정함.

### Trade-off

1/n 균등 분배는 실제 작업 시간을 반영하지 않는다. 근거 없이 시간을 추정하는 것보다
설명 가능한 규칙을 선택했다.

### Evidence

- `impactnote/core/intel/gitintel.py`
- `impactnote/core/intel/engine.py`
- Commit `e728935`
- `docs/evaluation-results.md`

---

## Case 6. `ci`가 `asyncio`에 매칭된 카테고리 오탐

### Situation

성과 후보 카테고리를 키워드 substring으로 분류했다.

### Problem

`ci`가 `asyncio`에, `fast`가 `breakfast`에 매칭됐다. 배포·성능 카테고리가 잘못 붙어
성과 후보의 품질이 떨어졌다.

### Alternatives

1. 키워드 목록을 줄인다. → Recall 손실.
2. 정규식 단어 경계를 쓴다. → 짧은 영문 패턴만 정확히 매칭.
3. 형태소 분석기를 도입한다. → 새 의존성·한국어 사전 필요.

### Decision

2번. ASCII 영문·숫자 5자 이하는 `(?<![a-z0-9])pattern(?![a-z0-9])`로 검사한다.
한국어·기호는 기존 substring을 유지한다.

### Result

- `tests/test_impact_eval.py::test_category_short_patterns_do_not_match_inside_asyncio` 통과.
- 통제 저장소 Precision/Recall 1.00 유지.

### Trade-off

`CI/CD`처럼 기호가 붙은 패턴은 별도 규칙이 필요하다. 현재 목록으로 커버된다.

### Evidence

- `impactnote/core/intel/engine.py::_pattern_present`
- Commit `e728935`

---

## Case 7. gpt-oss가 reasoning 토큰을 쓰고 빈 응답을 반환한 문제

### Situation

NVIDIA NIM `openai/gpt-oss-20b` 호출에서 content가 비어 오는 경우가 있었다.

### Problem

reasoning 모델이 `max_tokens`를 추론에 먼저 소모해 최종 content가 0자가 됐다.
`max_tokens=512`에서 빈 응답, 1024+에서 성공하는 패턴을 실측했다.

### Alternatives

1. `reasoning_effort`를 낮춘다. → LiteLLM `nvidia_nim` 경로에서 지원하지 않음.
2. `max_tokens` 하한을 올린다. → 최소 변경.
3. 다른 모델로 교체한다. → 모델 접근·품질 재검증 필요.

### Decision

2번. gpt-oss 호출에 한해 `max_tokens`를 최소 2048로 보정한다.

### Implementation

```python
if provider.name == "nvidia_nim" and "gpt-oss" in str(runtime_model):
    kwargs["max_tokens"] = max(int(kwargs.get("max_tokens") or 0), 2048)
```

### Result

- 2026-11-16 live 생성 6/6 성공, JSON 6/6.
- `tests/test_ai_rate_limit_recovery.py::test_nvidia_gpt_oss_gets_reasoning_token_headroom`
  (Commit `dd4d64f`)가 2048 하한을 고정한다.

### Trade-off

토큰 사용량이 늘어 비용·지연이 증가할 수 있다. 빈 응답으로 재시도하는 것보다 낫다.

### Evidence

- `devfolio/core/ai_service.py`
- Commit `adfe892`
- `docs/nvidia-provider.md`

---

## Case 8. 소표본 0건을 "0%"로 오독할 뻔한 문제

### Situation

효과 Gate가 근거 없는 효과 claim 12개를 모두 차단해 false accept 0건이 나왔다.
초기 보고서는 percentile bootstrap 구간을 사용했다.

### Problem

0/12에서 percentile bootstrap 구간이 0–0으로 붕괴했다. "오류율 0%"로 읽히지만
실제 95% 상한은 약 24%다.

### Alternatives

1. 0건이므로 0%라고 쓴다. → 과대 주장.
2. Clopper-Pearson/Wilson 구간을 쓴다. → 소표본 비율에 적합.
3. 표본을 늘린다. → live 호출 비용·시간.

### Decision

2번. `wilson_interval()`을 추가하고, 0/12는 0–24.3%로 보고한다.

### Result

- `test_wilson_interval_does_not_collapse_at_zero` 통과.
- 실험 문서에 "5% 이하 달성 아님"을 명시.

### Trade-off

구간이 넓어 보이지만, 이것이 실제 불확실성이다.

### Evidence

- `evals/impact/metrics.py`
- `docs/evaluation/hallucination-experiments.md`
- Commit `e2dd608`
