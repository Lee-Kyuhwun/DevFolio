# ImpactNote 기술 포트폴리오

작성일: 2026-11-16
이 문서는 제품 기능이 아니라 **개발 기록의 별도 산출물**이다. 저장소의 코드·테스트·
평가 결과로 확인되는 내용만 담았다.

- 상세 케이스: [`../engineering/problem-solving-cases.md`](../engineering/problem-solving-cases.md)
- 개발사: [`../engineering/development-history.md`](../engineering/development-history.md)
- 증거 매트릭스: [`evidence-index.md`](evidence-index.md)
- 기존 케이스 스터디: [`../03-portfolio-case-study.md`](../03-portfolio-case-study.md)
- 면접 Q&A: [`../07-interview-preparation.md`](../07-interview-preparation.md)

## 1. 프로젝트 소개

| 항목 | 내용 |
| --- | --- |
| 프로젝트명 | 성과노트 (ImpactNote) |
| 한 줄 소개 | 회사 업무를 기록하고, 근거로 확인한 성과만 남겨 제출용 보고서로 만드는 로컬 우선 도구 |
| 개발 배경 | 평가 시즌의 기억 의존, 출처 없는 수치, 팀 성과와 개인 기여 혼합 |
| 사용자 | 성과평가·승진·이직 서류를 준비하는 개발자·실무자 |
| 주요 기능 | 업무 기록, 성과·근거·지표 관리, Git/문서/코드 분석, 보고서 생성 |
| 기술 스택 | Python 3.11+, Typer, Pydantic v2, FastAPI, 바닐라 JS, JSON 저장, Docker |
| 구조 | 웹 UI/CLI → ImpactService → JSON Store·Report·Intel Analyzer → 선택적 AI |
| 핵심 원칙 | 기록과 해석 분리, 근거 없는 수치·효과 차단, 외부 전송 기본 차단 |
| 담당 범위 | 이 저장소의 구현·테스트·문서 작업 (팀 규모·역할 분담은 Git으로 확인 불가) |
| 개발 기간 | Git 기록 기준 2026-04-16 ~ 2026-11-16 (연속 기간·투입 시간은 미확인) |
| 현재 상태 | 로컬 1.0.0, 481 tests, Docker/CI 통과, AI 품질은 부분 검증 |

### 해결하려던 문제

1. 평가 시즌에 무슨 일을 했는지 기억나지 않는다.
2. 숫자를 쓰고 싶지만 출처를 댈 수 없다.
3. 팀 성과와 개인 기여가 섞여 과장처럼 보인다.

기존 DevFolio는 문서를 예쁘게 만드는 문제를 풀었다. ImpactNote는 **기록·근거·검증**으로
문제를 다시 정의했다.

## 2. 아키텍처 요약

```text
사용자 → Web UI / CLI → ImpactService
                         ├─ JsonStore (원자적 쓰기, 0600)
                         ├─ Report Engine (MD/DOCX/PDF/TXT/CSV)
                         ├─ Intel Analyzer (문서·코드·Git, 읽기 전용)
                         └─ AI (동의 시) → Provider Router → NVIDIA NIM 등
```

다이어그램 10개: [`../architecture/diagrams.md`](../architecture/diagrams.md)
Claim 검증 상세: [`../architecture/claim-validation.md`](../architecture/claim-validation.md)

## 3. 기술적 문제 해결 사례

| 사례 | 문제 | 선택 | 검증된 결과 |
| --- | --- | --- | --- |
| 중첩 수치 우회 | `statements.monthly`의 60%가 통과 | 모든 문자열 재귀 검사 | 회귀 테스트 |
| 단위 불일치 | `80ms`를 근거로 `80%` 승인 | `(값, 단위)` 대조 | 80% 차단, 10m=10분 |
| 정성 효과 | "안정성 향상" 무검증 | 결정론 효과 Gate | 12/12 차단, 10/10 보존 |
| 보고서 재유입 | 확인 후 검증 우회 | 생성 시점 재검증 | 회귀 테스트 |
| 공동 기여 | author만 집계 | co-author 1/n 분배 | 귀속 exact 100% (8) |
| 카테고리 오탐 | `ci` ⊂ `asyncio` | 단어 경계 매칭 | P/R 1.00 유지 |
| 빈 AI 응답 | gpt-oss reasoning 토큰 | max_tokens 하한 | live 6/6 성공 |
| 소표본 0건 | 0/12를 0%로 오독 | Wilson 구간 | 0–24.3% 보고 |

