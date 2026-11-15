# 정성 효과 Hard Gate — 실험 기록

작성일: 2026-11-16
데이터셋: `impactnote-ai-eval-1.0.0` (SHA-256 앞 16자 `6cf68ed945bc6b91`)
기준 코드: `main` @ `6e6ce68` + 이번 작업 트리 변경
환경: macOS (darwin), Python 3.14.4, `./.venv`

## 1. 실험 가설

| ID | 가설 | 측정 |
| --- | --- | --- |
| H1 | 효과 주장만 문장 단위로 근거와 대조하면, 근거 없는 정성 효과를 저장 전에 막을 수 있다 | false accept rate, retention |
| H2 | Gate 는 근거 있는 효과 주장을 과도하게 차단하지 않는다 | false rejection, retention |
| H3 | 프롬프트 강화만으로는 부족하다 | live raw 효과 주장 수 |
| H4 | 수치 검증은 값뿐 아니라 단위를 대조해야 한다 | `80%` vs `80ms` 회귀 테스트 |
| H5 | 사용자가 확인한 AI 성과도 보고서에서 재검증해야 한다 | 보고서 본문 재유입 테스트 |

H1·H2·H4·H5는 코드·테스트로 검증했다. H3는 live 3건에서 관찰했다. 표본이 작아
통계적 결론이 아니라 **방향 확인**이다.

## 2. Baseline 과 Variant

| 이름 | 구성 |
| --- | --- |
| Baseline | 현재 프롬프트 + 수치 가드레일(`sanitize_ai_result`) |
| Variant A | Baseline + 결정론 효과 Gate(`claims.gate_result`) |
| Variant B | Variant A + 프롬프트 효과 규칙 + 수치 단위 대조 |
| Variant C | 보고서 생성 시 기계 생성 성과 재검증 |

한 번에 한 조건만 바꿨다. Variant A는 같은 raw 출력에 두 저장 방식을 적용해
Gate 의 증분 효과를 분리했다. Variant B는 프롬프트가 이미 반영된 상태에서
3건을 새로 호출했고, Baseline은 같은 raw 출력에 수치 가드레일만 적용해 계산했다.

## 3. 평가 데이터

- Claim 42개: Historical NVIDIA `gpt-oss-20b` 생성문 30 + 경계 12.
- 그중 효과 주장 22개(52.4%): 근거 있음 10, 근거 없음 12.
- Live 활동 3개: 배포 자동화, Redis 캐시, 결제 API 설계.
- 나머지 20개 claim 은 효과 주장이 아니므로 Gate 분모에서 제외하고 coverage 로
  보고했다.

## 4. 실험 명령

```bash
# 1) 전체 회귀
./.venv/bin/python -m pytest -q

# 2) 오프라인 Gate 측정 (외부 호출 없음)
./.venv/bin/python -m evals.impact.run --offline --no-judge --out /tmp/impact-gate-offline

# 3) 실제 NVIDIA 3건 A/B (활동당 1회 호출)
./.venv/bin/python -m evals.impact.live_ab --out /tmp/impact-live-ab-v2
```

재현 환경:

- `DEVFOLIO_AI_PROVIDER_FALLBACK=0` (live_ab 가 설정)
- 생성 모델 `nvidia_nim/openai/gpt-oss-20b`
- `max_tokens=1600`, `json_mode=True`
- 심사 모델은 이번 라운드에서 호출하지 않음(비용 절감, Gate 는 결정론)

## 5. 결과

### 5.1 Gate 단위 평가 (42 claims, 오프라인)

| 값 | 결과 |
| --- | ---: |
| 전체 claim | 42 |
| 효과 주장 | 22 (52.4%) |
| 근거 있는 효과 주장 | 10 |
| 근거 없는 효과 주장 | 12 |
| False accept | **0 / 12** |
| False reject | **0 / 10** |
| Retention | **100%** |
| 통과 정밀도 | **100%** |
| False accept Wilson 95% CI | 0 – 24.3% |

- 차단 12건: c002, c003, c004, c010, c011, c019, c023, c025, c031, c035, c036, c039.
- 보존 10건: c007, c008, c012, c013, c014, c017, c018, c022, c027, c042.
- 0/12는 "오류율 0%"가 아니다. 95% 상한 24.3%다.

### 5.2 실제 NVIDIA A/B (최종 실행)

| ID | Baseline 저장된 근거 없는 효과 | Variant 저장 | Gate 차단 | 지연 |
| --- | ---: | ---: | ---: | ---: |
| live_deploy | 2 | 0 | 3 | 173,557 ms |
| live_cache | 1 | 0 | 1 | 51,909 ms |
| live_team | 1 | 0 | 1 | 37,923 ms |
| **합계** | **4** | **0** | **5** | 평균 87,796 ms |

