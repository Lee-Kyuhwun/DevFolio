# ImpactNote AI 평가 체계

기준일: 2026-11-15 · Ground Truth 버전: `impactnote-ai-eval-1.0.0`

이 문서는 “AI 가 그럴듯한 문장을 썼는가”가 아니라 **실제 근거와 비교해 맞는가**를 측정하는
방법을 정의한다. 평가 코드는 제품 코드와 분리된 `evals/impact/` 에 있고, 결과는
[`evaluation-results.md`](evaluation-results.md) 에 기록한다.

## 1. 목적과 원칙

목적:

1. Hallucination(근거 없는 주장)을 실제로 센다.
2. 성과 발굴의 Precision/Recall/F1 을 실제 분석기로 측정한다.
3. 성과 문장 품질을 사실성 중심으로 채점한다.
4. 여러 개발자 저장소에서 개인 기여 귀속을 검증한다.
5. 문서와 코드의 의미 일치 판정을 검증한다.
6. AI 가 인용한 근거가 주장을 논리적으로 뒷받침하는지(Semantic Entailment) 검증한다.

원칙:

- 정답 데이터와 생성 결과를 분리한다.
- 임계값은 결과를 보기 전에 `evals/impact/run.py::THRESHOLDS` 에 고정한다.
- 실제 Provider 호출과 Mock/Offline 결과를 분리 보고한다.
- 분모가 0이면 100%로 바꾸지 않고 `NOT_MEASURED` 로 둔다.
- 평가 데이터에 맞춰 프롬프트를 반복 튜닝하지 않는다. 평가셋은 동결 버전으로 관리한다.
- 원문·비밀키·회사 자료를 결과 파일에 남기지 않는다.

## 2. 평가 데이터

`evals/impact/dataset.json` (SHA-256 앞 16자 `6cf68ed945bc6b91`):

| 데이터 | 수 | 내용 |
| --- | ---: | --- |
| Claim 단위 | 42 | 2026-10-03 NVIDIA `gpt-oss-20b` 생성문 30개 + 경계 사례 12개. 라벨: ENTAILMENT 22, NEUTRAL 13, INSUFFICIENT_EVIDENCE 4, CONTRADICTION 3 |
| 문서-코드 단위 | 12 | MATCH 3, PARTIAL_MATCH 2, MISMATCH 3, NOT_IMPLEMENTED 3, INSUFFICIENT_EVIDENCE 1 |
| 성과 단위 | 12 | 실제 개선이 있는 통제 변경 |
| 비성과 경로 | 8 | 포맷·주석·이동·무의미 변경 등 |
| 귀속 단위 | 8 | 단독·분리 파일·공동 수정·리팩터링·pair·co-author·merge 등 |
| 품질 출력 | 20 | 2026-10-03 NVIDIA 요약문. **현재 프롬프트가 아닌 Historical 출력** |
| Live 활동 | 3 | 현재 프롬프트로 NVIDIA 실호출 |

총 라벨 결정 행은 85개(claim 42 + doc 12 + 성과 20 + 귀속 8 + live 3)다. 다만 claim 42개는
같은 생성문에서 나온 복수 claim 을 포함하고, 성과 20개는 12 positive + 8 negative 이므로
“85개의 독립 프로젝트”가 아니다. 지표별 표본 수를 각각 보고한다.

### 품질 데이터의 시점

품질 20개는 **2026-10-03 DevFolio 시절 NVIDIA 출력**이다. 현재 `impactnote.core.ai`
프롬프트의 품질을 대표하지 않는다. 현재 프롬프트 품질은 live 3개뿐이므로 일반화하지 않는다.
이 구분을 결과 문서에 명시한다.

## 3. 지표 정의

### 3.1 Hallucination Rate

성과 문장을 검증 가능한 claim 으로 나누고, 각 claim 을 근거와 비교해 다음으로 분류한다.

| 라벨 | 의미 |
| --- | --- |
| `SUPPORTED` / `ENTAILMENT` | 근거가 claim 을 뒷받침 |
| `CONTRADICTED` / `CONTRADICTION` | 근거가 claim 을 반박 |
| `UNSUPPORTED` / `NEUTRAL` | 관련은 있으나 claim 을 입증하지 못함 |
| `INSUFFICIENT_EVIDENCE` | 근거 자체가 부족 |

정의:

```text
Contradiction Rate = CONTRADICTION / N
Unsupported Claim Rate = (NEUTRAL + INSUFFICIENT_EVIDENCE) / N
Combined Unsupported-or-Contradicted Rate = (NEUTRAL + INSUFFICIENT_EVIDENCE + CONTRADICTION) / N
```

