# 2026-11-16 독립 검토 — 정성 효과 Hard Gate

대상: `impactnote/core/claims.py`, `metrics.py`, `ai.py`, `intel/ai_stage.py`,
`report.py`, `evals/impact/gate.py`, `evals/impact/live_ab.py`, 관련 문서
검토 시점: 2026-11-16 · 코드 `main` @ `6e6ce68` + 작업 트리

> 실제 병렬 서브 에이전트를 실행하지 않았다. 아래 6개 역할을 같은 세션에서 순차
> 수행했으므로 **독립성의 한계**가 있다. 발견 사항은 코드·테스트·실행 결과로만
> 뒷받침한다.

## 검토에 사용한 실제 명령

```bash
make check                                   # 480 passed, ruff/format
./.venv/bin/python -m evals.impact.run --offline --no-judge
./.venv/bin/python -m evals.impact.live_ab --out /tmp/impact-live-ab-v2
git diff --check
# 비밀값 패턴 스캔, 문서 링크 존재 확인
# clean copy 480 passed, Docker build + /api/health 200
```

실행 결과: `make check` **480 passed**, clean copy **480 passed**, Docker build 성공,
container `/api/health` **HTTP 200**, 깨진 문서 링크 **0**, 비밀값 패턴 **0**(문서의
형식 설명 제외).

---

## 1. Research Reviewer

| 발견 | 심각도 | 판정 |
| --- | --- | --- |
| Superpowers 방법론을 절차로만 적용하고 플러그인 설치를 주장하지 않음 | 낮음 | 통과 |
| NVIDIA NIM 접근을 `/v1/models` HTTP 200, 83개로 재확인 | 낮음 | 통과 |
| NeMo Guardrails/Retriever/Evaluator를 도입하지 않고 이유를 기록 | 낮음 | 통과 |
| 모델 간 품질 A/B를 수행하지 않았는데 모델 선택 근거가 충분한가 | 중간 | 한계로 명시됨 |
| “6개 역할 독립 검토”가 실제 병렬 에이전트가 아님 | 중간 | 본문에 한계 명시 |

조치: `nvidia-model-comparison.md` 에 모델 A/B `NOT_MEASURED` 를 명시했다.
추가 조치 불필요.

## 2. Evidence Reviewer

| 발견 | 심각도 | 판정 |
| --- | --- | --- |
| 효과 문장을 통째로 삭제해, 같은 문장의 사실 절이 함께 사라질 수 있음 | 중간 | 수용(보수적). 문장 재작성은 새 주장을 만들 위험이 있어 하지 않음 |
| 부정 표현이 같은 문장의 다른 대상에 걸려 근거 있는 주장을 차단할 수 있음 | 중간 | false rejection 0/10으로 측정. 표본 확대 필요 |
| `activity.result`(사용자 기록)를 근거로 인정한다. 기록된 주장이지 독립 측정은 아님 | 중간 | 제품 모델상 “기록된 결과”는 근거다. 상태·출처를 보고서에 표시 |
| `outcome` 분류가 일반 효과어+공통 토큰만으로 통과할 수 있음 | 낮음 | 12개 표본에서 false accept 0. 규칙 유지보수 필요 |
| 보고서는 AI·분석·Git 성과에만 적용되고 수동 성과는 보존됨 | 낮음 | 의도된 동작, 테스트로 고정 |

조치: 추가 코드 변경 없음. “기록=근거, 측정=별도 확인” 구분을 문서에 남겼다.

## 3. Evaluation Reviewer

| 발견 | 심각도 | 판정 |
| --- | --- | --- |
| **효과 Gate 규칙을 같은 42개 claim 을 보면서 설계했다. 0/12·10/10은 in-sample 이다** | **높음** | **중대한 한계. 일반화 주장 금지** |
| 효과 주장 22개만 분모로 사용한다(coverage 52.4%) | 중간 | coverage 를 함께 보고 |
| 0/12의 percentile bootstrap 구간이 0–0으로 붕괴 | 중간 | Wilson 0–24.3%로 수정 |
| live 3건은 프롬프트·모델이 같아 독립 표본이 아니다 | 중간 | 방향 확인으로만 사용 |
| 두 번째 live 실행은 규칙 동결 후 수행돼 소규모 out-of-sample 로 볼 수 있다 | 낮음 | 4/4 차단, n=3 |
| 전체 Hallucination 47.6%와 Gate false accept 0%를 혼동할 위험 | 높음 | 문서에서 지표 정의를 분리 |

