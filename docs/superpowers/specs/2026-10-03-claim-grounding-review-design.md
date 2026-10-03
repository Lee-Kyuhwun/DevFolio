# 문장별 근거 검사와 사람 승인 — 설계

- 상태: 설계 검토 중
- 작성: 2026-10-03
- 선행: [에이전트 실수 기록부](2026-10-03-agent-incident-log-design.md)
- 후속: [AI 심사 신뢰도 측정](2026-10-03-judge-reliability-eval-design.md)이 이 문서의 검사기를 사용한다

## 1. 배경

- 생성 프롬프트는 "evidence 밖의 사실은 추가하지 말 것"을 계약으로 건다. 지금 이 계약을 확인하는 장치는 심사 모델의 `factuality` 점수 하나다. 심사 모델도 생성 모델과 같은 착각을 할 수 있다.
- `_validate_generated_output`은 형식만 검사한다(bullet 수, 문장 수, 섹션 존재).
- 웹 API는 생성 결과를 **사람 확인 없이 바로 저장**한다. `generate_experience_summary`와 `generate_project_summary`가 생성 직후 `pm.save_project_summary`를 호출한다.

## 2. 목표와 비목표

목표
1. evidence에 없는 **숫자와 기술명**을 코드로 찾는다. 결정적이고 비용이 들지 않는다.
2. 찾은 결과를 refine 피드백으로 돌려, AI가 스스로 고칠 기회를 준다.
3. 최종 채택은 사람이 한다. 문장마다 근거를 보고 적용, 편집 후 적용, 버리기 중 하나를 고른다.
4. 사람의 결정을 기록해, 이후 측정과 프롬프트 개선에 쓴다.

비목표
- 의미 수준의 사실 검증(예: "팀 리드"와 "팀원"의 차이). 한계로 명시한다.
- 요약 이외의 모드(과제 bullet, 케이스 스터디). 요약에서 검증한 뒤 확장한다.
- 근거 없는 표현이 있을 때 자동으로 차단하는 것.

## 3. 핵심 결정과 검토한 대안

| 결정 | 이유 | 버린 대안 |
|---|---|---|
| 검사는 결정적 코드로 한다 | 심사 모델과 다른 방식으로 실패해야 서로 보완된다. 비용 0, 결과 재현 가능 | LLM 사실 검증(심사 모델과 같은 약점, 호출 비용), 로컬 NLI 모델(무거운 의존성, 한국어 품질 불확실) |
| 검사 대상은 숫자와 라틴 문자 토큰 | 채용 문서에서 가장 해로운 지어낸 사실은 수치와 기술명이다. 한국어 문장 속 라틴 문자 토큰은 대부분 기술명·고유명사다 | 한국어 고유명사 추출(형태소 분석기 의존성 필요, 오탐 많음) |
| 위반은 차단하지 않고 표시만 한다 | 표기 차이("레디스"와 "Redis"), 단위 변환("1초"와 "1000ms") 같은 오탐이 있다. 최종 판단은 사람이 한다 | 자동 차단(오탐 때문에 정상 결과까지 막힘) |
| 생성 결과는 초안으로만 반환하고, 사람이 채택해야 저장한다 | 사람 확인 없는 저장 경로를 없앤다 | 저장 후 되돌리기(사람이 확인하지 않아도 저장된 상태가 됨) |
| 후보 선택은 근거 없는 표현 수를 먼저 비교한다 | 근거 없는 표현이 있는 후보가 점수만으로 이기지 못하게 한다 | 점수에 페널티 가중치 추가(임의 상수가 생김) |

## 4. 구성 요소

### 4.1 `devfolio/core/claim_check.py` (새 모듈)

순수 함수로만 구성하고 AI에 의존하지 않는다.

- `build_evidence_index(evidence: PortfolioEvidence) -> EvidenceIndex`
  - `model_dump()` 결과의 모든 문자열 값을 `(필드 경로, 정규화 텍스트)` 목록으로 평탄화한다.
  - 필드 경로 예: `results[0]`, `tasks[1].result`
- `check_claims(text: str, index: EvidenceIndex) -> ClaimReport`
  - **문장 분리**: bullet 줄 단위. bullet이 없으면 문장 종결 기준
  - **숫자 claim 추출**: 숫자와 선택 단위(`%`, `배`, `x`, `ms`, `초`, `분`, `시간`, `일`, `명`, `건`, `개`, `회`, `만`, `억`, `원`, `TPS`, `RPS` 등)
  - **숫자 정규화**: 쉼표 제거, 전각 숫자를 반각으로
  - **기술명 claim 추출**: `[A-Za-z][A-Za-z0-9.+#-]+` 형태(2자 이상), 대소문자 무시
  - **판정**: 정규화한 claim이 evidence 텍스트 어딘가에 있으면 지원됨으로 보고, 출처 필드 경로를 기록한다.
- 모델 (Pydantic)
  - `Claim { text, kind: "number" | "term", supported: bool, sources: list[str] }`
  - `SentenceCheck { text, claims: list[Claim] }`
  - `ClaimReport { sentences: list[SentenceCheck] }`
  - `ClaimReport.unsupported`는 지원되지 않는 claim 목록을 반환하는 property다.

