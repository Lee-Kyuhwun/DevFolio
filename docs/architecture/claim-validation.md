# Claim 검증 파이프라인

기준: 2026-11-16 · 관련 커밋 `f05691d`
관련 코드: `impactnote/core/metrics.py`, `impactnote/core/claims.py`,
`impactnote/core/ai.py`, `impactnote/core/intel/ai_stage.py`,
`impactnote/core/report.py`, `evals/impact/gate.py`

## 1. 문제

AI는 숫자가 없어도 성과를 만들 수 있다.

```text
기록: 백오피스 기능 목록만 있고 비용·운영 지표는 기록되지 않음
AI:   "운영 비용을 절감했다."
```

기존 수치 가드레일은 `40%`, `3시간` 같은 **숫자+단위**만 검사했다. 숫자가 없는
효과 문장은 검사 대상이 아니었고, 사용자가 AI 후보를 확인하면 보고서가 그대로
실었다.

## 2. 두 개의 검증 계층

### 2.1 수치 Claim — `metrics.py`

1. `find_claims()`가 숫자+단위를 추출한다.
2. `normalize_unit()`이 `10m`/`10분`, `%`/`퍼센트`, `ms`/`밀리초`를 통일한다.
3. `unsupported_claims()`가 근거의 `(값, 단위)` 쌍과 대조한다.
4. 불일치하면 `sanitize_claims()`가 `[확인 필요]`로 바꾼다.
5. `sanitize_ai_result()`가 중첩 dict/list까지 재귀한다.

핵심 변경:

```python
_CLAIM_PATTERN = re.compile(
    r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*"
    r"(개월|분기|퍼센트|밀리초|시간|ms|min|hr|sec|분|초|년|주|일|건|개|회|배|원|명|%|m|h|s)"
)
```

`80%`와 `80ms`는 값이 같아도 단위가 다르므로 통과하지 않는다.
반대로 `10m`와 `10분`은 같은 단위로 정규화한다.

### 2.2 정성 효과 Claim — `claims.py`

효과 술어를 가진 문장만 대상으로 한다.

| 단계 | 동작 |
| --- | --- |
| 탐지 | `향상·개선·절감·단축·보장·예방·제거·분산` 등 + 대상 |
| 수치 확인 | 주장의 모든 수치가 근거에 있어야 함 |
| 부정 확인 | `측정되지 않음·기록 없음·자료 없음` 문장은 지원에서 제외 |
| 대상 확인 | 근거 문장과 공유하는 대상 토큰이 있어야 함 |
| 효과 확인 | 같은 종류의 효과 표현이 근거에 있어야 함 |
| 판정 | `SUPPORTED` / `UNSUPPORTED` + 사유 |

효과 주장이 아니면 `None`을 반환하고 문장을 건드리지 않는다. 구현·설계 사실은
그대로 둔다.

## 3. 저장 전 흐름

```text
AIService._call
  → _parse_json
  → sanitize_ai_result(수치)
  → gate_result(정성 효과)
  → AIAnalysis.result
       unverified_metrics[]
       unverified_effects[]
       unverified_fields[]
```

차단된 문장은 삭제하고, 왜 삭제됐는지를 `unverified_effects`에 남긴다.
`result`가 전부 삭제되면 빈 문자열로 두고 `unverified_fields`에 `result`를 넣는다.

프로젝트 분석(`intel/ai_stage.py`)은 인용 근거별로 같은 검증을 수행한다.
차단이 있으면 후보 품질을 `HYPOTHESIS`로 낮추고 note에 이유를 남긴다.

## 4. 보고서 재검증

`report.build_content()`는 AI·분석·Git이 만든 성과에 대해:

1. 확인 전(`confirmed=False`)이면 본문에서 제외한다.
2. 확인 후에도 **외부 근거**(Evidence + Activity)로 효과 주장을 다시 검증한다.
3. 차단된 문장은 "확인 필요 항목 (근거 없음)"에 사유와 함께 표시한다.

사용자가 직접 작성한 성과(`source=manual`)는 자동 삭제하지 않는다. 사용자의
주장과 기계 생성 문장을 같은 기준으로 취급하면 사용자가 쓴 기록을 잃기 때문이다.

## 5. 데이터 구조

현재 별도 Claim 테이블은 없다. 최소 변경을 위해 다음에 결과를 남긴다.

