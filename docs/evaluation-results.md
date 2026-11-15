# ImpactNote AI 평가 결과

> 이 문서는 실제 실행 결과다. Mock/Offline 결과와 구분하며, 측정하지 못한 값은
> `NOT_MEASURED` 로 표기한다.

## 0. 2026-11-16 추가 측정 — 정성 효과 Hard Gate

2026-11-15 결과는 **Historical 생성문** 기준으로 그대로 보존한다. 이 절은 같은 42개
claim 에 새 결정론 Gate 를 적용한 **추가 측정**이며, 생성 모델을 다시 호출해
Hallucination Rate 를 낮췄다는 뜻이 아니다.

| 항목 | 값 |
| --- | --- |
| 실행 시각 | 2026-11-16 00:19:45 +09:00 |
| 코드 | `main` @ `6e6ce68` + 이번 작업 트리 |
| 데이터셋 | `impactnote-ai-eval-1.0.0` (`6cf68ed945bc6b91`) |
| 생성 모델 | `nvidia_nim/openai/gpt-oss-20b` |
| Gate | `impactnote/core/claims.py` (결정론, 외부 호출 없음) |
| 효과 주장 | 22 / 42 (52.4%) |
| 근거 없는 효과 주장 차단 | 12 / 12 |
| 근거 있는 효과 주장 보존 | 10 / 10 |
| False accept | 0 (Wilson 95% CI 0–24.3%) |
| 실제 NVIDIA A/B | Baseline 저장 4건 → Variant 0건 (3/3 성공) |
| 전체 회귀 | 480 passed |

산출물:
[`../evals/impact/results/effect-gate-2026-11-16.json`](../evals/impact/results/effect-gate-2026-11-16.json),
[`../evals/impact/results/live-ab-2026-11-16.json`](../evals/impact/results/live-ab-2026-11-16.json).

상세:
[`research/hallucination-root-cause.md`](research/hallucination-root-cause.md),
[`evaluation/hallucination-experiments.md`](evaluation/hallucination-experiments.md).

이 Gate 는 효과 주장만 대상으로 한다. 기능 존재·의미 반대·기여 귀속·용량 주장은
여전히 미해결이며, 전체 환각률이 5% 이하라고 주장하지 않는다.

## 1. 실행 메타데이터

| 항목 | 값 |
| --- | --- |
| 실행 시각 | 2026-11-15 23:09:12 +09:00 |
| 실행 모드 | `--live` (실제 NVIDIA 호출 + 독립 심사) |
| Git 기준 | `48e35fc` (평가 코드·가드레일 수정은 작업 트리에 포함) |
| Ground Truth | `impactnote-ai-eval-1.0.0` |
| Dataset SHA | `6cf68ed945bc6b91` |
| 생성 Provider | `nvidia_nim` |
| 생성 모델 | `nvidia_nim/openai/gpt-oss-20b` |
| 독립 심사 모델 | `minimaxai/minimax-m3.1-flash` |
| 심사 상태 | `LIVE_VERIFIED` |
| 전체 판정 | **CONDITIONAL PASS** |
| 집계 결과 | [`../evals/impact/results/latest.json`](../evals/impact/results/latest.json) |

`CONDITIONAL PASS` 는 실패 지표가 2개라서 붙은 판정이다. **AI 품질 자체는 Hallucination 과
문장 품질에서 FAIL** 이다. “전체 통과”로 읽으면 안 된다.

## 2. 요약 표

| 평가 항목 | 기존 | 이번 측정 | 표본 수 | 판정 |
| --- | --- | --- | ---: | --- |
| Hallucination Rate (combined) | 미측정 | **47.6%** (95% CI 33.3–61.9%) | 42 claims | **FAIL** |
| 성과 발굴 Precision / Recall / F1 | 미측정 | **1.00 / 1.00 / 1.00** | 20 경로 (12 TP) | **PASS** |
| 성과 문장 품질 | 미측정 | 평균 **3.68 / 5**, 사실성 **2.65 / 5** | 20 | **FAIL** |
| 개인 기여 귀속 | 미측정 | exact **100%**, coverage **100%**, wrong-solo **0%** | 8 | **PASS** |
| 문서·코드 의미 일치 | 미측정 | accuracy **83.3%**, macro F1 **0.839** | 12 | **PASS** |
| Semantic Entailment | 미측정 | accuracy **83.3%**, macro F1 **0.710** | 42 claims | **PASS** |

