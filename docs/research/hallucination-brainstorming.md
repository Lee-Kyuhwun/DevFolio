# 환각 완화 Brainstorming

작성일: 2026-11-16 · 대상: ImpactNote 성과 생성 파이프라인

> 이 문서는 결과 요약이 아니라 **어떤 대안을 왜 버렸는지**를 남긴다.
> 실제 서브 에이전트를 실행한 것이 아니라, 아래 6개 역할을 독립 검토 관점으로
> 순차 적용했다. 독립성의 한계는 §6에 적었다.

## 1. 목적과 제약

목적: 근거 없는 **정량·정성** 성과 주장을 줄이면서, 근거가 있는 성과의 발견 능력
(Recall)을 유지한다.

제약:

- 기존 `evals/impact/` Ground Truth 와 `sanitize_claims` 를 재사용한다.
- 새 평가 프레임워크·벡터 DB·마이크로서비스를 기본 도입하지 않는다.
- 승인되지 않은 유료 호출·민감 자료 외부 전송·데이터 삭제·공유 브랜치 Push 금지.
- 실측하지 않은 개선율을 만들지 않는다.
- 기존 465개 테스트와 호환한다.

## 2. 조사한 공식 자료

| 자료 | 확인한 내용 | 적용 판단 |
| --- | --- | --- |
| Superpowers brainstorming | 기존 조사 → 다중 대안 → 트레이드오프 → 설계 문서 → 위험 검토 | 그대로 절차화 |
| Superpowers systematic-debugging | 재현 → 입력/검색/생성/검증 단계 추적 → 가설 검증 | 42 claim 역추적에 적용 |
| Superpowers writing-plans | 독립 테스트 가능한 작업 단위, 기대 결과 명시 | Gate 단위·통합·라이브 3단계로 분리 |
| Superpowers test-driven-development | 실패 사례를 먼저 회귀 테스트로 고정 | `tests/test_claims.py` 11+2개 |
| Superpowers verification-before-completion | 실제 실행 결과 없이 완료 선언 금지 | 오프라인·라이브·전체 테스트 결과 첨부 |
| NVIDIA NIM LLM API | OpenAI 호환 `/v1/chat/completions`, `/v1/models` | 기존 `AIService` 경로 유지 |
| NeMo Guardrails fact-checking | Self-check fact-check, AlignScore 기반 groundedness, 출력 차단/보류 | 개념만 참고, 제품 도입 보류 |
| NeMo Retriever | 파싱·임베딩·리랭킹(NV-RerankQA) | 이번 라운드 미도입 |
| NeMo Evaluator | LLM-as-judge, groundedness, answer accuracy, context relevance | 기존 하네스와 중복 → 지표만 참고 |

플러그인은 설치하지 않았다. 방법론만 프로젝트 절차로 변환했다.

## 3. 역할별 제안

### Agent A — Retrieval Architect

제안: 활동-근거 검색을 BM25 + 심볼 검색으로 확장하고, 근거 chunk 에 commit hash·
line range 를 붙인다. 검색 결과를 리랭킹해 프롬프트에 넣는다.

장점: c005·c024·c038 같은 "근거에 없는 기능" 주장을 줄일 수 있다.
단점: 활동 1건 분석에는 검색할 문서가 이미 좁다. 42개 중 12개는 문맥에 근거가
있어도 생긴 효과 주장이라 검색만으로 막히지 않는다. 인덱스·임베딩 운영 비용이 든다.

### Agent B — LLM Generation Engineer

제안: 출력 스키마를 `claims[]`로 바꾸고, 각 claim 에 `evidence_quote`를 강제한다.
`result`는 자유 문자열이 아니라 `{claim, evidence_id}` 배열로 받는다.

장점: 검증 가능한 구조가 된다.
단점: JSON 길이가 늘어 절단 위험이 커지고, 모델이 evidence_quote 를 지어낼 수 있다.
기존 `AIAnalysis.result` 소비자(웹 UI·CLI·보고서)를 모두 바꿔야 한다.

### Agent C — Factuality Researcher

제안: Atomic Claim 분해 + NLI/LLM Judge + Semantic Entailment. 각 claim 을
SUPPORTED / CONTRADICTED / UNSUPPORTED / INSUFFICIENT_EVIDENCE 로 판정한다.

장점: 의미 반대(c034, c037)와 미묘한 불일치를 잡을 수 있다.
단점: claim 1건당 1회 호출 → 비용·지연 증가. Judge 자체 오탐을 별도 평가해야 한다.
한국어 NLI 품질을 이번 라운드에서 검증하지 않았다.

### Agent D — AI Evaluation Engineer

제안: Baseline/Variant 를 동일 입력·동일 모델·동일 출력 계약으로 비교하고,
표본 수와 95% 구간을 함께 보고한다. 0건이면 Wilson 구간을 쓴다.