| 위치 | 내용 |
| --- | --- |
| `AIAnalysis.result.unverified_metrics` | 대체된 수치 claim |
| `AIAnalysis.result.unverified_effects` | 삭제된 효과 문장·분류·사유·필드 |
| `AIAnalysis.result.unverified_fields` | 사용자가 확인해야 할 필드 |
| `Candidate.quality` | `HYPOTHESIS` 강등 |
| `Candidate.notes` | 강등 사유 |
| `Report` meta `unverified` | 보고서에서 제외된 항목 |
| `Report` meta `pending_achievement_ids` | 본문 제외 미확정 성과 |

## 6. 검증 결과 (2026-11-16)

42개 동결 claim 중 효과 주장 22개:

| 값 | 결과 |
| --- | ---: |
| 근거 없는 효과 claim | 12 |
| 차단 | 12 / 12 |
| 근거 있는 효과 claim | 10 |
| 보존 | 10 / 10 |
| False accept | 0 (Wilson 95% CI 0–24.3%) |
| False reject | 0 |

실제 NVIDIA 생성 3건(2회 실행):

| 실행 | Baseline 저장 | Variant 저장 |
| --- | ---: | ---: |
| 1차 | 4 | 0 |
| 2차 | 4 | 0 |

- Baseline = 수치 가드레일만.
- Variant = 수치 가드레일 + 정성 효과 Gate.
- 같은 raw 출력에 두 방식을 적용해 Gate의 증분 효과를 분리했다.

## 7. 테스트

| 테스트 | 고정하는 동작 |
| --- | --- |
| `test_unmeasured_effect_claim_is_blocked` | 근거 없는 안정성 향상 차단 |
| `test_explicit_no_measurement_is_not_treated_as_support` | "기록 없음"을 지원으로 오판하지 않음 |
| `test_effect_claim_with_matching_measurement_is_kept` | 측정값이 있는 효과 보존 |
| `test_numeric_effect_without_benchmark_is_blocked` | 벤치마크 없는 70% 차단 |
| `test_implementation_fact_is_not_stripped` | 구현 사실 보존 |
| `test_gate_result_reports_nested_field_paths` | 중첩 필드 경로 |
| `test_ai_analysis_drops_unsupported_effect_claim` | 저장 전 차단(HTTP) |
| `test_ai_analysis_keeps_effect_supported_by_recorded_result` | 사용자 기록 결과를 근거로 인정 |
| `test_report_does_not_reintroduce_confirmed_ai_effect_claim` | 확인 후 재유입 차단 |
| `test_report_keeps_effect_claim_with_matching_evidence` | 근거 있는 보고서 문장 보존 |
| `test_manual_effect_claim_is_not_silently_removed` | 수동 성과 보존 |
| `test_percent_claim_is_not_supported_by_millisecond_value` | 80% vs 80ms |
| `test_minute_and_m_alias_are_the_same_unit` | 10m = 10분 |
| `test_ai_candidate_without_effect_evidence_is_demoted` | 프로젝트 후보 HYPOTHESIS 강등 |

전체: **481 passed** (`make check`).

## 8. 한계

1. **효과 주장만 검증한다.** 기능 존재(c005), 의미 반대(c034, c037), 기여 귀속(c001),
   용량(c040)은 이 Gate의 대상이 아니다.
2. **규칙 기반이다.** 한국어 표현이 목록에 없으면 놓칠 수 있다.
3. **문장 단위로 삭제한다.** 한 문장에 사실과 효과가 섞여 있으면 사실 절도 함께
   사라진다. 새 문장을 만들어 붙이지 않는 것이 더 안전하다고 판단했다.
4. **사용자 기록을 근거로 인정한다.** `activity.result`는 사용자가 쓴 기록이며,
   독립 측정을 보장하지 않는다.
5. **표본이 작다.** 12개 효과 claim, live 3건이다. 0/12의 95% 상한은 24.3%다.
6. **Gate 규칙을 같은 42개 claim을 보면서 설계했다.** in-sample 결과이므로
   일반화 성능으로 읽으면 안 된다. held-out 효과 claim 세트가 다음 과제다.

## 9. 관련 문서

- [`../research/hallucination-root-cause.md`](../research/hallucination-root-cause.md)
- [`../research/hallucination-brainstorming.md`](../research/hallucination-brainstorming.md)
- [`../decisions/ADR-hallucination-mitigation.md`](../decisions/ADR-hallucination-mitigation.md)
- [`../evaluation/hallucination-experiments.md`](../evaluation/hallucination-experiments.md)
- [`../evaluation/hallucination-failure-cases.md`](../evaluation/hallucination-failure-cases.md)
