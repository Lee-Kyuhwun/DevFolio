# 개선 리포트

> **아카이브 (2026-11-15):** 이 문서는 **DevFolio 시절의 기록**입니다. 현재 제품은 **성과노트(ImpactNote)** 이며,
> 최신 제품 설명·구조·검증 결과는 `README.md`, `docs/impactnote.md`, `docs/04-architecture.md` 가 기준입니다.
> 아래 내용은 당시의 판단과 측정을 보존하기 위해 수정하지 않았습니다.


기준일: 2026-11-15
범위: 웹 스튜디오 안정성·접근성·UX 개선 + 백엔드 검증 강화
원칙: 기존 동작 보존, 의존성 추가 없음, 사용자 데이터 미변경

---

## 1. 작업 환경

- 저장소: 현재 워크스페이스, `main` 브랜치, 작업 트리 클린 상태에서 시작
- Python: 3.14.4 (`.venv`), 프로젝트 요구사항은 3.11+
- 웹 검증: `HOME=/tmp/devfolio-demo`로 **격리된 임시 홈 디렉터리**에서 `devfolio serve` 실행 → 사용자의 실제 `~/Library/...` 데이터·키체인 미변경
- 시드 데이터: 실제 사용자에게 보이지 않는 임시 저장소에 한국어 경험 4건 생성 후 화면 확인, 이후 전부 삭제하여 빈 상태도 확인

---

## 2. 수정한 항목

### 2.1 백엔드

#### (1) 폴더 열기가 항상 HTTP 500 → INC-20

| 항목 | 내용 |
|---|---|
| 증상 | "폴더 열기"를 누르면 폴더는 열리지만 화면에는 실패 토스트가 뜬다 |
| 재현 | `POST /api/fs/open-folder?path=<홈 내부 디렉터리>` → 500 |
| 근본 원인 | `open_folder()`의 반환 타입은 `dict[str, str]`인데 함수 끝에 `return`이 없었다. FastAPI가 `None`을 응답 모델로 검증하다 `ResponseValidationError` 발생 |
| 수정 | `{"status": "ok", "folder": str(folder)}` 반환 |
| 검증 | `test_inc20_open_folder_returns_ok_payload` (수정 전 500, 수정 후 200) |
| 심각도 | Medium (기능 자체는 동작, 사용자에게는 실패로 보임) |

#### (2) 홈 디렉터리 경로 검사가 유사 접두사 허용 → INC-19

| 항목 | 내용 |
|---|---|
| 증상 | 홈이 `/Users/me`일 때 `/Users/me-evil/...`이 "홈 내부"로 판정되어 탐색기로 열린다 |
| 근본 원인 | `str(folder).startswith(str(home))` — 문자열 접두사 비교 |
| 수정 | `Path.is_relative_to(home)` + 디렉터리가 아닌 경로는 400 |
| 검증 | `test_inc19_open_folder_rejects_home_sibling_prefix_path`, `test_inc19_open_folder_opens_directory_inside_home`, `test_open_folder_rejects_non_directory_path` |
| 심각도 | Low (로컬 실행 사용자 범위) |

#### (3) AI 로그 `limit` 범위 미검증

음수 `limit`이 슬라이스를 뒤집어(`lines[-(-5):]`) 결과가 반전되고, 과대 값은 응답을 키웠다. `max(1, min(limit, 1000))`으로 고정. `test_ai_logs_limit_is_clamped`로 고정.

### 2.2 프론트엔드 — 안정성

| # | 변경 | 파일 | 효과 |
|---|---|---|---|
| 4 | 초기 로딩 실패를 전용 오류 화면으로 표시 + "다시 시도" | `studio_v2.js` | "데이터 없음"과 "불러오기 실패" 구분, 복구 경로 확보 |
| 5 | `requestJson`에 `AbortController` 타임아웃 + 네트워크 오류 문구, GET 한정 1회 재시도 | `studio_v2.js` | 멈춘 서버에서 무한 대기 방지. 저장/삭제는 재시도하지 않아 중복 생성 위험 없음 |
| 6 | 빈 상태 CTA(`data-screen`+`data-action`)가 화면 이동 후 액션도 실행 | `studio_v2.js` | "첫 경험 추가"가 실제로 새 경험 폼을 연다 |
| 7 | 검색 입력을 결과 영역 부분 갱신으로 변경 | `studio_v2.js` | 입력 노드 유지 → 한글 IME 조합·커서 위치 보존 |
| 8 | 편집기 폼 `submit` 처리 추가 | `studio_v2.js` | 입력란 Enter로 저장 |

### 2.3 프론트엔드 — 접근성/디자인

