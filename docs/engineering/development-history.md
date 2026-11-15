# ImpactNote 개발 히스토리

작성일: 2026-11-16
근거: Git 133 commits (`ff77e94` 2026-04-16 ~ 이번 문서 커밋), 코드, 테스트, 기존 설계 문서
표기: **VERIFIED**(커밋·코드·테스트로 확인) / **INFERRED**(코드에서 합리적으로 추론) /
**UNKNOWN**(당시 의도 확인 불가)

> 개발 기간은 Git 기록 기준 **2026-04-16 ~ 2026-11-16**이다. 연속 개발 기간이나
> 투입 인원은 기록으로 확인할 수 없어 추정하지 않는다.

## 1. 한눈에 보는 타임라인

| 시기 | 전환 | Git 근거 |
| --- | --- | --- |
| 2026-04 | DevFolio 초기: CLI·문서 생성·GitHub 동기화 | `ff77e94`, `ff64a54` |
| 2026-10 | AI 신뢰성: 모델 전환·Circuit Breaker·관측 | `71aa804`, `34c7b97`, `b82b250` |
| 2026-11-15 | ImpactNote 전환: Activity·Achievement·Evidence·Report | `26e6695`, `d0e3eaf`, `dfaa64a` |
| 2026-11-15 | 프로젝트 인텔리전스: 문서·코드·Git 교차 분석 | `436c119`, `48e35fc` |
| 2026-11-16 | Ground Truth 평가·정성 효과 Gate | `e2dd608`, `f05691d` |
| 2026-11-16 | 이번 정리: NVIDIA Provider·Guardrail·문서 | `adfe892`~문서 커밋 |

## 2. Workstream별 재구성

### A. Core Domain & Product

| 질문 | 답 |
| --- | --- |
| 해결하려던 문제 | 평가 시즌에 업무 기록이 사라지고, 숫자의 출처를 댈 수 없고, 팀 성과와 개인 기여가 섞이는 문제 |
| 처음 구조 | DevFolio: 프로젝트 문서·경험을 YAML로 관리하고 문서를 예쁘게 내보내는 도구 |
| 실제 문제 | "문서 생성"은 해결했지만 **기록·근거·검증** 흐름이 없었다. 수치를 써도 출처를 확인할 단계가 없었다 |
| 대안 | (1) DevFolio에 성과 필드 추가 (2) 별도 제품으로 전환 (3) 외부 SaaS 연동 |
| 선택 | 로컬 우선 별도 제품 `impactnote/` + `devfolio/` 호환 계층 유지 |
| 이유 | 기존 데이터·CLI·내보내기를 버리지 않으면서 도메인을 재정의할 수 있다. 외부 전송 없는 기본값을 지킬 수 있다 |
| 수정 코드 | `core/models.py`(Activity/Achievement/Evidence/Metric/Report), `core/service.py`, `core/report.py`, `web/`, `main.py` |
| 새 문제 | AI·Git 후보가 사용자 확인 없이 `verified`가 되는 문제 → `_apply_status`에서 `needs_review` 강제 |
| 트레이드오프 | 자유도 높은 JSON 저장 vs 관계 무결성. 단일 사용자 로컬 도구라 JSON+ID 참조를 선택 |
| 최종 구조 | Activity(사실) → Achievement(해석) → Evidence/Metric(근거) → Report(제출) |
| 실제 결과 | 465→480개 회귀 테스트, AI 키 없이 기록·보고서·분석 동작 |
| 한계 | 다중 사용자·동시 편집·권한 모델은 없다 |

근거: **VERIFIED** (`26e6695`, `d0e3eaf`, `dfaa64a`, `tests/test_impactnote.py`).

### B. Project Intelligence