## 3. Hallucination 상세

| 라벨 | 수 | 비율 |
| --- | ---: | ---: |
| SUPPORTED / ENTAILMENT | 22 | 52.4% |
| CONTRADICTED | 3 | 7.1% |
| UNSUPPORTED (NEUTRAL + INSUFFICIENT_EVIDENCE) | 17 | 40.5% |
| 합계 | 42 | 100% |

정의별:

- **Contradiction Rate**: 3 / 42 = **7.1%**
- **Unsupported Claim Rate**: 17 / 42 = **40.5%**
- **Combined Unsupported-or-Contradicted Rate**: 20 / 42 = **47.6%**
- 95% bootstrap CI: **33.3%–61.9%**
- 임계값: ≤ 20% → **FAIL**

원인:

- 2026-10-03 생성문에는 “생산성 향상”, “안정성 개선” 같은 정성 효과 주장이 많았고,
  기록에 없는 수치·기능이 섞였다.
- 30개 생성문과 경계 사례 12개를 사용한 Historical 평가다. 현재 프롬프트의 성능을 직접
  대표하지 않는다.
- 수치 가드레일은 숫자를 `[확인 필요]` 로 바꾸지만, **정성 효과 주장의 진위는 자동으로
  판정하지 못한다.**

## 4. 성과 발굴 Precision / Recall

통제 Git 저장소를 매 실행마다 새로 만들고, 정답 12개 성과 + 비성과 8개 경로와 비교했다.

```text
TP = 12, FP = 0, FN = 0
Precision = 1.00
Recall    = 1.00
F1        = 1.00
```

- 카테고리 부분문자열 버그(`ci` → `asyncio`)를 수정한 뒤 측정했다.
- 후보 상한을 12→14로 올려 저가중치 Dockerfile/metrics 누락을 줄였다.
- 합성 fixture 이므로 실제 회사 저장소의 모든 성과를 찾는다고 일반화하지 않는다.

## 5. 문장 품질

| 축 | 평균 |
| --- | ---: |
| 사실 정확성 | **2.65** |
| 구체성 | 4.55 |
| 개인 기여 명확성 | 3.70 |
| 문제→해결 연결 | 4.05 |
| 내부 보고 문체 | 3.45 |
| **전체 평균** | **3.68 / 5** (95% CI 3.51–3.88) |

- 사실 정확성 1~2점: **11 / 20 (55%)**
- 품질 하한: 평균 ≥3.5, 사실성 ≥3.0, 1~2점 비율 ≤25%
- 결과: 평균은 넘지만 사실성·저사실성 비율이 미달 → **FAIL**

문장은 구체적이고 구조는 좋지만, 근거에 없는 효과·수치가 포함된 경우가 절반을 넘었다.
“문장이 매끄럽다”는 이유로 품질 통과로 처리하지 않는다.

## 6. 개인 기여 귀속

| 항목 | 결과 |
| --- | ---: |
| Exact attribution accuracy | **100%** (8/8) |
| Coverage | **100%** |
| Wrong solo rate | **0%** |

검증한 사례: 단독 작성, 파일 분리, 공동 수정, 리팩터링, pair, `Co-authored-by`, merge.
`Co-authored-by` trailer 와 merge parent(`%P`)를 파싱하고, 작성자와 co-author 에게 credit 을
분배하도록 수정한 뒤 측정했다.

한계: 리뷰만 한 경우, 대리 커밋, 이슈 담당자 기여는 근거가 없어 정답에서 제외했다.
즉 “모든 협업 유형을 맞혔다”는 뜻이 아니다.