상세: [`../engineering/problem-solving-cases.md`](../engineering/problem-solving-cases.md).

## 4. 변경 전후 비교

| 개선 주제 | 기존 | 변경 | 이유 | 실제 결과 | 근거 |
| --- | --- | --- | --- | --- | --- |
| AI Provider | 단일 모델 | NVIDIA NIM + 재시도/전환 | 429·timeout 흡수 | live 6/6 | `adfe892` |
| JSON 출력 | 빈 응답·prefix 중복 | JSON mode·prefix 정규화 | 파싱 실패 방지 | JSON 6/6 | `adfe892` |
| 수치 검증 | 값만 비교 | 값+정규화 단위 | 파생 수치 차단 | 80% vs 80ms | `f05691d` |
| 중첩 검증 | 최상위 문자열 | dict/list 재귀 | 우회 차단 | 회귀 테스트 | `f05691d` |
| 정성 효과 | 무검증 | 효과 Gate | 근거 없는 효과 차단 | 12/12 차단 | `f05691d` |
| 보고서 | 확인 후 그대로 | 생성 시 재검증 | 재유입 차단 | 테스트 | `f05691d` |
| Git 분석 | 최근 커밋 | 최초+최근, revert 제외 | 역사 왜곡 방지 | P/R 1.00 | `e728935` |
| 기여 귀속 | author만 | co-author 분배 | 공동 기여 보존 | exact 100% (8) | `e728935` |
| 평가 | 수동 확인 | 동결 Ground Truth | 재현 가능 | 42 claim | `e2dd608` |
| 이식성 | macOS 중심 | 3 OS CI·Docker health | 환경 차이 | 481 tests | `dd4d64f` |

## 5. 정량·정성 성과

### 검증된 것

- **효과 claim 12/12 차단**: 근거 없는 정성 효과 12개를 저장 전에 삭제.
- **효과 claim 10/10 보존**: 근거 있는 효과 문장은 유지.
- **live A/B 4→0**: 실제 NVIDIA 3건에서 Baseline 저장 4건, Variant 0건. 2회 실행 모두.
- **회귀 테스트 481개**: 기존 465 + 신규 16.
- **Docker/CI**: 이미지 빌드, `/api/health` 200, 3 OS matrix, CI 9/9 job success.

### 부분 검증

- **귀속 exact 100%**: 합성 통제 저장소 8단위. 실제 회사 저장소 전체가 아니다.
- **성과 P/R 1.00**: 합성 fixture 12 positive + 8 negative. 일반화 아님.
- **Semantic 83.3%**: Historical 42 claim, Judge 의존.

### 검증되지 않은 것

- 전체 환각률 5% 이하 달성: **NOT_MEASURED** (동일 생성문 재심사 아님).
- 사실성 4.0/5: **NOT_MEASURED** (2.65/5는 Historical).
- 사람 평가자 일치도, USD 비용, Windows GUI: **NOT_MEASURED**.
- "모든 환각 제거": **UNSUPPORTED**.

## 6. 트레이드오프

| 선택 | 얻은 것 | 잃은 것 |
| --- | --- | --- |
| 결정론 Gate | 비용 0, 재현성, 사유 기록 | 의미 반대·새 표현 |
| 문장 단위 삭제 | 새 주장 생성 방지 | 같은 문장의 사실 절 |
| 사용자 수동 성과 보존 | 기록 손실 방지 | 수동 주장은 자동 검증 밖 |
| 합성 fixture | 재현 가능 | 실제 저장소 다양성 |
| live 3건 | 실제 호출 확인 | 통계적 일반화 |
| LLM Judge 보류 | 비용·오탐 회피 | Semantic 검증 부재 |

## 7. 면접 예상 질문

### Q1. 왜 NVIDIA NIM을 선택했는가?

기존 DevFolio AI 계층이 LiteLLM Provider 구조였고, NIM이 OpenAI 호환
`/v1/chat/completions`를 제공해 최소 변경으로 연결할 수 있었다. 2026-11-16
`/v1/models` 83개를 확인하고 `gpt-oss-20b`만 허용 목록에 넣었다. 근거:
`devfolio/core/ai_service.py`, `docs/nvidia-provider.md`.

### Q2. 프롬프트만 강화하지 않은 이유는?