세 값을 하나의 “Hallucination Rate”로 섞지 않는다. 보고서의 **Hallucination Rate**는
명시적으로 `Combined Unsupported-or-Contradicted Rate` 이다.

### 3.2 성과 발굴 Precision / Recall / F1

통제 Git 저장소의 정답 성과 경로와 분석기 후보를 비교한다.

```text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 × Precision × Recall / (Precision + Recall)
```

분모가 0이면 `NOT_MEASURED`. 같은 문제를 표현하는 후보는 사전에 정의한 경로·변경 단위
matching rule 로만 TP 로 인정하고, 문장 유사도만으로 판정하지 않는다.

### 3.3 문장 품질

독립 심사 모델이 근거와 요약문을 보고 5개 축을 1~5로 채점한다.

| 축 | 높은 점수의 조건 |
| --- | --- |
| `factual_accuracy` | 근거에 없는 수치·기능·성과가 없음. 있으면 1~2 |
| `specificity` | 구체적 기술·행동·결과가 있음 |
| `contribution_clarity` | 본인 행동과 공동 작업이 구분됨 |
| `problem_solution` | 문제→행동→결과가 연결됨 |
| `internal_report_tone` | 자기소개서·마케팅 과장 없이 내부 보고 문체 |

품질 하한 게이트:

```text
mean >= 3.5
AND factual_accuracy 평균 >= 3.0
AND factual_accuracy 1~2점 비율 <= 25%
```

평균만 높고 사실성이 낮은 출력은 통과하지 못한다. 이 사실성 하한은 1차 측정에서
`mean 3.68` 인데도 `factual_accuracy 2.65`, 1~2점 55%가 나온 뒤 **명시적으로 추가**했다.
사후에 추가한 게이트임을 숨기지 않는다.

### 3.4 개인 기여 귀속

`GitCommit.author`, `committer`, `Co-authored-by`, merge parent, 파일별 변경을 결합한다.
정답은 다음을 구분한다.

- 직접 구현 / 공동 구현 / 리뷰·설계 기여 / 담당자 기록 / 확인 불가(UNKNOWN)

지표:

```text
Exact attribution accuracy = 정확히 맞힌 단위 / N
Wrong-solo rate = 공동 기여를 단독 기여로 잘못 표시한 단위 / N
Coverage = 귀속을 산출한 단위 / N
```

근거가 없으면 단독 귀속으로 확정하지 않고 UNKNOWN 으로 둔다.

### 3.5 문서-코드 의미 일치

문서의 주요 주장을 요구사항/명제로 나누고 실제 코드·설정·테스트와 비교한다.

라벨: `MATCH`, `PARTIAL_MATCH`, `MISMATCH`, `NOT_IMPLEMENTED`, `INSUFFICIENT_EVIDENCE`.

지표: accuracy, macro F1, class별 confusion matrix, **false MATCH rate**(구현되지 않았는데
MATCH 로 판정한 비율).

### 3.6 Semantic Entailment

AI 주장 → 인용 근거 → 논리적 뒷받침을 평가한다.

| 라벨 | 의미 |
| --- | --- |
| `ENTAILMENT` | 근거가 주장을 뒷받침 |
| `CONTRADICTION` | 근거가 주장을 반박 |
| `NEUTRAL` | 관련은 있지만 입증하지 못함 |
| `INSUFFICIENT_EVIDENCE` | 근거가 불충분 |

예: “캐싱을 적용해 응답 시간이 70% 단축되었다”에서 캐시 코드는 “캐싱 도입”만 뒷받침하고
“70% 단축”은 별도 벤치마크 없이는 ENTAILMENT 가 아니다.

지표:

```text
Claim-level Entailment Accuracy
Macro F1
Unsupported Citation Rate = ENTAILMENT 로 인정된 claim 중 근거가 부족한 비율
Contradiction Detection Recall = 실제 CONTRADICTION 중 맞힌 비율
```

LLM Judge 를 쓰더라도 **정답 라벨과 비교해 Judge 자체의 정확도를 먼저 측정**한다.
Judge 점수만으로 정답을 대체하지 않는다.

## 4. 평가 실행 구조

```text
evals/impact/run.py
  ├─ dataset.json 로드 (동결 버전·SHA 기록)
  ├─ fixture.py: 매 실행마다 임시 Git 저장소 생성
  ├─ 결정론 분석기 실행 (성과 후보·귀속·문서-코드)
  ├─ claim/semantic/doc/quality: NVIDIA 독립 심사 (judge.py, 캐시)
  ├─ --live: 현재 impactnote.core.ai 프롬프트로 3회 실제 생성
  │    └─ sanitize_ai_result() 적용 전/후 수치 비교
  ├─ THRESHOLDS 로 PASS/FAIL/CONDITIONAL 판정
  └─ impact-results.json + impact-results.md
```

