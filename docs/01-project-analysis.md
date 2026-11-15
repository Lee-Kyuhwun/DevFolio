# DevFolio 프로젝트 분석

> **아카이브 (2026-11-15):** 이 문서는 **DevFolio 시절의 기록**입니다. 현재 제품은 **성과노트(ImpactNote)** 이며,
> 최신 제품 설명·구조·검증 결과는 `README.md`, `docs/impactnote.md`, `docs/04-architecture.md` 가 기준입니다.
> 아래 내용은 당시의 판단과 측정을 보존하기 위해 수정하지 않았습니다.


기준일: 2026-11-15
분석 대상: 현재 워크스페이스의 `main` 브랜치 (변경 전 상태 + 이번 작업 변경분)
근거: 소스 코드, 기존 문서, git 이력, `pytest` 실행 결과, 격리된 홈 디렉터리에서 실행한 웹 스튜디오

> 표기 규칙: **[사실]** 은 코드·테스트·실행 결과로 확인한 내용, **[추론]** 은 구조를 근거로 한 해석, **[가설]** 은 아직 검증되지 않은 개선 가설이다.

---

## 1. 프로젝트 정체성

### 무엇을 만드는 서비스인가 **[사실]**

DevFolio는 개발자 경력을 **문서가 아니라 구조화된 데이터**로 먼저 관리하고, 그 하나의 원본에서 이력서·경력기술서·포트폴리오를 다시 출력하는 로컬 우선(local-first) 도구다.

- CLI: `devfolio <command>` (Typer). `devfolio/main.py`의 `cli()`가 진입점이다.
- 웹: `devfolio serve` → FastAPI 앱(`devfolio/web/app.py:create_app()`) → `http://127.0.0.1:8000`의 Portfolio Studio.
- 문서 엔진: Jinja2 템플릿(`devfolio/templates/*.j2`) + Markdown/HTML/PDF/DOCX/JSON/CSV 출력(`devfolio/core/export_engine.py`).

즉 이 프로젝트는 "이력서 편집기"가 아니라 **경력 데이터 관리 + 다중 문서 렌더링 + 선택적 AI 보조**가 결합된 형태다.

### 주요 사용자 **[추론]**

코드에 등장하는 개념(경험 유형 `work/personal/study/toy`, 문서 대상 `resume/career/portfolio`, `author_email` 기반 git 스캔)으로 볼 때 주 사용자는 다음으로 좁혀진다.

- 지원 시기마다 같은 경험을 다른 문서로 다시 써야 하는 **개인 개발자**
- GitHub 이력을 근거로 프로젝트 서술을 만들고 싶은 **주니어~미드레벨 엔지니어**
- 문서를 외부 SaaS에 올리지 않고 로컬에서 관리하려는 사용자

`user.email`이 git 스캔의 기본 작성자 필터로 쓰이는 점(`devfolio/web/routes/api.py:scan_git`)은 "본인 커밋만 골라내는 개인 도구"라는 전제를 코드로 확인시켜 준다.

### 해결하는 사용자 문제 **[사실 + 추론]**

| 문제 | 코드에서의 대응 |
|---|---|
| 같은 경험을 문서마다 다시 작성 | `Experience`/`Project` 단일 모델 → `TemplateEngine.render(doc_type=...)`로 재출력 |
| 자유 텍스트와 제출 문서 사이의 구조화 단계 부재 | 웹 Intake(자유 텍스트 → `ProjectDraft`), Git Scan(저장소 → 초안) |
| AI 결과를 어디에 반영할지 불분명 | draft → 사람이 편집 → 저장 → preview → export 흐름을 한 화면에 배치 |
| 문서와 원본이 따로 관리됨 | YAML 원본 + export 산출물을 같은 데이터 디렉터리에 보관, 선택적 GitHub 동기화 |

### 서비스 가치 제안 **[추론]**