## 7. 문서·코드 의미 일치

| 항목 | 결과 |
| --- | ---: |
| Accuracy | **83.3%** (10/12) |
| Macro F1 | **0.839** |
| False MATCH rate | **0%** |

Confusion matrix:

| Gold \ Pred | MATCH | PARTIAL | MISMATCH | NOT_IMPL | INSUFF |
| --- | ---: | ---: | ---: | ---: | ---: |
| MATCH | 3 | 0 | 0 | 0 | 0 |
| PARTIAL_MATCH | 0 | 1 | 1 | 0 | 0 |
| MISMATCH | 0 | 0 | 3 | 0 | 0 |
| NOT_IMPLEMENTED | 0 | 0 | 0 | 3 | 0 |
| INSUFFICIENT_EVIDENCE | 0 | 1 | 0 | 0 | 0 |

- 존재하지 않는 구현을 MATCH 로 판정한 false MATCH 는 0건이다.
- `PARTIAL_MATCH` 1건을 MISMATCH 로, `INSUFFICIENT_EVIDENCE` 1건을 MATCH 로 판정했다.
- 12개 소규모 표본이며, 문서-코드 판정은 심볼/라우트 기반이라 한국어 서술형 문서에 보수적이다.

## 8. Semantic Entailment

| 항목 | 결과 |
| --- | ---: |
| Claim-level accuracy | **83.3%** (35/42) |
| Macro F1 | **0.710** |
| Unsupported Citation Rate | **0%** (predicted ENTAILMENT 22건 중) |
| Contradiction Detection Recall | **100%** (3/3) |

Confusion matrix:

| Gold \ Pred | ENTAIL | CONTRAD | NEUTRAL | INSUFF |
| --- | ---: | ---: | ---: | ---: |
| ENTAILMENT | 22 | 0 | 0 | 0 |
| CONTRADICTION | 0 | 3 | 0 | 0 |
| NEUTRAL | 0 | 2 | 8 | 3 |
| INSUFFICIENT_EVIDENCE | 0 | 1 | 1 | 2 |

- ENTAILMENT 22건은 모두 근거가 뒷받침했다(unsupported citation 0%).
- NEUTRAL 13건 중 5건을 CONTRADICTION/INSUFFICIENT_EVIDENCE 로 과소·과대 판정했다.
- 결정론 기준선 semantic accuracy 는 61.9%, macro F1 0.559 였다. Judge 가 더 높지만,
  Judge 자체의 정답 일치도 83.3% 이므로 Judge 점수만으로 100% 신뢰하지 않는다.

## 9. 실제 NVIDIA 호출 (현재 프롬프트)

| 항목 | 결과 |
| --- | --- |
| 상태 | **LIVE_VERIFIED** |
| 성공/전체 | **3/3** |
| 평균 지연 | **145,844 ms** (최대 307,546 ms) |
| 토큰 | prompt **1,966** / completion **2,795** |
| JSON 통과 | 3/3 |
| raw unsupported number rate | **7.1%** |
| 가드레일 적용 후 unsupported number rate | **0.0%** |
| 수치 대체 | **1건** (`75%`, `statements.monthly`) |
| 금지 주장 hit | **0** |

핵심: 현재 제품 경로에서는 `sanitize_ai_result()` 가 **중첩된 statements 필드까지** 검사해
근거 없는 `75%` 를 `[확인 필요]` 로 바꿨다. 이 수정 전에는 `statements.monthly` 가 가드레일을
우회했다. 수정 후 회귀 테스트를 추가했고 전체 465개 테스트가 통과했다.

단, 이는 **숫자**에 대한 결과다. “안정성 향상” 같은 정성 주장은 여전히 자동 검증되지 않는다.

## 10. 비용

- 실제 청구 금액: **NOT_MEASURED** — NVIDIA 무료 크레딧/계정 정책에 따라 달라지며 이번
  실행에서 청구서를 확인하지 않았다.