### 4.2 `AIService` 통합

- **refine 피드백**: refine을 실행하는 경로(s1_refine, hybrid, 최종 수정)의 피드백에 "근거에 없는 표현: X, Y. 삭제하거나 evidence에 있는 표현으로 바꿀 것"을 추가한다.
- **후보 선택**: 정렬 키를 `(근거 없는 claim 수 오름차순, 심사 점수 내림차순)`으로 바꾼다.
- **새 메서드** `generate_project_summary_draft(...) -> SummaryDraft { text, review, claims }`
  - 기존 `generate_project_summary`의 반환 타입은 유지한다. CLI가 사용 중이다.
  - CLI는 생성 후 근거 없는 표현이 있으면 경고를 출력한다.

### 4.3 웹 API

| 엔드포인트 | 변경 |
|---|---|
| `POST /api/experiences/{id}/generate-summary` | 저장하지 않고 `{status, draft: {text, claims, review_scores}}`를 반환 |
| `POST /api/projects/{id}/generate-summary` | 위와 같음 |
| `POST /api/draft/generate-summary` | 원래 저장하지 않는다. 응답에 `claims`만 추가 |
| `POST /api/experiences/{id}/summary/decision` (신규) | 본문: `{action: "accepted" \| "edited" \| "discarded", draft_text, final_text}`<br>`accepted`/`edited`면 저장하고 결정 기록, `discarded`면 기록만 |

`/projects/{id}/summary/decision`도 같은 형태로 둔다.

### 4.4 화면 (`studio_v2.js`)

- 생성이 끝나면 검토 패널을 연다.
  - 문장 목록을 보여준다.
  - 근거 없는 claim은 빨간 강조와 "근거 없음" 표시
  - 근거가 있는 문장에는 출처 필드를 칩으로 표시
- 편집 가능한 텍스트 영역과 [적용] [버리기] 버튼을 둔다. 편집했는지는 `draft_text`와 비교해 자동 판별한다.
- 문장과 claim은 `textContent`로만 넣는다(`AGENTS.md`의 XSS 금지 규칙).

### 4.5 결정 기록 `review_decisions.jsonl`

- 위치는 `DEVFOLIO_DATA_DIR`, 파일 권한은 `0o600`이다.
- 레코드 필드: `ts`, `project_id`, `mode`, `action`, `draft_text`, `final_text`, `unsupported_in_draft`, `unsupported_in_final`
- 원문을 저장하는 이유는 사람이 무엇을 고쳤는지 나중에 분석하기 위해서다. 로컬에만 저장하고 동기화 대상에서 제외한다.

## 5. 데이터 흐름

```
evidence ─▶ 생성 ─▶ 근거 검사 ─▶ (refine 피드백) ─▶ 후보 선택 ─▶ 초안 + 검사 보고서
   ─▶ 검토 패널 ─▶ 사람의 결정 ─▶ 저장 + review_decisions.jsonl
```

## 6. 오류 처리

- 근거 검사에서 예외가 나도 생성은 실패시키지 않는다. 경고 로그를 남기고 `claims: null`을 반환하며, 화면에 "근거 검사 불가"를 표시한다.
- 결정 기록 쓰기에 실패해도 저장은 진행하고 경고 로그를 남긴다.

## 7. 테스트

| 수준 | 내용 |
|---|---|
| 단위 (`claim_check`) | 숫자 단위·쉼표·전각, 대소문자 무시, 출처 경로, 한글만 있는 문장은 claim 없음, bullet 분리 |
| 서비스 | 모킹한 AI가 지어낸 수치를 넣으면 refine 피드백에 그 수치가 포함됨, 후보 정렬 순서 |
| API | 생성 후 저장되지 않음, `accepted`/`edited`는 저장되고 기록 1줄, `discarded`는 저장되지 않음 |
| 화면 | 브라우저에서 수동 확인, 스크린샷을 `docs/images/`에 저장 |

## 8. 역할 분담

| 일 | 담당 |
|---|---|
| 무엇을 사실 주장(claim)으로 볼지 | 사람 |
| 오탐 정책(차단하지 않고 표시) | 사람 |
| 최종 채택 | 사람 |
| 검사기, API, 화면 구현과 테스트 | AI |
| 근거 검사 실행 | 결정적 코드 |

## 9. 한계

- 의미 수준의 왜곡은 잡지 못한다. 사람의 검토가 남아야 하는 이유다.
- 표기 차이 때문에 오탐이 생긴다. 오탐률은 [심사 신뢰도 측정](2026-10-03-judge-reliability-eval-design.md)에서 잰다.

## 10. 성공 기준

- 지어낸 수치·기술명을 넣은 테스트 초안에서 해당 claim이 모두 근거 없음으로 표시된다.
- 웹 API에서 사람 확인 없이 요약을 저장하는 경로가 없다.
- 모든 채택과 버림이 `review_decisions.jsonl`에 기록된다.
- `scripts/check.sh`와 CI가 통과한다.
