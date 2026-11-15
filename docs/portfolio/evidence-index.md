# Evidence Index

작성일: 2026-11-16
목적: 포트폴리오·면접에서 쓰는 모든 주요 주장을 코드·커밋·테스트·측정 자료에 연결한다.

## 상태 정의

| 상태 | 의미 |
| --- | --- |
| VERIFIED | 코드/테스트/실행 결과로 직접 확인 |
| PARTIALLY_VERIFIED | 확인됐지만 표본·범위·환경이 제한적 |
| INFERRED | 코드·이력에서 합리적으로 추론, 직접 진술 없음 |
| NOT_MEASURED | 측정 자료 없음 |
| UNSUPPORTED | 근거가 없거나 현재 자료로 주장 불가 |

## 데이터셋 구분 (혼용 금지)

| ID | 데이터 | 시점 | 모델 | 성격 |
| --- | --- | --- | --- | --- |
| D1 | Historical 42 claim | 2026-10-03 | gpt-oss-20b 생성, 별도 심사 | 과거 생성문 |
| D2 | 효과 claim 42 (22 효과/20 대조) | 2026-11-16 | 결정론 Gate | 동결 fixture |
| D3 | 문서-코드 12 / 성과 20 / 귀속 8 | 2026-11-16 | 결정론 + fixture | 합성 통제 |
| D4 | Live 3 사례 × 2회 | 2026-11-16 | NVIDIA NIM gpt-oss-20b | 실제 호출 |

D1·D4는 실제 모델 출력, D2·D3은 통제 입력이다. D1의 47.6%를 D2/D4의 성과로
대체하거나, D2의 0/12를 전체 환각률로 읽으면 안 된다.

## 주장 매트릭스