| 질문 | 답 |
| --- | --- |
| 해결하려던 문제 | 커밋 메시지 요약만으로는 "무엇을 실제로 만들었는지" 알 수 없다 |
| 처음 구조 | Git log 키워드 기반 후보 수집(`suggest_from_git`) |
| 실제 문제 | 문서에만 있는 기능, 리버트된 변경, 목표 문구, 목업이 성과로 섞였다. 최근 커밋만 보면 최초 구현이 사라졌다 |
| 대안 | (1) LLM에게 저장소 전체를 요약 (2) 정적 분석 + Git diff 교차 (3) 사람이 전부 입력 |
| 선택 | 결정론적 탐색·비교 + 선택적 AI 보강 |
| 이유 | 근거 ID·파일 경로·커밋 SHA를 보존해야 보고서에서 추적할 수 있다. AI 요약만으로는 인용을 검증할 수 없다 |
| 수정 코드 | `intel/discovery.py`, `gitintel.py`, `engine.py`, `ai_stage.py`, `models.py` |
| 새 문제 | `ci`가 `asyncio`에 매칭되는 오탐, rename 경로, symlink, 분석 경로 탈출 |
| 트레이드오프 | 정밀도 우선 → 후보를 줄이고 `HYPOTHESIS`로 낮춘다. Recall은 fixture 12/12로 유지 |
| 최종 구조 | 문서 발견 → 코드 심볼 → Git 진화 → 교차 분석 → 후보/근거 |
| 실제 결과 | 통제 저장소 P/R/F1 1.00/1.00/1.00, 귀속 exact 100% (8단위) |
| 한계 | 합성 fixture이며 실제 회사 저장소 전체를 대표하지 않는다 |

근거: **VERIFIED** (`436c119`, `48e35fc`, `e728935`, `evals/impact/results/latest.json`).

### C. Evidence & Attribution

| 질문 | 답 |
| --- | --- |
| 해결하려던 문제 | 팀 성과를 개인 성과로 쓰거나, 리뷰만 한 사람을 구현자로 쓰는 문제 |
| 처음 구조 | 커밋 author만 집계 |
| 실제 문제 | pair programming·co-authored-by·리팩터링·merge commit에서 귀속이 틀렸다 |
| 대안 | (1) author 단독 (2) 커밋 수 단순 합 (3) co-author까지 분배 |
| 선택 | author + `Co-authored-by` 참여자에게 균등 분배, merge/revert 제외 |
| 이유 | 커밋 하나를 여러 명이 만들 수 있다는 Git trailer를 보존하는 것이 최소 변경 |
| 수정 코드 | `gitintel.py`(trailer 파싱), `engine.py`(credits/share), `models.py`(co_authors) |
| 새 문제 | co-author가 여러 명이면 1/n 가중치가 실제 작업량과 다를 수 있다 |
| 트레이드오프 | 단순·설명 가능한 균등 분배 vs 실제 기여 시간 추정. 후자는 근거가 없다 |
| 최종 구조 | EvidenceRef(kind/path/locator/excerpt/verified) + 후보별 참조 집합 |
| 실제 결과 | 8개 통제 단위 exact 100%, wrong-solo 0% |
| 한계 | 리뷰·설계만 한 기여, 대리 커밋은 여전히 UNKNOWN |

근거: **VERIFIED** (테스트·평가), **INFERRED** (1/n 가중치의 실제 작업량 근사).

### D. AI Provider & Reliability

| 질문 | 답 |
| --- | --- |
| 해결하려던 문제 | AI 호출이 429·timeout·빈 응답으로 실패하면 분석 전체가 사라진다 |
| 처음 구조 | 단일 Provider·단일 모델 호출 |
| 실제 문제 | 추론 모델이 `max_tokens`를 reasoning에 소모해 content가 비었고, 모델 prefix가 중복됐고, JSON이 잘렸다 |
| 대안 | (1) 재시도만 (2) 모델 자동 전환 + Circuit Breaker (3) 외부 큐 |
| 선택 | 재시도·백오프·모델 전환·Circuit Breaker·오류 분류 |
| 이유 | 로컬 도구에 큐·워커를 두지 않고도 일시 장애를 흡수할 수 있다 |
| 수정 코드 | `devfolio/core/ai_service.py`, `ai_reliability.py`, `ai_observability.py` |
| 새 문제 | fallback이 품질 낮은 모델로 조용히 내려가 결과 품질이 흔들림 → 실제 사용 모델 기록 |
| 트레이드오프 | 가용성 vs 일관성. 실패 시 원본 Activity는 유지 |
| 최종 구조 | Provider Router → 재시도 → 모델 후보 → 실패 분류 → AIAnalysis.failed |
| 실제 결과 | 429/timeout 회귀 테스트, live 6/6 성공(2026-11-16) |
| 한계 | NVIDIA 계정 rate limit·비용은 계정 정책에 의존 |

근거: **VERIFIED** (`71aa804`, `34c7b97`, `adfe892`, `tests/test_ai_reliability.py`).

### E. AI Factuality & Guardrails