장점: 작은 표본에서 "0% 달성"으로 오독하는 것을 막는다.
단점: 3건 라이브 표본은 여전히 작다. 프롬프트·Gate 를 동시에 바꾸면 교란된다.

### Agent E — Skeptical Reviewer

반론:

1. "효과 표현 목록"은 평가셋에 과적합될 수 있다. 42개 문장의 표현을 외우면
   새 문장에서 재현율이 떨어진다.
2. 근거 있는 효과 주장을 차단하면 Recall 이 줄고, 사용자는 빈 결과를 받는다.
3. "근거에 있다"는 것은 그 문장이 효과를 **입증**한다는 뜻이 아니다. 같은 단어가
   있다고 지원으로 보면 false accept 가 생긴다.
4. Gate 를 제품에 넣으면 사용자가 쓴 효과 문장까지 지울 수 있다.
5. Judge 를 제품 경로에 넣지 않으면 의미 반대는 여전히 못 잡는다.

재검토 결과:

- 1 → 표현 목록을 "효과 술어 + 대상"의 일반 규칙으로 만들고, 근거 문장에 같은
  효과 표현이 있을 때만 지원으로 인정했다. 평가셋 ID를 코드에 넣지 않았다.
- 2 → 보존율을 별도 지표로 측정했다(10/10). 차단은 근거 없는 문장만.
- 3 → 부정 표현("측정되지 않음")을 명시적 UNSUPPORTED 로 처리하고, 수치+단위를
  함께 대조하도록 수정했다. 이 수정은 실제 live 실행에서 발견했다.
- 4 → Gate 는 `source in {ai, analysis, git}` 인 기계 생성 성과에만 적용했다.
  사용자가 직접 쓴 성과는 사용자 주장으로 유지한다.
- 5 → 인정. 이번 라운드의 남은 한계로 문서화했다.

### Agent F — Engineering Architect

제안: 새 서비스 없이 `impactnote/core/claims.py` 하나를 추가하고, 기존
`sanitize_ai_result`·`_achievement_lines`·`ai_stage.enrich_with_ai` 에 연결한다.

장점: 의존성 0, 결정론, 테스트 가능, 오프라인 동작.
단점: 한국어 규칙 유지보수 부담. 의미 반대·기능 존재는 못 잡는다.

## 4. 대안 비교

| 접근 | 환각 감소 | Recall 유지 | 비용 | 지연 | 복잡도 | 이번 판단 |
| --- | --- | --- | --- | --- | --- | --- |
| A. Hybrid Retrieval + Rerank | 중 | 중 | 중 | 중 | 높음 | 보류 |
| B. 구조화 Claim 스키마 | 중 | 중 | 낮음 | 낮음 | 중 | 부분 채택(프롬프트 규칙) |
| C. Atomic Claim + NLI/Judge | 높음 | 중 | 높음 | 높음 | 중 | 보류(Judge 제품화) |
| D. 결정론 효과 Gate | 중~높음 | 높음(측정) | 0 | <1ms | 낮음 | **채택** |
| E. Generate → Critique → Repair | 높음 | 중 | 매우 높음 | 매우 높음 | 높음 | 기각 |
| F. Abstention(보류) | 높음 | 낮음 위험 | 0 | 0 | 낮음 | **부분 채택**(문장 삭제+목록) |

## 5. 실험 후보 선정

우선순위:

1. **Variant A — 결정론 효과 Gate**: 비용 0, 즉시 측정 가능, 12개 표적.
2. **Variant B — 프롬프트 + Gate**: 프롬프트만으로 되는지 확인.
3. **Variant C — 수치 단위 대조**: live 에서 발견한 `80%` vs `80ms` 결함 수정.
4. **Variant D — 독립 Judge**: 비용 때문에 이번 라운드에서는 기존 42 claim 심사
   결과(83.3%)를 참고만 하고 제품 경로에는 넣지 않았다.
5. **Variant E — Retrieval/Rerank**: 데이터가 좁아 효과를 분리 측정하기 어렵다.
   다음 라운드 과제로 남겼다.

## 6. 독립성의 한계

- 6개 역할을 실제 병렬 에이전트로 실행하지 않았다. 같은 세션에서 역할을 바꿔
  검토했으므로, 이해충돌(자기 제안 옹호) 가능성이 있다.
- 외부 전문가 리뷰·사람 2인 이상의 평가자 일치도는 없다.
- 따라서 이 문서의 판단은 **재현 가능한 코드·테스트·측정값**으로만 뒷받침한다.

## 7. 최종 결정

- 채택: 결정론 효과 Gate + 프롬프트 규칙 + 수치 단위 대조 + 보고서 재검증.
- 보류: NeMo Guardrails, NeMo Retriever, 제품 경로 Judge, Repair loop.
- 이유: 이번 표본에서 12개 효과 주장을 0건 통과·10개 보존으로 막았고, 새 의존성·
  유료 호출 없이 재현됐다. 나머지 8개 claim 유형은 별도 실험이 필요하다.