조치: `hallucination-experiments.md` 에 in-sample 한계와 “5% 달성 아님”을 명시.
최종 판정을 `CONDITIONAL PASS` 로 제한.

## 4. Security Reviewer

| 발견 | 심각도 | 판정 |
| --- | --- | --- |
| 새 문서·결과에 `nvapi-` 실제 키 없음(문서의 형식 설명만 존재) | 낮음 | 통과 |
| `evals/impact/results/*.json` 에 합성 입력·모델 출력만 포함 | 낮음 | 통과 |
| Gate 는 외부 호출을 하지 않는다 | 낮음 | 통과 |
| live_ab 는 동결 데이터셋만 읽고 회사 자료를 전송하지 않는다 | 낮음 | 통과 |
| 프롬프트에 사용자 활동 원문이 전송된다(기존 동의 게이트 유지) | 중간 | 기존 `external_ai_consent` 경로 유지, 변경 없음 |

조치: 없음. 비밀값 스캔 결과는 이 문서 작성 시점에 clean.

## 5. Architecture Reviewer

| 발견 | 심각도 | 판정 |
| --- | --- | --- |
| 새 패키지·서비스·DB 없이 모듈 1개 + 평가 2개 추가 | 낮음 | 통과 |
| `claims.py` 가 `metrics.py` 를 import 하지 않아 순환 없음 | 낮음 | 통과 |
| `AIAnalysis.result` 자유 dict 에 `unverified_effects` 를 추가 | 낮음 | 하위 호환(추가 필드) |
| 정규식 규칙 테이블 유지보수 부담 | 중간 | 테스트·문서로 완화, 대안 없음 |
| `metrics._numbers`/`_NUMBER` 데드 코드 | 낮음 | **제거함** |
| 보고서가 `claims` 에 직접 의존해 계층이 약간 늘어남 | 낮음 | 허용 |

조치: 데드 코드 제거. 추가 구조 변경 없음.

## 6. Documentation Reviewer

| 발견 | 심각도 | 판정 |
| --- | --- | --- |
| README/AGENTS/testing/impactnote 테스트 수 480 일치 | 낮음 | 통과 |
| 2026-11-15 감사 문서의 465는 역사 기록으로 유지 | 낮음 | 통과 |
| 깨진 상대 링크 0 | 낮음 | 통과 |
| `nvidia-model-comparison.md` 토큰 표가 실제 JSON 과 불일치 | **중간** | **수정함(1,722/1,228/1,015)** |
| `hallucination-failure-cases.md` 오타(“事实”) | 낮음 | 수정함 |
| Historical 47.6%와 2026-11-16 측정이 분리됨 | 낮음 | 통과 |

조치: 토큰 표·오타 수정. `make check` 재실행 예정.

---

## 통합 판정

| 영역 | 판정 | 근거 |
| --- | --- | --- |
| 코드 정확성 | PASS | 480 tests, ruff/format |
| 비밀값·외부 전송 | PASS | 스캔 clean, 동의 게이트 유지 |
| 문서 일치 | PASS | 링크 0 broken, 수치 재확인 |
| 측정 타당성 | CONDITIONAL | in-sample 규칙 설계, n=3 live |
| 일반화 | NOT_MEASURED | held-out 효과 claim 없음 |
| 전체 AI 품질 목표 | FAIL(역사값) | 47.6%, 사실성 2.65/5 는 Historical |

**최종: CONDITIONAL PASS.** 효과 주장 부분집합에서 저장 전 차단은 검증됐지만,
전체 환각률 5% 이하·사실성 4.0/5 를 달성했다고 주장하지 않는다. 다음 라운드의
필수 과제는 **규칙 설계에 사용하지 않은 held-out 효과 claim 세트**와
기능 존재·의미 반대·귀속 주장 검증이다.
