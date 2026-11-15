# Agent A — Evaluation Auditor

감사일: 2026-11-15 · 대상: `evals/impact/` · 결과 파일: `evals/impact/results/latest.json`

## 범위

- 지표 정의·분자·분모가 코드와 문서에서 일치하는가
- Ground Truth 표본 수와 결과 표본 수가 일치하는가
- 최신 결과의 산술을 독립적으로 재계산할 수 있는가
- 임계값 적용과 전체 판정이 일관적인가

## 확인한 증거

1. `dataset.json` 로드:
   - claim 42 (ENTAILMENT 22, NEUTRAL 13, CONTRADICTION 3, INSUFFICIENT_EVIDENCE 4)
   - doc-code 12 (MATCH 3, PARTIAL 2, MISMATCH 3, NOT_IMPLEMENTED 3, INSUFFICIENT 1)
   - achievement 12 + non-achievement 8, attribution 8, live 3, quality 20
2. `latest.json`:
   - hallucination N=42, supported 22, contradicted 3, unsupported 17
   - combined = (17+3)/42 = **0.47619** → 47.6%
   - verdict `FAIL` (임계값 20%)
3. 결과 표본:
   - extraction 20 경로, TP 12/FP 0/FN 0 → P/R/F1 1.0
   - doc-code N=12, accuracy 10/12 = 83.3%, macro F1 0.839
   - semantic N=42, accuracy 35/42 = 83.3%, macro F1 0.710
   - attribution N=8, exact 8/8 = 100%
   - quality N=20, mean 3.68, factual 2.65, low-factuality 11/20 = 55%
4. `tests/test_impact_eval.py` 및 전체 `pytest`: **465 passed**.

## 판정

**계산·표본 일치: PASS.** 산술 오류, 분모 0의 100% 처리, 라벨 혼용은 발견하지 못했다.

## 발견 사항

1. **품질 사실성 하한은 1차 결과 확인 후 추가됐다.**
   - 최초에는 평균 3.5만 게이트였다. 1차 결과에서 평균 3.68·사실성 2.65·저사실성 55%가
     나온 뒤 사실성 하한을 추가했다.
   - 이는 사후 기준 변경이므로 결과 문서에 명시했다. “사전 등록된 단일 기준”이라고
     주장하지 않는다.
2. **전체 판정 `CONDITIONAL PASS`는 두 지표 FAIL을 숨기지 않는다.**
   - 코드 정책은 실패 1~2개일 때 `CONDITIONAL PASS`, 3개 이상일 때 `FAIL`이다.
   - 결과 문서와 README에 Hallucination·품질 FAIL을 별도 표기했다.
3. **표본 독립성**
   - 85개 라벨 행은 85개의 독립 프로젝트가 아니다. claim 42개는 같은 생성문의 복수 claim을
     포함한다. 문서에 이 한계를 적었다.
4. **정성 주장**
   - 수치 가드레일은 숫자만 대상이다. “안정성 향상” 같은 정성 효과는 Hallucination 집계에
     포함되지만 자동으로 차단되지 않는다.

## 잔여 위험

- 95% CI는 42개 claim 기준이며 넓다(33.3–61.9%).
- 품질 20개는 Historical 출력이다.
- 사람 평가자 간 일치도는 `NOT_MEASURED`.

## 결론

지표 계산은 재현 가능하고 문서와 일치한다. 다만 **AI 품질이 통과했다는 결론은 지지하지
않는다.** Hallucination 47.6%와 사실성 2.65/5는 FAIL이다.