경험 1건을 한 번만 정리하면 이력서(요약 위주), 경력기술서(프로젝트별 상세), 포트폴리오(케이스 스터디)에 같은 문장을 재사용할 수 있다. 차별점은 **문서 편집 기능이 아니라 데이터 모델과 렌더링 분리**에 있다. `doc_type`과 `template` 이름만 바꿔 같은 원본에서 다른 문서를 만든다(`_render_document()`).

---

## 2. 구현 범위 (README 주장 vs 코드)

README는 기능이 많다. 실제 코드에서 확인한 범위는 다음과 같다. **[사실]**

| 영역 | 구현 상태 | 근거 |
|---|---|---|
| CLI 프로젝트/작업 CRUD | 구현됨 | `devfolio/commands/project.py`, `task.py` |
| 웹 스튜디오(경험 CRUD) | 구현됨 | `devfolio/web/routes/api.py` (`/api/experiences`) |
| Git 저장소 스캔 | 구현됨 | `devfolio/core/git_scanner.py`, `/api/scan/git` |
| AI 초안/요약/task 문구 | 구현됨 (선택 의존성) | `core/ai_service.py`(litellm lazy import) + `core/ai_reliability.py`(재시도·차단·예산) + `core/ai_quality.py`(품질 하한선) |
| 미리보기 | 구현됨 (draft 미저장 상태도 가능) | `/api/preview/{doc_type}`, `DraftPreviewRequest.source == "draft"` |
| 다중 포맷 export | 구현됨 | `ExportEngine.export_*` |
| GitHub 동기화 | 구현됨 | `devfolio/core/sync_service.py`, `commands/sync.py` |
| 다국어 | 구현됨 (ko/en 문자열 카탈로그) | `devfolio/i18n.py`, `devfolio/locales/` |
| Docker 실행 | 파일 존재 | `Dockerfile`, `docker-compose.yml` (실행 검증은 이번에 하지 않음) |
| 생성 전략 평가(eval) | 구현됨 | `evals/`, `tests/test_evals_*.py` |

문서에 "계획만 된 부분"을 찾아볼 근거는 코드에서 발견되지 않았다. 다만 아래 5절의 미검증 항목은 구현과 별개로 **이번 작업에서 실행 검증하지 않은** 영역이다.

---

## 3. 기술 스택

### 런타임/핵심 **[사실]** (`pyproject.toml`)

- Python `>=3.11`
- Typer (`typer[all]`) — CLI
- Pydantic v2 — 모델/검증
- ruamel.yaml — 주석 보존 YAML
- Jinja2 — 문서 템플릿
- keyring — API 키 1순위 저장소
- platformdirs — OS별 데이터 경로
- 선택 의존성: `ai`(litellm), `pdf`(weasyprint, markdown), `docx`(python-docx), `gui`(fastapi, uvicorn)

### 웹 **[사실]**

- 백엔드: FastAPI + Starlette StaticFiles, Jinja2Templates
- 프론트엔드: **프레임워크 없음.** `devfolio/web/static/studio_v2.js`(단일 IIFE, 약 3.1k 줄)가 전역 `state` 객체를 들고 `root.innerHTML`을 다시 그리는 방식. 빌드 도구·번들러·npm 의존성 없음.

> **[사실]** `devfolio/web/static/app.js`(3,122줄)와 `style.css`(1,201줄)는 어떤 템플릿에서도 참조되지 않는다(`index.html`은 `studio_v2.css`/`studio_v2.js`만 로드). 이전 UI의 잔재로 보이며 현재 죽은 코드다. **[추론]** 삭제 대상이지만 이번 작업 범위에서 제외했다(다른 브랜치와 충돌 위험).

### 저장 **[사실]**

DB 없음. 모든 데이터는 YAML/JSON 파일이다.

- `Config` → `config.yaml` (권한 `0o600`)
- `Project` → `projects/<project_id>.yaml` (1 프로젝트 = 1 파일)
- 내보내기 결과 → `exports/`
- AI 호출 로그 → `ai_logs.jsonl`

---

## 4. 실제 실행 흐름

### 4.1 웹 스튜디오 부팅 **[사실]**