| # | 변경 | 효과 |
|---|---|---|
| 9 | `--text-3` `#6f7a86` → `#8b949e` | 보조 텍스트 대비 3.96:1 → **5.62:1** (AA 통과) |
| 10 | `:focus-visible` 공통 포커스 링 추가, `.btn:focus-visible`의 `outline: none` 제거 | 버튼·탭·카드에 키보드 포커스 가시화 |
| 11 | `prefers-reduced-motion` 블록 추가 | 장식 모션·호버 이동 제거 |
| 12 | 모달에 `role="dialog"`, `aria-modal`, `aria-label`, ESC 닫기, 초기 포커스 | 키보드 이탈 경로 확보 |
| 13 | 고정 라이브 리전(`#live-region`) + 토스트 통지 | 스크린리더에 저장/실패 결과 전달 |
| 14 | 로딩 오버레이에 `role="status" aria-busy` | 진행 상태 노출 |
| 15 | `card-button` 등 카드형 버튼 좌측 정렬 | 패널 내 정렬 일관성 |
| 16 | 모바일 내비 한 줄 가로 스크롤, 상단바 2행 분리, 토스트 폭 조정, 미리보기 높이 축소 | 첫 화면 콘텐츠 노출 121px 개선 |

---

## 3. 변경 파일 목록

| 파일 | 변경 성격 |
|---|---|
| `devfolio/web/routes/api.py` | 백엔드 3건 (반환값 누락, 경로 포함 검사, limit 범위) |
| `devfolio/web/static/studio_v2.css` | 토큰·포커스·모션·모바일 레이아웃·정렬 |
| `devfolio/web/static/studio_v2.js` | 오류 상태, 타임아웃/재시도, 부분 갱신, 모달 키보드, 라이브 리전, submit |
| `devfolio/web/templates/index.html` | 라이브 리전 요소 추가 |
| `tests/test_web_api.py` | 신규 테스트 4개 (`test_inc19_*` 2, `test_inc20_*` 1, `test_open_folder_rejects_non_directory_path`, `test_ai_logs_limit_is_clamped`) |
| `docs/agent-incidents.md` | INC-19, INC-20 항목 및 요약 표 추가 |
| `docs/01~07-*.md`, `docs/assets/*.png` | 분석·포트폴리오·감사 문서 및 스크린샷 |

> 미변경(의도적): `devfolio/web/static/app.js`, `style.css` — 어떤 템플릿에서도 참조되지 않는 죽은 코드. 별도 정리 권장.

---

## 4. 테스트 결과

| 검사 | 결과 |
|---|---|
| `pytest` (전체) | **334 passed** (UI 라운드 289 → INC-21 +4 → AI 신뢰성 +41), 약 3.8초 |
| `ruff check devfolio/ tests/` | **All checks passed** |
| 되돌림 확인 (INC-19) | `startswith`로 되돌리면 `test_inc19_open_folder_rejects_home_sibling_prefix_path` **실패** ✅ |
| 되돌림 확인 (INC-20) | `return` 제거 시 `test_inc20_open_folder_returns_ok_payload` **실패(500)** ✅ |
| 복구 확인 | 수정 복원 후 4개 테스트 모두 통과 |

`make check`(ruff + format + pytest)의 format 단계는 별도 실행하지 않았고 `ruff check`만 수행했다. 이번 변경은 `ruff format` 대상 Python 파일에 포맷 영향이 없는 3줄 수준 수정이다.

---

## 5. 브라우저 검증 결과 (실측)

격리 서버(`127.0.0.1:8011`)에서 실제 Chromium으로 확인했다.

| 확인 항목 | 결과 |
|---|---|
| 콘솔 오류 | 없음 |
| 네트워크 실패 | 없음 (config/experiences 200, 정적 자원 200) |
| `--text-3` 대비 | 5.62:1 (surface) / 6.15:1 (bg) — 수정 전 3.96 / 4.33 |
| 카드 정렬 | `text-align: left`, 콘텐츠 좌표 = 카드 좌측 + 패딩 + border |
| `prefers-reduced-motion` | 스타일시트에 규칙 존재·파싱 확인 |
| 검색 입력 | `결제` 입력 후 결과 4→1건, **동일 입력 노드 유지**, 포커스 유지 |
| 모달 | `role=dialog`, `aria-modal=true`, 초기 포커스 모달 내부, **ESC로 닫힘** |
| 빈 상태 CTA | 경험 0건에서 "첫 경험 추가" 클릭 → 화면 `Experience Editor`, 폼·Intake 표시 |
| 폴더 열기 API | 200 (수정 전 500) |
| 모바일 390×844 | 내비 194→73px, 콘텐츠 시작 426→305px |

### 검증하지 못한 것 (성공으로 보고하지 않음)

- **`:focus-visible`의 실제 렌더링**: 규칙이 로드되고 버튼에 `outline: none` 경쟁 규칙이 없음을 확인했으나, 자동화 도구의 주입 키 이벤트가 Chromium의 키보드 모달리티를 세우지 않아 `:focus-visible` 매칭을 화면으로 확인하지 못했다. 실제 키보드 사용 시 표시된다.
- **스크린리더 청취 검증**: 라이브 리전·dialog 속성 추가는 확인했으나 VoiceOver/NVDA 실제 청취는 미실행.
- **AI 기능 실행**: API 키·비용 문제로 미실행. 기존 단위 테스트(모킹)로만 커버.
- **PDF/DOCX 실제 렌더**: 브라우저에서 내보내기 미실행(단위 테스트로 커버).
- **Docker 경로**: 미검증.
- **성능 지표(LCP/INP/CLS)**: Lighthouse 미실행. 성능 수치를 주장하지 않는다.

