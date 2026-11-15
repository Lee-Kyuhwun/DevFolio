# NVIDIA 모델·기술 비교

작성일: 2026-11-16 · Provider: NVIDIA NIM (`https://integrate.api.nvidia.com/v1`)

> 모델 목록은 실제 `/v1/models` 호출 결과다. 성능 비교는 **이번 라운드에서 새로
> 수행하지 않은 항목과 수행한 항목을 구분**한다. 비용은 NIM 응답에 USD가 없어
> `NOT_MEASURED` 다.

## 1. 접근 확인

| 항목 | 결과 |
| --- | --- |
| 인증 | 기존 keyring 키 사용, 키 값은 출력·문서에 남기지 않음 |
| `GET /v1/models` | HTTP 200, 모델 83개 |
| `openai/gpt-oss-20b` | 목록에 존재 |
| `minimaxai/minimax-m3.1-flash` | 목록에 존재 |
| `z-ai/glm-5.3-flash` | 목록에 존재 |
| `meta/llama-3.3-70b-instruct` | 목록에 없음. 과거 410 Gone 이력과 일치 → 후보에서 제외 |

## 2. 역할 분리

| 역할 | 모델 | 이유 |
| --- | --- | --- |
| 생성 | `openai/gpt-oss-20b` | 기존 평가·프로덕트 경로와 동일. 2026-11-15/16 실호출 성공 |
| 독립 심사 | `minimaxai/minimax-m3.1-flash` | 생성 모델과 다른 계열. claim/doc/quality 심사에 사용 |
| 심사 fallback | `z-ai/glm-5.3-flash` | 1차가 503/429 일 때만 사용. 실제 사용 모델을 결과에 기록 |
| 결정론 Gate | 없음(코드) | LLM Judge 대체가 아니라 저장 직전 Hard Gate |

`evals/impact/judge.py` 는 `temperature=0`, 180초 timeout, 최대 3회 재시도,
Provider fallback 비활성(`DEVFOLIO_AI_PROVIDER_FALLBACK=0`)으로 호출한다.

## 3. 이번 라운드 실제 호출

### 3.1 생성 (활동 3건, 2026-11-16)

| ID | 상태 | 지연 | prompt tokens | completion tokens | JSON |
| --- | --- | ---: | ---: | ---: | --- |
| `live_deploy` | LIVE_VERIFIED | 173,557 ms | 775 | 1,722 | OK |
| `live_cache` | LIVE_VERIFIED | 51,909 ms | 760 | 1,228 | OK |
| `live_team` | LIVE_VERIFIED | 37,923 ms | 740 | 1,015 | OK |
| 합계/평균 | 3/3 | 87,796 ms | 2,275 | 3,965 | 3/3 |

- 같은 모델·프롬프트로 2026-11-16에 두 번 실행했다. 첫 실행은 평균 120,345 ms,
  두 번째는 87,796 ms였다. `live_deploy`는 90.7초 → 173.6초로 변동했다.
- 180초 timeout 에 근접하는 호출이 있으므로, 재시도·cooldown 정책을 바꾸면 실패율이
  달라질 수 있다. 지연은 입력 길이만으로 설명되지 않았다.

### 3.2 독립 심사 (2026-11-15 Historical)

| 지표 | 결과 | 표본 |
| --- | --- | ---: |
| Claim 분류 accuracy | 83.3% | 42 |
| Claim macro F1 | 0.710 | 42 |
| 문서·코드 accuracy | 83.3% | 12 |
| 품질 평균 | 3.68/5 | 20 |
| 사실성 평균 | 2.65/5 | 20 |

- 이 값은 `minimaxai/minimax-m3.1-flash` 심사 결과다. 이번 라운드에서 새로 심사하지
  않았으므로 Historical 값으로 표시한다.
- 심사 모델 자체의 오탐률은 사람 라벨과 비교해 측정하지 않았다. 42개 라벨은
  Ground Truth 로 고정되어 있지만, Judge 오류와 생성 오류를 분리한 분석은 없다.

## 4. 비용

| 항목 | 값 |
| --- | --- |
| API 과금 단가 | NOT_MEASURED (응답에 비용 필드 없음) |
| 이번 라운드 생성 토큰 | 5,945 (prompt 2,275 + completion 3,670) |
| 이번 라운드 생성 호출 | 3회 |
| 심사 호출 | 2026-11-15 캐시 재사용, 이번 라운드 추가 호출 없음 |

정확한 USD 비용은 NVIDIA 계정의 과금 내역에서 확인해야 한다. 이 문서는 추정치를
만들지 않는다.

## 5. 모델 선택 근거와 한계

선택 근거:

1. 세 모델 모두 2026-11-16 현재 `/v1/models` 에서 접근 가능함을 확인했다.
2. 생성 모델은 기존 프롬프트·출력 계약과 호환되고 3/3 JSON 파싱에 성공했다.
3. 심사 모델은 생성 모델과 다른 계열로, 자기 선호 편향을 줄이려는 기존 설계를
   유지했다.
4. `meta/llama-3.3-70b-instruct` 는 접근 불가이므로 후보에서 제외했다.

한계:

- **모델 간 품질 A/B를 이번 라운드에서 수행하지 않았다.** `gpt-oss-20b` 대 다른
  모델의 환각률 비교는 `NOT_MEASURED` 다.
- 생성 모델 1개·표본 3건이므로 모델 선택을 통계적으로 정당화하지 않는다.
- 심사 모델의 한국어 판정 품질을 사람 라벨과 비교하지 않았다.
- 비용·rate limit 여유는 계정 정책에 따라 달라진다. 3/3 성공이 지속성을 보장하지
  않는다.

## 6. NeMo 기술 검토 결과

| 기술 | 검토 | 이번 판단 |
| --- | --- | --- |
| NeMo Guardrails fact-checking | Self-check/AlignScore 기반 groundedness, 차단·보류 rail | 별도 런타임·한국어 캘리브레이션 부재로 보류 |
| NeMo Retriever | 파싱·임베딩·리랭킹 | 활동 단위 분석에는 과함. 보류 |
| NeMo Evaluator | LLM-as-judge, groundedness, context relevance | 기존 `evals/impact/` 와 중복. 지표 정의만 참고 |

이번 개선은 NVIDIA **모델**은 사용하되, NeMo **제품**은 도입하지 않았다. 도입
여부는 [`../decisions/ADR-hallucination-mitigation.md`](../decisions/ADR-hallucination-mitigation.md)
의 Revisit Conditions 로 남긴다.