```
브라우저 GET /
  → ui.index()  (devfolio/web/routes/ui.py)
     ├ is_initialized() / load_config()  → 템플릿 변수
     └ index.html 렌더 (body data-initialized)
  → studio_v2.js DOMContentLoaded
     ├ applyRoute(location.hash)
     ├ loadInitialData()
     │   ├ GET /api/config      → config + ai_providers(마스킹) + generation 해석 결과
     │   └ GET /api/experiences → experiences + summary
     └ render()  (사이드바/상단바/화면 전체를 문자열로 재구성)
```

초기 로딩은 두 API를 `Promise.all`로 동시에 호출한다. 화면 상태는 `state.ui.loading` 하나로만 관리된다.

### 4.2 경험 저장 **[사실]**

```
폼 입력 → (버튼 클릭 시) syncExperienceFormFromDom()
  → state.experienceForm (ExperienceDraft 형태)
  → POST/PUT /api/experiences
     → api.create_experience / update_experience
        → project_draft_from_experience()        # 웹 DTO → 저장 모델
           → sync_canonical_links()              # extra_links URL을 github/demo/docs/video로 승격
        → ProjectManager.save_project_draft()
           → Project.model_validate(...)         # 저장 직전 재검증
           → storage YAML 원자적 쓰기
  → 응답을 normalizeExperience() 후 state 반영
```

중요한 설계 포인트: **웹 UI의 `ExperienceDraft`와 저장 모델 `Project`가 분리**되어 있고, 변환은 `devfolio/web/experience_mapper.py` 한 곳에서만 일어난다. UI 필드명(`title`, `type=work|personal|study|toy`)과 저장 모델(`name`, `type=company|side|course`)의 어휘가 다른데, 이 매핑이 한 파일에 모여 있어 변경 지점이 좁다.

### 4.3 문서 미리보기/내보내기 **[사실]**

```
POST /api/preview/career  {source, project_ids|draft_project, template}
  → _resolve_projects()          # source=saved → 저장된 Project, source=draft → 임시 Project
  → TemplateEngine().render(projects, cfg, template_name, doc_type)
  → ExportEngine()._md_to_html_body(markdown)   # 허용 목록 기반 HTML 변환
  → full_html (Mermaid 포함) → iframe srcdoc (sandbox="allow-scripts")

POST /api/export/career  {format}
  → doc_type별 지원 포맷 검사 → engine.export_{md,html,pdf,docx,csv} 또는 JSON 직접 쓰기
  → EXPORTS_DIR/<doc_type>_<template>.<ext>
```

미리보기는 **저장 전 초안으로도 동작**한다(`source: "draft"`). 이 덕분에 저장을 강요하지 않고 결과를 먼저 확인할 수 있다.

### 4.4 Git 스캔 **[사실]**

```
POST /api/scan/git {repo_path, author_email, refresh, analyze}
  → _resolve_scan_repo_path()
     ├ 원격 URL이면 거부 (clone 유도 hint)
     └ Docker용 호스트 경로 → 컨테이너 경로 후보 변환
  → scan_repo(repo_path, author_email, analyze)
     ├ git log 파싱 → CommitInfo[], 작성자 비율, LOC 증감, 언어 Counter
     └ analyze=True → README/핵심 파일 수집 → project_context
  → (선택) AIService.analyze_project_from_code()
  → build_project_payload() → 웹 초안 필드로 변환 (자동 저장하지 않음)
```

캐시는 **저장된 프로젝트의 `last_commit_sha`와 현재 HEAD 비교**로 판단한다(`analyze`/`refresh`가 아니면 재분석 생략). `analyze=True`인 경우 AI 분석을 항상 다시 수행한다.

### 4.5 AI 호출 **[사실]**

`AIService`는 litellm을 함수 내부에서 import한다. 호출 경로에는 다음 안전장치가 코드로 존재한다.

- `resolve_generation_model()` — 표시용 모델명과 실제 생성 모델을 분리하고, 미지원/대체 상태를 UI에 노출
- provider 폴백 체인 — 실패 시 다음 모델/provider로 이동
- 빈 응답·거절 문구 감지 — HTTP 200 본문이 거절 문구면 실패로 처리
- 한국어 문서에서 일본어/중국어 문자 제거 후처리
- AI 호출 로그(`ai_logs.jsonl`)에 요청/응답 길이·지연 기록 (`/api/ai-logs`로 조회)