---

## 6. 성능 관련 서술

이번 작업은 **성능 최적화가 아니라 정확성·접근성 개선**이다. 다만 다음 두 가지는 구조적으로 낭비를 줄인다.

1. **검색 시 전체 재렌더 제거** — 입력 한 글자마다 사이드바·상단바·카드 전체를 재생성하던 경로가 결과 목록 갱신으로 바뀌었다. 렌더 비용이 줄지만 **측정하지 않았다**.
2. **불필요한 재시도 금지** — GET만 1회 재시도. 저장/삭제는 재시도하지 않아 중복 쓰기 위험이 없다.

---

## 7. 남은 위험과 후속 우선순위

| 우선순위 | 항목 | 이유 |
|---|---|---|
| P1 | 프론트엔드 스모크 테스트 도입 | 이번 결함 6건 중 3건이 브라우저에서만 드러났다. Playwright 최소 시나리오(부팅→경험 저장→미리보기)가 있으면 회귀를 자동으로 잡는다 |
| P1 | `--host 0.0.0.0` 사용 시 경고 | 웹 API에 인증이 없다. README가 이 옵션을 안내하지만 위험 고지가 없다 |
| P2 | 전체 재렌더 → 화면별 부분 갱신 | 입력 상태·포커스 보존의 근본 해결 |
| P2 | 모달 포커스 트랩 | 현재 ESC·초기 포커스만 처리 |
| P2 | 섹션 순서 변경의 키보드 대체 수단 | 드래그 전용 |
| P3 | `ai_logs.jsonl` 회전 | 무한 증가 |
| P3 | 죽은 프론트엔드 자산 삭제 | 약 4.3k 줄 |
| P3 | 자동 접근성 감사(axe) | 의존성 추가 판단 필요 |

---

## 8. 후속 라운드 — AI 신뢰성 계층 (INC-21·INC-22)

이 문서의 1~7절은 UI/UX 라운드(커밋 `207e738`) 기준이다. 이후 AI 분석 실패를 다루는 별도 라운드가 이어졌으므로 수치와 구조를 여기에 갱신한다.

### 발견한 장애

| 증상 | 원인 |
|---|---|
| AI 딥 분석이 항상 "기본 스캔 결과로 계속"으로 끝남 | Groq 후보 4개가 모두 폐기·미존재(`/v1/models` 실측) |
| 폴백 응답이 JSON으로 파싱되지 않음 | pollinations가 `max_tokens` 미지정 시 1,500토큰에서 절단(`finish_reason=length`) |
| 폐기 모델을 매 호출마다 반복 시도 | 모델 상태를 기억하는 계층이 없었고 `_MAX_RETRIES`가 모든 예외에 적용 |
| 요청 성공이 곪 분석 완료로 처리 | 응답의 형태·근거·잘림 여부를 판정하지 않음 |

### 추가한 구조

| 파일 | 역할 |
|---|---|
| `core/ai_reliability.py` | 오류 분류, 모델 Circuit Breaker(파일 영속), 시간 예산(90초), 백오프+`Retry-After` |
| `core/ai_quality.py` | Level 1(스키마)·Level 2(기술 스택·수치 근거 대조) Hard Gate |
| `core/ai_service.py` | 단계 상태(`AnalysisOutcome`), 재시도 제어 지점 단일화, `max_retries=0` |
| `web/routes/api.py`, `studio_v2.js/.css` | 사용 모델·자동 전환·단계·품질 판정 노출 |

### 결과 (측정)

| 항목 | 값 |
|---|---|
| `pytest` | **334 passed** (289 → INC-21 +4 → AI 신뢰성 +41) |
| Docker E2E `/api/scan/git` | 9.3초, `analyzed: true`, `groq/openai/gpt-oss-120b`, 품질 `passed`(기술 12/14 근거 확인) |
| 전 Provider 실패 시 | `completed: false`, `payload: {}`, 스캔 단계만 유지 |
| 폐기 모델 낭비 호출 | 요청당 4회 → 0회 |

### 남은 위험

| 우선순위 | 항목 | 이유 |
|---|---|---|
| P1 | 모델 목록 `/v1/models` 자동 동기화 | 폐기 반복 시 수동 갱신이 필요하다 |
| P2 | pollinations 1,500토큰 상한 대응(스키마 축약·호출 분할) | 서버 측 상한은 클라이언트로 못 넘긴다 |
| P2 | P95 지연·장기 성공률 수집 | 1회 E2E 외에 측정하지 않았다 |
| P3 | UI 패널 브라우저 확인 | 코드 검증(`node --check`)만 했고 화면은 보지 않았다 |