- 성공 3/3, JSON 3/3, 금지 패턴 hit 0.
- 토큰: prompt 2,275 / completion 3,965.
- Baseline 4건은 Wilson 95% CI 0–49.0%다(4건 표본).
- `gate_blocked_claims`(5)가 Baseline 의 고유 문장 수(4)보다 큰 이유는 같은
  문장이 `statements` 등 여러 필드에 중복 등장해 필드 단위로 차단되기 때문이다.
- 첫 실행(2026-11-16 00:12, 수치 단위 수정 전)도 Baseline 4 → Variant 0이었다.
  두 실행을 합치면 6회 호출에서 Baseline 8건, Variant 0건이다. 같은 모델·프롬프트의
  독립 반복이며, 표본은 여전히 6건이다.

### 5.3 실제 생성에서 관찰된 효과 주장

- `live_deploy` `self_review`: "운영 효율성과 안정성을 크게 향상시켰습니다." → 근거
  없음, 차단.
- `live_deploy` `executive`: "배포 시간을 15분 단축" → 기록에 15분 없음, 수치 가드레일
  + 효과 Gate 차단.
- `live_cache` `executive`: "응답 시간을 80% 이상 단축" → 근거는 `200ms → 80ms`.
  80은 ms 값이므로 80%는 파생 수치. **첫 실행에서 통과했고, 단위 대조 수정 후 차단.**
- `live_team`: 결과 기록이 비어 있어 효과 주장이 생성되지 않았다. 3건 중 1건은
  보류가 자연스럽게 동작한 사례다.

### 5.4 회귀 테스트

`tests/test_claims.py` 13개:

- 근거 없는 효과 차단, 부정 표현 처리, 수치 없는 효과, 구현 사실 보존.
- 중첩 dict 필드 경로.
- AI 저장 경로 차단(HTTP), 기록된 측정값이 있는 효과 보존.
- 보고서 재유입 차단, 근거 있는 효과 보존, 수동 성과 미삭제.
- `80%` vs `80ms`, `10분` vs `10m`.

전체: **480 passed** (기존 465 + 신규 15: `test_claims.py` 13, `test_intel.py` 1,
`test_impact_eval.py` 1). `make check`의 ruff/format 포함.

산출물: `evals/impact/results/effect-gate-2026-11-16.json`,
`evals/impact/results/live-ab-2026-11-16.json`.

## 6. 실패 실험과 원인

| 실패 | 원인 | 조치 |
| --- | --- | --- |
| 첫 live 실행이 295초에 타임아웃 | 3회 호출이 각 90–176초, eval 이 마지막에만 파일 기록 | `live_ab.py` 로 행 단위 저장, 백그라운드 실행 |
| `80%`가 `80ms` 근거로 통과 | 수치 비교가 값만 사용 | `(값, 정규화 단위)` 대조, 회귀 테스트 |
| 보고서 테스트에서 효과가 남음 | 근거 목록에 성과 자신의 `result`가 포함되어 자기 지지 | 효과 Gate 는 외부 근거(evidence+activity)만 사용 |
| AI 테스트에서 기록된 측정값이 차단됨 | `activity.result`가 sources 에 없었음 | sources 에 사용자 기록 결과 추가 |

## 7. 통계적 불확실성

- Gate 0/12: Wilson 95% CI 0–24.3%.
- Live 0/4: Wilson 95% CI 0–49.0%.
- 두 실행 합산 0/8: 상한은 약 32%다.
- Historical 47.6% (20/42): 95% CI 33.3–61.9%.
- 따라서 "환각률 5% 이하 달성"은 **주장하지 않는다.** 효과 주장 부분집합에서
  저장된 근거 없는 주장이 0건이라는 것과, 전체 파이프라인 환각률이 5%라는 것은
  다르다.

## 8. 채택 여부

| Variant | 채택 | 이유 |
| --- | --- | --- |
| A. 결정론 효과 Gate | **채택** | 12/12 차단, 10/10 보존, 비용 0 |
| B. 프롬프트 + 단위 대조 | **채택** | live 에서 효과 주장 생성 자체를 줄이고, 파생 수치 차단 |
| C. 보고서 재검증 | **채택** | 확인 후 재유입 경로 차단 |
| D. 제품 경로 Judge | 보류 | 비용·지연·한국어 캘리브레이션 미검증 |
| E. Retrieval/Rerank | 보류 | 효과 주장 12개에는 불필요, 기능 존재 주장에 필요 |
| F. Repair loop | 기각 | 새 주장 생성 위험 |

## 9. 측정하지 못한 항목

- USD 비용 (NIM 응답에 비용 필드 없음).
- 사람 2인 이상의 평가자 일치도.
- Judge 모델의 오탐률(사람 라벨 대비).
- 다른 도메인·문체에서의 효과 표현 재현율.
- 기능 존재·의미 반대·기여 귀속 주장의 개선율.
- Windows GUI, 실제 GitHub 전체 앱 Clean Clone.