- 생성 모델: `nvidia_nim/openai/gpt-oss-20b`
- 독립 심사 모델: `minimaxai/minimax-m3.1-flash` (실패 시 `z-ai/glm-5.3-flash`)
- 심사 캐시: `evals/impact/.cache/judge.json` (gitignore)
- Provider fallback: 평가 중 비활성 (`DEVFOLIO_AI_PROVIDER_FALLBACK=0`)
- Judge 429/503: 백오프 후 재시도, 503 safety screening 은 대체 모델

## 5. 실행 방법

```bash
# 의존성
python3.11+ -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,all]"

# 키 없이 결정론 기준선 + 분석기만
python -m evals.impact.run --offline --no-judge --out /tmp/impact-offline

# 실제 NVIDIA 생성 3회 + 독립 심사 (비용·시간 발생)
export NVIDIA_NIM_API_KEY=...        # 채팅·문서·로그에 값을 남기지 않는다
export DEVFOLIO_AI_PROVIDER_FALLBACK=0
python -m evals.impact.run --live --out /tmp/impact-live

# 키 없이 저장된 심사 캐시를 사용해 재계산
python -m evals.impact.run --offline --out /tmp/impact-recheck
```

전체 제품 테스트와 평가 회귀 테스트:

```bash
pytest -q
pytest -q tests/test_impact_eval.py tests/test_intel.py tests/test_ai_service.py
```

## 6. 판정 규칙

`THRESHOLDS`:

| 지표 | 기준 |
| --- | ---: |
| Hallucination combined | ≤ 20% |
| Extraction F1 | ≥ 0.70 |
| Quality mean | ≥ 3.50 |
| Quality factual mean | ≥ 3.00 |
| Quality low-factuality rate | ≤ 25% |
| Attribution exact | ≥ 80% |
| Doc-code accuracy | ≥ 70% |
| Semantic accuracy | ≥ 70% |
| Effect gate false accept | ≤ 5% |
| Effect gate retention | ≥ 80% |

전체 판정:

- 모든 지표 PASS → `PASS`
- 실패 1~2개 또는 `NOT_MEASURED` 존재 → `CONDITIONAL PASS`
- 실패 3개 이상 → `FAIL`
- 필수 데이터가 없어 판정 불가 → `INCONCLUSIVE`

`CONDITIONAL PASS` 는 “제품 전체가 통과했다”는 뜻이 아니다. 실패한 지표는 별도로
`FAIL` 로 표시하며, 이번 결과는 Hallucination 과 품질이 FAIL 이다.

## 7. 한계

- 42 claim, 12 문서-코드, 20 성과, 8 귀속은 소규모다. 95% 구간은 넓다.
- 통제 저장소는 합성이며 실제 회사 저장소의 언어·도메인 분포를 대표하지 않는다.
- 품질은 단일 AI 심사 모델 점수다. 사람 2인 이상의 평가자 간 일치도는 측정하지 않았다.
- 품질 20개는 2026-10-03 Historical 출력이다.
- 생성 모델과 심사 모델이 같은 NVIDIA 호스팅 환경에 있어 완전한 독립성은 아니다.
- 리뷰·설계 기여, 대리 커밋, 이슈 담당자 기여는 근거 부족으로 정답에서 제외했다.
- 정성 효과 주장은 `impactnote/core/claims.py` 의 결정론 Gate 로 검증한다. 효과 주장이 아닌 기능 존재·의미 반대·기여 귀속·용량 주장은 여전히 자동 검증하지 못한다.
- 효과 Gate 의 22개 표본(근거 없음 12)은 작다. 0/12 의 Wilson 95% 상한은 24.3%다.

## 8. 결과

실제 측정값·신뢰구간·실패 항목은 [`evaluation-results.md`](evaluation-results.md) 와
[`../evals/impact/results/latest.json`](../evals/impact/results/latest.json) 에 있다.

## 9. 정성 효과 Hard Gate

`evals/impact/gate.py` 는 42개 claim 중 효과 주장만 골라 다음을 측정한다.

- `false_accept_rate`: 근거 없는 효과 주장을 통과시킨 비율 (목표 ≤ 5%).
- `retention`: 근거 있는 효과 주장을 보존한 비율 (목표 ≥ 80%).
- `coverage`: 전체 claim 중 Gate 적용 대상 비율. 효과 주장이 아닌 claim 은 분모에서
  제외되므로, 이 지표를 함께 보지 않으면 개선을 과대 해석하게 된다.

42-claim Historical Hallucination Rate 와 이 Gate 의 false accept rate 는 서로 다른
지표다. 전자는 생성문 전체의 unsupported 비율, 후자는 효과 주장 부분집합의 저장 차단
성능이다.