| ID | 기술적 주장 | 코드 근거 | Commit | 테스트 | 측정 자료 | 상태 |
| --- | --- | --- | --- | --- | --- | --- |
| C-01 | NVIDIA NIM을 OpenAI 호환 경로로 연동했다 | `devfolio/core/ai_service.py` | `adfe892` | `tests/test_ai_service.py` | live 6/6 | VERIFIED |
| C-02 | 429/timeout에 재시도·모델 전환·Circuit Breaker를 적용했다 | `ai_service.py`, `ai_reliability.py` | `71aa804`, `adfe892` | `tests/test_ai_reliability.py` | — | VERIFIED |
| C-03 | JSON mode·prefix 정규화·빈 응답 보정을 적용했다 | `ai_service.py` | `adfe892` | `tests/test_ai_service.py`, `test_nvidia_gpt_oss_gets_reasoning_token_headroom` | JSON 6/6 | VERIFIED |
| C-04 | 중첩 dict/list까지 수치 claim을 검사한다 | `core/metrics.py` | `f05691d` | `test_numeric_guardrail_reaches_nested_statements` | — | VERIFIED |
| C-05 | 값+단위를 함께 검증해 80%를 80ms로 승인하지 않는다 | `core/metrics.py` | `f05691d` | `test_percent_claim_is_not_supported_by_millisecond_value` | live 1차 발견 | VERIFIED |
| C-06 | 정성 효과 claim을 저장 전에 차단한다 | `core/claims.py`, `core/ai.py` | `f05691d` | `tests/test_claims.py` | D2 | VERIFIED |
| C-07 | 근거 없는 효과 claim 12/12를 차단했다 | `claims.py` | `f05691d` | `test_claims.py` | D2 JSON | VERIFIED (D2 한정) |
| C-08 | 근거 있는 효과 claim 10/10을 보존했다 | `claims.py` | `f05691d` | `test_claims.py` | D2 JSON | VERIFIED (D2 한정) |
| C-09 | live A/B에서 저장된 근거 없는 효과가 4→0이었다 | `ai.py`, `evals/impact/live_ab.py` | `f05691d`, `e2dd608` | — (결과 JSON) | D4 | VERIFIED (n=3, 2회) |
| C-10 | 보고서 생성 시 효과 claim을 재검증한다 | `core/report.py` | `f05691d` | `test_report_does_not_reintroduce_confirmed_ai_effect_claim` | — | VERIFIED |
| C-11 | 수동 성과는 자동 삭제하지 않는다 | `report.py` | `f05691d` | `test_manual_effect_claim_is_not_silently_removed` | — | VERIFIED |
| C-12 | 프로젝트 후보의 근거 부족 시 HYPOTHESIS로 강등한다 | `intel/ai_stage.py` | `e728935` | `tests/test_intel.py` | D3 | VERIFIED |
| C-13 | co-author를 귀속에 포함해 1/n 분배한다 | `intel/gitintel.py`, `engine.py` | `e728935` | `test_fixture_extracts_achievements_and_coauthor_attribution` | D3 | VERIFIED (규칙) |
| C-14 | 통제 저장소 귀속 exact 100% (8단위) | `engine.py` | `e728935` | `tests/test_intel.py`, `test_fixture_extracts_achievements_and_coauthor_attribution` | D3 | PARTIALLY_VERIFIED |
| C-15 | 문서-코드 후보 P/R/F1 1.00 (12 positive/8 negative) | `intel/engine.py` | `e728935` | `test_dataset_has_enough_units_and_valid_labels` | D3 | PARTIALLY_VERIFIED |
| C-16 | 전체 테스트 481개 통과 | `tests/` | `dd4d64f` | `pytest -q` | 481 passed | VERIFIED (로컬) |
| C-17 | Docker 이미지 빌드·health 200 | `Dockerfile`, compose | `3ec1010` | CI docker job | 200 | VERIFIED (CI + 로컬) |
| C-18 | 3개 OS CI matrix가 통과한다 | `.github/workflows/ci.yml` | `61d9a70` | run `43733588389` | 9/9 jobs success | VERIFIED |
| C-19 | Clean copy에서 481개 통과 | — | `dd4d64f` | clean copy run | 481 passed | VERIFIED |
| C-20 | Historical 환각률 47.6% (20/42) | `evals/impact/run.py` | 이전 | judge | D1 | PARTIALLY_VERIFIED |
| C-21 | Historical 사실성 2.65/5 | judge | 이전 | — | D1 | PARTIALLY_VERIFIED |
| C-22 | 현재 전체 환각률 5% 이하 | — | — | — | D1 재심사 없음 | NOT_MEASURED |
| C-23 | 현재 사실성 4.0/5 | — | — | — | D1 재심사 없음 | UNSUPPORTED |
| C-24 | 모든 환각을 제거했다 | — | — | — | — | UNSUPPORTED |
| C-25 | LLM Judge가 사람 라벨과 일치한다 | — | — | — | 사람 라벨 없음 | NOT_MEASURED |
| C-26 | NVIDIA API 비용(USD) | — | — | — | 단가·청구 없음 | NOT_MEASURED |
| C-27 | Windows GUI가 정상 동작한다 | — | — | CI import만 | 클릭 없음 | NOT_MEASURED |
| C-28 | Mermaid 10개 다이어그램이 렌더링된다 | `docs/architecture/diagrams.md` | `cdaf597` | mmdc 10/10 | SVG 렌더 exit 0 | VERIFIED (로컬 mmdc) |
| C-29 | 개발 기간 2026-04-16~2026-11-16 | Git | — | — | `git log` | VERIFIED (기록 기준) |
| C-30 | 팀 규모·역할 분담 | — | — | — | — | UNKNOWN |

## 제외한 주장

| 주장 | 이유 |
| --- | --- |
| "AI 분석 정확도 90% 향상" | 전후 동일 데이터 측정 없음 |
| "환각률 47.6% → 0%" | D1과 D2/D4는 데이터·범위가 다름 |
| "테스트 커버리지 95%" | coverage 측정 자료 없음 |
| "개발 기간 7개월" | Git 날짜 범위일 뿐 연속 개발 기간이 아님 |
| "실제 회사 업무에 도입" | 도입·사용 로그 없음 |

## 인용 규칙

- 숫자 뒤에 데이터셋 ID를 붙인다. 예: "12/12 차단 (D2)".
- `pytest` 수치는 실행 시점을 함께 쓴다. 예: "481 passed (2026-11-16, `dd4d64f`)".
- 과거 결과는 "Historical"을 붙이고 현재 성능으로 표현하지 않는다.
- 0건 비율은 신뢰구간과 함께 쓴다.