- 기록된 사용량: 생성 prompt 1,966 / completion 2,795 tokens, 3회.
- 심사 호출은 캐시를 사용했으며, 최초 심사 호출의 토큰은 결과 메타데이터에 남아 있다.
- 비용을 0원이라고 주장하지 않는다. 유료 계정이면 콘솔에서 확인해야 한다.

## 11. 실패·미측정 항목

| 항목 | 상태 | 이유 |
| --- | --- | --- |
| Hallucination ≤20% | **FAIL** | 47.6%, 정성 효과·미검증 수치 |
| 품질 사실성 하한 | **FAIL** | 2.65/5, 1~2점 55% |
| 사람 평가자 간 일치도 | **NOT_MEASURED** | 독립 사람 평가자 2인 이상 없음 |
| Windows/macOS GUI 클릭 | **NOT_MEASURED** | 이 환경은 macOS ARM64, 자동 브라우저 클릭 미수행 |
| Linux 실제 배포 E2E | **NOT_MEASURED** | Docker health 는 확인, 운영 배포는 미수행 |
| OmniRoute 경유 | **NOT_CONFIGURED** | 기존 설정·로그 흔적 없음 |
| 정성 효과 자동 검증 | **NOT_MEASURED** | 현재 가드레일은 숫자만 대상 |
| PDF 렌더링 품질 | **NOT_MEASURED** | 파일 생성과 시각 품질을 별도 검증하지 않음 |

테스트 실패는 없다. 2026-11-15 `bash scripts/check.sh` 는 lint·format·**465 passed** 로
종료 코드 0이었다.

## 12. Clean Clone·이식성

2026-11-15 실제 검증:

- 작업 트리를 `.git`·`.venv`·`.env` 없이 새 디렉터리에 스냅샷하고 새 Git 저장소로 clone.
- 새 venv(`Python 3.14.4`)에서 `pip install -e ".[dev,all]"` 성공.
- **465 passed** (28.95s).
- AI 키 없이 `impactnote init` → 업무 기록 → 주간 Markdown 보고서 → 목록 조회 성공.
- Docker 이미지 빌드, `IMPACTNOTE_PORT=18000`으로 컨테이너 실행, `/api/health` 성공.
- macOS 기본 `python3` 3.9.6 으로는 설치 실패(`requires-python >=3.11`)를 재현했다.
  3.11+ 사용 안내가 필요하다는 증거다.

한계: GitHub 원격에 현재 작업 트리를 push하지 않았으므로 **원격 GitHub Clean Clone 자체는
수행하지 못했다.** 대신 동일 파일 집합을 새 Git 저장소로 clone하는 방식으로 검증했다.
CI 는 push 후 `ubuntu/macos/windows`에서 이를 자동 검증하도록 추가했다. Windows 실제 GUI 는
미검증이다.

## 13. 일반화 한계

- 42 claim, 12 문서-코드, 20 성과, 8 귀속은 작다. 신뢰구간이 넓다.
- 품질 20개는 **2026-10-03 Historical 출력**이고, 현재 프롬프트 품질은 live 3개뿐이다.
- 생성·심사 모델이 같은 NVIDIA 호스팅에 있어 독립성에 한계가 있다.
- 통제 저장소는 합성이며 실제 회사 저장소의 언어·도메인을 대표하지 않는다.
- 수치 가드레일은 근거 없는 **숫자**를 막지만, 정성 효과 주장은 막지 못한다.
- “AI 성능이 전반적으로 좋아졌다”거나 “모든 저장소에서 100%”라고 주장하지 않는다.

## 14. 재현

```bash
python -m evals.impact.run --live --out /tmp/impact-live
python -m evals.impact.run --offline --no-judge --out /tmp/impact-offline
```

전체 방법·임계값·표본 정의는 [`ai-evaluation.md`](ai-evaluation.md), NVIDIA 설정은
[`nvidia-provider.md`](nvidia-provider.md), 설치·Clean Clone은
[`installation.md`](installation.md) 에 있다.