프롬프트를 강화한 뒤에도 live 3건 중 2건에서 근거 없는 효과 주장이 나왔다.
프롬프트는 필요하지만 강제력이 없다. 저장 직전 결정론 Gate를 추가했다.
근거: `impactnote/core/claims.py`, `docs/evaluation/hallucination-experiments.md`.

### Q3. Deterministic Guardrail의 한계는?

한국어 효과 표현 목록에 없으면 놓치고, 기능 존재·의미 반대·귀속·용량은 검증하지
못한다. 42개 중 나머지 8개가 그 예다. 근거:
`docs/research/hallucination-root-cause.md` §4.

### Q4. LLM Judge를 제품 경로에 넣지 않은 이유는?

호출 비용·지연, Judge 자체 오탐, 한국어 캘리브레이션 데이터 부재. 평가 하네스에는
독립 심사 모델을 두되, 저장 경로는 결정론으로 유지했다. 근거:
`docs/decisions/ADR-hallucination-mitigation.md`.

### Q5. Hallucination Rate는 어떻게 측정했는가?

2026-10-03 NVIDIA 생성문 30개 + 경계 12개를 동결 라벨링하고, 생성 모델과 다른
심사 모델로 claim을 분류했다. Historical 47.6% (20/42, 95% CI 33.3–61.9%).
근거: `evals/impact/dataset.json`, `docs/evaluation-results.md`.

### Q6. 현재 결과를 전체 품질 개선이라고 주장할 수 없는 이유는?

효과 claim 부분집합만 측정했고, Gate 규칙을 같은 42개 claim을 보면서 설계해
in-sample이다. 전체 환각률·사실성은 재측정하지 않았다. 0/12의 95% 상한은 24.3%다.
근거: `evals/impact/results/effect-gate-2026-11-16.json`.

### Q7. Git 커밋만으로 개인 기여를 판단하면 어떤 문제가 있는가?

리뷰·설계만 한 기여, 대리 커밋, pair programming이 사라진다. author + co-author
trailer를 보존하고 1/n 분배했지만, 실제 작업 시간은 여전히 모른다. 근거:
`impactnote/core/intel/engine.py`, `tests/test_intel.py`.

### Q8. 어떤 데이터를 근거로 성과를 확정하는가?

Activity(사용자 기록), Evidence(PR·문서·로그), Metric(값·단위·기간·산출 기준),
Git commit/diff, 테스트. AI·Git 후보는 `confirmed=False`면 보고서 본문에서 제외한다.
근거: `impactnote/core/service.py::_apply_status`, `core/report.py`.

### Q9. 다른 PC에서 재현 가능한 환경을 어떻게 구성했는가?

Python 3.11–3.14 CI matrix, Ubuntu/macOS/Windows portability job, AI 키 없는
Docker build+health, `IMPACTNOTE_ANALYZE_ROOTS` allowlist, clean copy 테스트.
근거: `.github/workflows/ci.yml`, `docs/installation.md`, `docs/testing.md`.

### Q10. 다음 개선은?

1. held-out 효과 claim 세트로 Gate 일반화 측정.
2. 기능 존재·의미 반대 검증(인용 엔티티 대조 또는 Judge).
3. 기여 귀속의 리뷰·설계 증거 확장.
4. 품질 20개를 현재 프롬프트 출력으로 재수집.

## 8. 공개 안전성

- API 키·토큰·비밀번호는 문서·코드·결과에 없다.
- 평가 데이터의 이메일은 `alice@example.com` 등 합성 값이다.
- Historical 생성문은 사용자의 포트폴리오 사례에서 파생됐으며, 회사명·고객명·서버
  주소는 포함하지 않는다.
- 내부 전용 상세가 필요한 부분은 "비공개 근거"로 표시하고 수치를 만들지 않았다.
- 비밀값 스캔: `nvapi-` 실제 키 0, `sk-` 실제 키 0.

## 9. 읽는 순서

1. 이 문서 — 프로젝트·성과·트레이드오프
2. [`../architecture/diagrams.md`](../architecture/diagrams.md) — 구조 10개
3. [`../architecture/claim-validation.md`](../architecture/claim-validation.md) — 핵심 사례
4. [`../engineering/development-history.md`](../engineering/development-history.md) — 전체 과정
5. [`evidence-index.md`](evidence-index.md) — 주장별 근거
6. [`../07-interview-preparation.md`](../07-interview-preparation.md) — 기존 Q&A
