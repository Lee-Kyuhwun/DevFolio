# 성과노트(ImpactNote) 프로젝트 분석

기준일: 2026-11-15, 버전 1.0.0
분석 대상: `main` 브랜치의 `impactnote/` + `devfolio/` 호환 계층
근거: 소스 코드, `tests/` 431개 실행 결과, Docker 컨테이너, 브라우저 실행

> 표기: **[사실]** 코드·테스트·실행으로 확인, **[추론]** 구조를 근거로 한 해석, **[가설]** 추가 검증이 필요한 가정.

---

## 1. 프로젝트 정체성

### 무엇을 만드는 서비스인가 **[사실]**

성과노트는 회사 업무를 기록하고, 근거로 확인한 성과만 남기고, 제출용 보고서로 출력하는 **로컬 우선** 도구다.

- CLI: `impactnote <command>` (Typer) — `version`, `init`, `serve`, `migrate`, `activity`, `achievement`, `report`
- 웹: `impactnote serve` → FastAPI(`impactnote/web/app.py:create_app()`) → SPA(`web/static/`)
- 저장: 컬렉션별 JSON(`activities`, `achievements`, `evidence`, `metrics`, `goals`, `reports`, `analyses`, `settings`)
- 문서: Markdown/DOCX/PDF/TXT/CSV (`devfolio/core/export_engine.py` 재사용)

핵심은 문서 편집이 아니라 **기록 → 성과 → 근거 → 보고서의 데이터 흐름과 가드레일**이다.

### 주요 사용자 **[추론]**

- 성과평가·승진·이직 서류를 준비하는 회사 개발자/엔지니어
- 팀 성과와 개인 기여를 구분해 서술해야 하는 실무자
- 업무 데이터를 외부 SaaS에 올리지 않으려는 사용자

### 해결하는 사용자 문제 **[사실 + 추론]**

| 문제 | 제품의 대응 |
| --- | --- |
| 평가 시즌에 무슨 일을 했는지 기억나지 않음 | 제목+설명만으로 즉시 기록, 나중에 보완 |
| 숫자를 쓰고 싶지만 출처를 댈 수 없음 | 숫자+단위 주장을 기록·근거와 대조, 미확인은 `[확인 필요]` |
| 팀 성과가 개인 성과처럼 보임 | 직접/공동 수행·의사결정 기여를 분리 저장 |
| 같은 내용을 양식마다 다시 씀 | 기간·템플릿 조합으로 재생성, 버전 이력 유지 |
| AI가 그럴듯한 거짓 수치를 만듦 | AI 결과 수치 세탁 + 확인 전 후보 상태 유지 |

### 가치 제안 **[추론]**

"성과를 잘 쓰는 법"이 아니라 **말할 수 있는 성과만 남기는 구조**를 제공한다.
근거가 없으면 문서에 들어가지 않는다는 규칙이 제품의 차별점이다.

---

## 2. 구현 범위 (문서 주장 vs 코드)

| 기능 | 구현 위치 | 상태 |
| --- | --- | --- |
| 업무 기록 CRUD | `core/service.py`, `web/api.py` | 구현·테스트 |
| 기록 → 성과 묶기 | `create_achievement_from_activities` | 구현·테스트 |
| 근거 연결·상태 계산 | `_apply_status`, `link_evidence` | 구현·테스트 |
| 수치 검증 | `core/metrics.py`, `add_metric` | 구현·테스트 |
| AI 분석·동의 게이트 | `core/ai.py`, `Settings` | 구현·테스트(모의 호출) |
| Git 후보 | `suggest_from_git` + `devfolio/core/git_scanner.py` | 구현·테스트 |
| 보고서 5템플릿·6기간 | `core/report.py`, `core/periods.py` | 구현·테스트 |
| 다운로드 5형식 | `report.export_report` + ExportEngine | MD/DOCX/TXT/CSV 확인, PDF는 변환 도구 의존 |
| 버전·제출 상태 | `Report.version`, `status` | 구현·테스트 |
| DevFolio 이전 | `core/migrate.py` | 구현·테스트·컨테이너 검증 |
| 8개 화면 SPA | `web/static/app.js` | 구현·브라우저 확인 |

---

## 3. 기술 스택 **[사실]**