| 질문 | 답 |
| --- | --- |
| 해결하려던 문제 | 근거 없는 숫자·정성 효과가 성과와 보고서에 들어간다 |
| 처음 구조 | 프롬프트 지시 + 사후 수치 치환 |
| 실제 문제 | 숫자 없는 "안정성 향상"은 통과했고, `80%`가 `80ms`로 통과했고, 사용자 확인 후 보고서가 재검증 없이 실었다 |
| 대안 | (1) 프롬프트만 강화 (2) LLM Judge (3) 결정론 Gate (4) 전체 보류 |
| 선택 | 수치+단위 검증 + 정성 효과 Gate + 보고서 재검증 |
| 이유 | 비용 0, 결정론, 근거 ID와 함께 사유를 남길 수 있다. Judge는 비용·오탐 캘리브레이션이 선행돼야 한다 |
| 수정 코드 | `core/metrics.py`, `core/claims.py`, `core/ai.py`, `core/report.py`, `intel/ai_stage.py` |
| 새 문제 | 효과 문장을 통째로 지우면 같은 문장의 사실 절도 사라진다 |
| 트레이드오프 | 보수적 차단 vs Recall. 10/10 보존을 측정해 확인 |
| 최종 구조 | 수치 Claim → 단위 대조 → 효과 Claim → 근거 대조 → 저장/보고서 |
| 실제 결과 | 효과 claim 12/12 차단, 10/10 보존, live 4→0 |
| 한계 | 기능 존재·의미 반대·귀속·용량은 미해결 |

근거: **VERIFIED** (`f05691d`, `tests/test_claims.py`, `evals/impact/results/effect-gate-2026-11-16.json`).

### F. AI Evaluation & Research

| 질문 | 답 |
| --- | --- |
| 해결하려던 문제 | "AI가 그럴듯하다"와 "근거와 맞다"를 구분할 측정이 없었다 |
| 처음 구조 | 사례별 수동 확인·라벨링 |
| 실제 문제 | 47.6% Historical 환각률을 현재 성능으로 오독할 위험, 0건을 0%로 오독할 위험 |
| 대안 | (1) 사람 평가만 (2) LLM Judge만 (3) 결정론+Judge+구간 |
| 선택 | 동결 Ground Truth + 결정론 기준선 + 독립 Judge + 신뢰구간 |
| 이유 | Judge 오탐을 결정론 기준선과 비교하고, 소표본은 Wilson 구간으로 보고해야 한다 |
| 수정 코드 | `evals/impact/dataset.json`, `metrics.py`, `judge.py`, `run.py`, `gate.py`, `live_ab.py` |
| 새 문제 | 품질 20개가 Historical 출력이라 현재 프롬프트를 대표하지 않음 |
| 트레이드오프 | 표본 확대 vs 비용. live 3건·6회 호출로 제한 |
| 최종 구조 | claim/doc-code/성과/귀속/live 5개 축 + Gate/A-B |
| 실제 결과 | Historical 47.6%, 효과 Gate 0/12 false accept, live 4→0 |
| 한계 | 전체 환각률 재측정 없음, 사람 일치도 없음, 비용 NOT_MEASURED |

근거: **VERIFIED** (`e2dd608`, `evals/impact/results/*`).

### G. Test, Security & Portability

| 질문 | 답 |
| --- | --- |
| 해결하려던 문제 | 다른 PC·OS·Docker에서도 같은 결과가 나와야 한다 |
| 처음 구조 | 로컬 macOS 중심, Docker 포트 전체 노출 |
| 실제 문제 | 분석 경로 탈출, `.env` 이미지 포함, Windows/macOS 차이, 인증 없는 API의 LAN 노출 |
| 대안 | (1) Docker만 (2) 로컬만 (3) CI matrix + Clean Clone + Docker health |
| 선택 | 3개 OS CI, Python 3.11–3.14, Docker health, 경로 allowlist |
| 이유 | 설치·실행·분석 경계를 자동 검증해야 회귀를 막을 수 있다 |
| 수정 코드 | `.github/workflows/ci.yml`, `Dockerfile`, `docker-compose.yml`, `discovery.py` |
| 새 문제 | Docker 기본 CMD가 `--help`라 컨테이너가 바로 종료 → compose/CI에서 `serve --host 0.0.0.0` 명시 |
| 트레이드오프 | 127.0.0.1 바인딩으로 원격 접근 불가. 로컬 우선 제품에는 의도된 제한 |
| 최종 구조 | pre-commit → CI 4 job → 수동 AI 평가 |
| 실제 결과 | 480 passed, clean copy 480, Docker build + health 200 |
| 한계 | Windows 실제 GUI 클릭, PDF 폰트 렌더링은 미검증 |

근거: **VERIFIED** (`3ec1010`, `dfde13c`, `docs/testing.md`).