이 장치들은 대부분 `docs/agent-incidents.md`의 실제 장애 기록(INC-01~12)과 1:1로 대응한다. 즉 **사후 대응의 흔적이 코드에 남아 있는 프로젝트**다.

---

## 5. 인증·상태관리·비동기·배포

- **인증/인가**: 없음. `create_app()`은 Swagger UI(`/docs`)도 끄고 로컬(127.0.0.1)에서만 쓰는 것을 전제로 한다. **[사실]** 따라서 "로그인" 기능은 존재하지 않는다. **[추론]** 다중 사용자·원격 공유는 설계 범위 밖이다.
- **상태 관리**: 전역 `state` 객체 + 전체 재렌더. 서버 상태와 UI 상태를 분리하지 않는다. **[추론]** 규모가 커지면 이 지점이 병목이 된다(이번 작업에서 검색 입력만 부분 렌더로 바꿨다. 06 참고).
- **비동기/큐**: 없음. AI 호출은 요청-응답 동기 방식이며, 긴 호출 동안 UI는 전체 화면 오버레이로 차단된다. **[사실]**
- **캐싱**: Git 스캔의 HEAD SHA 비교가 유일. HTTP 캐시 정책은 StaticFiles 기본값(ETag/Last-Modified). **[사실]**
- **CI/CD**: `.github/workflows/ci.yml`, Python 3.11/3.12/3.13 매트릭스 + `scripts/check.sh`(ruff + format + pytest). pre-commit 훅이 같은 스크립트를 호출. **[사실]** 배포 파이프라인은 없고, Docker 이미지 빌드가 배포 수단이다.
- **에러 처리**: 도메인 예외 `DevfolioError`(hint 포함) → API에서 `HTTPException(detail=...)`로 변환, CLI에서는 `main.py`가 일괄 처리. **[사실]**
- **로깅**: stdlib logging 래퍼(`devfolio/log.py`), `DEVFOLIO_LOG_LEVEL`. 웹은 `log_level="warning"`으로 uvicorn 실행. **[사실]**

---

## 6. 테스트

**[사실]** `pytest` 334개 통과(2026-11-15 기준). 구성:

- 모델/저장소/프로젝트 매니저/템플릿/export 단위 테스트
- `tests/test_web_api.py` — FastAPI `TestClient` 기반 라우터 계약 테스트(경험 CRUD 왕복, 미리보기, export, 스캔 오류 처리, AI provider 설정)
- `tests/test_ai_service.py`, `test_ai_review_gate.py` — AI 응답 파싱·거절 감지·심사 게이트
- `tests/test_incident_regressions.py` — `test_inc01_*` ~ `test_inc21_*` 회귀 테스트
- `tests/test_ai_reliability.py` — 오류 분류·Circuit Breaker·시간 예산·품질 하한선·열화 동작 41개
- `tests/test_evals_*` — 생성 전략 평가 하네스

**없는 것**: 프론트엔드(JS) 테스트, 브라우저 E2E, 성능 측정 자동화. `package.json`이 없어 JS 테스트 인프라 자체가 없다. **[사실]**

---

## 7. 이번 분석에서 확인한 한계

| 항목 | 상태 |
|---|---|
| AI 실제 호출 | 실행 검증됨 — 2026-11-15 Groq 무료 등급, `/api/scan/git` E2E 9.3초 |
| Docker 실행 | 검증됨 — compose 기동 후 컴퓨테이너 내부에서 E2E 실행 |
| PDF/DOCX 실제 렌더 | 미실행 (단위 테스트로만 커버) |
| Lighthouse/CWV | 미측정 |
| 프론트엔드 자동 테스트 | 인프라 없음 |

측정하지 않은 값을 성과로 쓰지 않는다. 06 문서에서 측정값과 미측정값을 구분했다.