- 런타임: Python 3.11+ (검증 환경 3.14), Typer, Pydantic v2, FastAPI
- 저장: `platformdirs` + JSON, `os.replace` 원자적 쓰기, 파일 권한 `0600`
- 문서: 기존 ExportEngine(docxtpl/weasyprint 선택 의존성, lazy import)
- AI: `devfolio/core/ai_service.py` + `ai_reliability`/`ai_observability` 재사용
- 프론트엔드: 프레임워크 없음(바닐라 JS SPA)
- 배포: Docker Compose(서비스 `impactnote`, 포트 8000)

---

## 4. 실제 실행 흐름

### 4.1 기록 저장 **[사실]**

`POST /api/activities` → `ImpactService.create_activity()` → Pydantic 검증 → `JsonStore.put("activities")`.
제목·설명만 있으면 날짜는 오늘, 중요도는 3, 유형은 `general` 로 채워진다.

### 4.2 성과·근거 **[사실]**

기록 선택 → `POST /api/achievements/from-activities` → 성과 생성(상태 `user_input`).
근거 연결 시 `_apply_status()` 가 다음을 계산한다.

- AI/Git 후보이고 `confirmed=false` → `needs_review`
- 연결 근거 전부 verified → `verified`
- 일부만 verified → `partially_verified`
- 근거가 있으나 미확인 → `needs_review`

### 4.3 수치 **[사실]**

`Metric` 은 값·단위·기간·산출 기준·근거를 저장하고, `metric_is_verified()` 가
"값+단위 문자열이 기록/근거 텍스트에 존재"를 확인한다. 통과하지 못하면 `verified=false` 로 내려간다.

### 4.4 보고서 **[사실]**

`POST /api/reports` → `periods.resolve_period()` → 기간 내 기록/성과 선택 →
`build_content()`(템플릿별 섹션 + 검증 지표 + 확인 필요 부록) → ExportEngine → 파일 저장.
같은 기간·템플릿 재생성 시 `version` 이 증가한다.

### 4.5 AI **[사실]**

`Settings.external_ai_consent=false` 면 409 `EXTERNAL_AI_NOT_ALLOWED`.
동의 시 `AIService._call()` 을 호출하고 결과를 `sanitize_ai_result()` 로 수치 세탁한 뒤
`AIAnalysis` 로 별도 저장한다. 실패 시 `status="failed"` + `error_code` 만 남고 Activity 는 불변이다.

### 4.6 Git **[사실]**

커밋 메시지·변경량을 규칙 기반으로 분류해 Activity 와 Achievement 후보를 만든다.
AI 를 쓰지 않으며 후보는 항상 `needs_review` 다.

---

## 5. 인증·상태·배포

- 인증 없음(로컬 단일 사용자), 기본 바인딩 `127.0.0.1`
- 서버 상태 없음 — SPA 가 메모리 상태 + API 로 동작
- 비동기 작업 큐 없음 — AI 호출은 요청 내 동기 처리
- 배포: 단일 컨테이너 + 로컬 볼륨, 외부 DB 없음

---

## 6. 테스트·검증

| 구분 | 결과 |
| --- | --- |
| 전체 pytest | 431 passed (`impactnote` 30 + 레거시 401) |
| lint/format | ruff 통과, `scripts/check.sh` 통과 |
| JS 문법 | `node --check app.js` 통과 |
| Docker | 이미지 빌드·기동, `/api/health` 200, `/` 200 |
| 컨테이너 E2E | 기록→성과→근거→지표→DOCX/MD 보고서, AI 동의 차단 409 |
| 마이그레이션 | 백업 생성, 2회 실행 멱등, 원본 해시 불변, 권한 0600 |
| 브라우저 | 기록 저장→성과 생성→보고서 미리보기 확인 |

---

## 7. 리스크·한계 **[가설 포함]**

1. **지표 검증의 엄격함** — 값이 기록/근거 텍스트에 없으면 확인되지 않는다. URL 근거만 있는 경우 별도 확인 UX 가 필요하다.
2. **PDF 렌더링** — 시스템 폰트/변환 도구 의존. 컨테이너에서 PDF 실출력은 미검증.
3. **AI 품질** — 모의 호출로 게이트·실패 경로를 검증했고, 실제 Provider 품질은 `docs/ai-reliability.md` 정책에 의존한다.
4. **단일 사용자** — 동시 편집·권한·클라우드 동기화는 범위 밖이다.
5. **Git 후보 규칙** — 커밋 메시지 관례가 다른 저장소에서는 분류 품질이 달라질 수 있다.
