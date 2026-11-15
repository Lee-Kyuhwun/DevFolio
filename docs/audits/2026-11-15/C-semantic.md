# Agent C — Semantic Evidence Auditor

감사일: 2026-11-15 · 대상: `evals/impact/dataset.json`, `evals/impact/judge.py`

## 범위

- 인용 근거가 실제 claim을 뒷받침하는가
- 수치 claim에 벤치마크 없이 ENTAILMENT를 주지 않았는가
- CONTRADICTION과 NEUTRAL/INSUFFICIENT를 구분했는가
- Judge의 정확도를 Ground Truth와 비교했는가

## 표본 감사

| ID | Claim | 근거 | Gold | 판단 |
| --- | --- | --- | --- | --- |
| c031 | 캐싱으로 응답 시간 70% 단축 | `lru_cache` 추가, 벤치마크 없음 | NEUTRAL | 타당. 캐시 도입은 확인되지만 70%는 입증 불가 |
| c034 | PostgreSQL 사용 | 설정·코드는 SQLite | CONTRADICTION | 타당 |
| c001 | 1인 팀으로 구축 | role=백엔드, team_size=4 | CONTRADICTION | 타당 |
| c039 | 고가용성 아키텍처 | 단일 인스턴스, 이중화 없음 | NEUTRAL | **논란 가능**. CONTRADICTION에 더 가깝다 |

## 집계 감사

- N=42, accuracy 35/42 = 83.3%, macro F1 0.710.
- ENTAILMENT 22건 중 unsupported citation **0%** — 근거 없이 ENTAILMENT로 인정한 사례는
  집계상 없다.
- CONTRADICTION 3건 모두 탐지(recall 100%).
- NEUTRAL 13건 중 2건을 CONTRADICTION, 3건을 INSUFFICIENT로, INSUFFICIENT 4건 중 1건을
  CONTRADICTION, 1건을 NEUTRAL로 오분류.

## 발견 사항

1. **c039 라벨 모호성**: “고가용성 아키텍처” vs “단일 인스턴스·이중화 없음”은 NEUTRAL보다
   CONTRADICTION이 자연스럽다. 다만 이 라벨을 바꾸면 결과가 달라지므로, 동결 데이터셋을
   사후 수정하지 않고 잔여 라벨 위험으로 기록했다.
2. **행별 예측 미보존**: 커밋된 `latest.json`은 집계·confusion만 저장하고 claim별 예측·이유를
   저장하지 않는다. 전체 행 단위 재감사에는 `/tmp` 원본 결과가 필요하다.
   재현성을 높이려면 향후 `rows`(id/gold/predicted/reason)를 결과에 포함해야 한다.
3. **Judge 독립성**: Judge 정확도 자체가 83.3%이므로 Judge 점수를 정답으로 대체하지 않았다.

## 결론

Semantic 83.3%는 “근거 없는 인용 0%”와 “CONTRADICTION 100% 탐지”를 포함하지만, 라벨 모호성과
작은 표본 때문에 **PASS이나 제한적**이다. c039류 경계 사례는 사람 검토가 필요하다.