### H. Documentation & Portfolio

| 질문 | 답 |
| --- | --- |
| 해결하려던 문제 | 구현은 늘었지만 "왜 이렇게 했는지"가 커밋 메시지에만 남았다 |
| 처음 구조 | README·설계 문서·포트폴리오 케이스가 제품 전환 전후로 섞여 있었다 |
| 실제 문제 | 과거 47.6%와 현재 Gate 결과가 같은 표에 섞일 위험, Historical/현재 구조 혼동 |
| 대안 | (1) README만 갱신 (2) 문서 전체 재작성 (3) 현재/역사 분리 + 증거 인덱스 |
| 선택 | 기존 문서는 보존하고, 아키텍처·개발사·포트폴리오·증거 인덱스를 추가 |
| 이유 | 링크를 깨지 않고, 주장마다 코드·테스트·측정 자료를 연결할 수 있다 |
| 수정 코드 | `docs/architecture/`, `docs/engineering/`, `docs/portfolio/`, `docs/README.md` |
| 새 문제 | 문서가 코드보다 앞서가면 허구가 된다 → 실행 결과·SHA만 인용 |
| 트레이드오프 | 문서량 vs 유지보수. 다이어그램은 실제 컴포넌트만 사용 |
| 최종 구조 | 현재 기준 문서 + 역사 아카이브 + 증거 매트릭스 |
| 실제 결과 | 링크 0 broken, 비밀값 0, 10개 다이어그램 |
| 한계 | Mermaid 로컬 렌더링 미실행, GitHub 화면 확인 필요 |

근거: **VERIFIED** (이번 문서), **NOT_MEASURED** (Mermaid 렌더링).

## 3. 12개 질문에 대한 공통 답

| 질문 | 공통 결론 |
| --- | --- |
| 1. 어떤 문제를 해결했나 | 기록·근거·검증·보고서가 분리되지 않는 문제 |
| 2. 처음 구조는 | DevFolio 문서 생성 + 단일 AI 호출 |
| 3. 실제 문제는 | 근거 없는 수치·효과, 리버트/목표 문구 혼입, provider 장애 |
| 4. 고려한 대안은 | 프롬프트, LLM Judge, 결정론 Gate, Retrieval, Repair, 전체 보류 |
| 5. 선택은 | 결정론 검증 + 선택적 AI + 증거 추적 |
| 6. 이유는 | 비용·재현성·설명 가능성 |
| 7. 수정 코드는 | `core/metrics.py`, `core/claims.py`, `intel/*`, `evals/impact/*` |
| 8. 새 문제는 | 단위 무시, 문장 삭제 부작용, in-sample 과적합 |
| 9. 트레이드오프는 | Recall vs 정밀도, 비용 vs Judge, 문서량 vs 유지보수 |
| 10. 최종 구조는 | Activity→Achievement→Evidence→Report + Gate |
| 11. 실제 결과는 | 481 tests, 12/12 차단, 10/10 보존, live 4→0 |
| 12. 남은 한계는 | 의미 반대·기능 존재·귀속·용량, held-out 없음 |

## 4. 이번 작업의 Commit Map

| Commit | Workstream | 핵심 변경 | 검증 |
| --- | --- | --- | --- |
| `adfe892` | D | NVIDIA NIM provider·JSON mode·prefix·usage | 92 passed |
| `f05691d` | E | 수치 단위·정성 효과 Gate·보고서 재검증 | 43 passed |
| `e728935` | B/C | 경로 allowlist·Git 진화·co-author 귀속 | 53 passed |
| `e2dd608` | F | Ground Truth·Judge·Gate 지표·live A/B | 9 passed, offline exit 0 |
| `3ec1010` | G | Docker·CI matrix·Clean Clone 문서 | 480 passed (당시) |
| `dd4d64f` | D | NVIDIA gpt-oss 토큰 하한 회귀 | 1 passed |
| 문서 커밋 | H | 다이어그램·개발사·포트폴리오·증거 인덱스 | 링크·비밀값 검사 |

## 5. 확인되지 않은 것

- 최초 기획 당시의 회의·의사결정 문서는 저장소에 없다. 초기 설계 의도는 **UNKNOWN**이다.
- 팀 규모·개발 기간·투입 시간은 Git 기록으로 확인할 수 없다.
- 마케팅·사용자 인터뷰·실제 회사 도입 효과는 측정 자료가 없다.
- LLM Judge의 사람 라벨 대비 정확도, USD 비용, Windows GUI는 **NOT_MEASURED**다.
