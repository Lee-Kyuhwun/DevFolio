# 문서 인덱스

기준일: 2026-11-16 · 제품: 성과노트(ImpactNote) 1.0.0

`docs/` 의 문서는 **현재 기준 문서**와 **DevFolio 시절 아카이브**로 나뉜다.
아카이브 문서는 당시 판단·측정을 보존하며, 상단 배너에서 현재 기준 문서를 안내한다.

## 현재 기준 문서

| 문서 | 내용 |
| --- | --- |
| [`impactnote.md`](impactnote.md) | 제품 개념, 도메인, 수치 가드레일, AI 동의, 보고서, API, 마이그레이션 |
| [`installation.md`](installation.md) | 새 PC·Docker·OS별 설치, 데이터 위치, Clean Clone |
| [`architecture.md`](architecture.md) | 현재 시스템 구조, Evidence Graph, AI Provider·평가 계층 |
| [`architecture/diagrams.md`](architecture/diagrams.md) | 시스템·파이프라인·AI·검증·CI·커밋 다이어그램 10개 |
| [`architecture/claim-validation.md`](architecture/claim-validation.md) | 수치·단위·정성 효과 Gate와 보고서 재검증 상세 |
| [`ai-evaluation.md`](ai-evaluation.md) | Ground Truth, 6개 지표 정의, 임계값, 실행 방법 |
| [`nvidia-provider.md`](nvidia-provider.md) | NVIDIA NIM 설정·검증 모델·보안·제한 |
| [`testing.md`](testing.md) | 단위·통합·Live·Clean Clone·CI 검증 |
| [`evaluation-results.md`](evaluation-results.md) | 2026-11-15 실제 측정 결과·실패·한계 |
| [`engineering/development-history.md`](engineering/development-history.md) | Workstream별 문제·대안·결정·결과·한계 |
| [`engineering/problem-solving-cases.md`](engineering/problem-solving-cases.md) | 실제 결함 8건의 원인·수정·검증 |
| [`portfolio/README.md`](portfolio/README.md) | 포트폴리오 소개·비교표·성과·트레이드오프·면접 Q&A |
| [`portfolio/evidence-index.md`](portfolio/evidence-index.md) | 주장별 코드·커밋·테스트·측정·검증 상태 |
| [`final-report-2026-11-15.md`](final-report-2026-11-15.md) | Phase 16 최종 보고·판정 |
| [`audits/2026-11-15/`](audits/2026-11-15/) | 6개 역할별 감사 보고서 |
| [`ponytail/README.md`](ponytail/README.md) | Ponytail FULL 운영 규칙·원문·라이선스 |
| [`04-architecture.md`](04-architecture.md) | DevFolio 시절 시스템 구조 (역사 자료, 현재 구조는 architecture.md) |
| [`01-project-analysis.md`](01-project-analysis.md) | 제품 정체성, 구현 범위, 실행 흐름, 테스트·리스크 |
| [`02-technical-decisions.md`](02-technical-decisions.md) | 주요 설계 결정과 트레이드오프 |
| [`03-portfolio-case-study.md`](03-portfolio-case-study.md) | 제출용 케이스 스터디 |
| [`devfolio_backend_portfolio.md`](devfolio_backend_portfolio.md) | 백엔드 관점 포트폴리오 (파일명은 링크 호환 유지) |
| [`05-ui-ux-audit.md`](05-ui-ux-audit.md) | 8개 화면 구조, 디자인 시스템, 발견·수정한 UI 문제, 접근성 |
| [`06-improvement-report.md`](06-improvement-report.md) | 전환·검증 라운드 결과, 결함 수정, 테스트·실행 검증 |
| [`07-interview-preparation.md`](07-interview-preparation.md) | 면접 Q&A (사실/답변 예시 구분) |
| [`ai-reliability.md`](ai-reliability.md) | AI 재시도·차단·오류 분류 정책과 성과노트 적용 |
| [`ai-collaboration.md`](ai-collaboration.md) | 사람-AI 역할 분담, 검증 장치, 전환 라운드 기록 |
| [`agent-incidents.md`](agent-incidents.md) | 장애·에이전트 실수 기록 (INC-25~28: 성과노트 전환기) |

## 아카이브 (DevFolio 시절)

| 문서 | 성격 |
| --- | --- |
| `01`~`03`, `05`~`07` 의 이전 판 | 현재 기준으로 재작성됨 (Git 이력에 보존) |
| [`superpowers/plans/`](superpowers/plans/) | 2026-10-03 작업 계획 |
| [`superpowers/specs/`](superpowers/specs/) | 2026-10-03 설계 스펙 |
| [`team-sessions/`](team-sessions/) | 팀 세션 기록 |
| `../evals/runs/` | 심사 모델 평가 실행 결과 |

## 읽는 순서 (신규 기여자)

1. [`../README.md`](../README.md) — 제품 소개·실행
2. [`../GUIDE.md`](../GUIDE.md) — 사용 흐름
3. [`impactnote.md`](impactnote.md) — 설계·가드레일
4. [`architecture.md`](architecture.md) — 현재 구조
5. [`ai-evaluation.md`](ai-evaluation.md) — AI 평가 방법
6. [`evaluation-results.md`](evaluation-results.md) — 실제 결과와 한계
7. [`engineering/development-history.md`](engineering/development-history.md) — 개발 과정
8. [`portfolio/evidence-index.md`](portfolio/evidence-index.md) — 주장별 근거
9. [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — 개발·검증 규칙
