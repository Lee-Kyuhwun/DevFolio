# 성과노트 전환·검증 리포트

기준일: 2026-11-15
범위: DevFolio → 성과노트(ImpactNote) 전환, Docker·브라우저 검증, 발견 결함 수정
원칙: 기존 데이터 보존, 레거시 호환 유지, 검증하지 못한 것은 성공으로 보고하지 않음

---

## 1. 작업 환경

- 저장소: 현재 워크스페이스, `main` 브랜치
- Python 3.14.4 (`.venv`), 요구사항 3.11+
- Docker: `docker compose up -d --build` (서비스 `impactnote`, 컨테이너 `devfolio-impactnote-1`, 포트 8000)
- 브라우저: 로컬 Chromium, 1280×900 및 736px 폭
- 검증 데이터: 컨테이너의 신규 `impactnote-data` 볼륨에서 생성 후 삭제, DevFolio 원본은 읽기만 함

---

## 2. 전환 내용

### 2.1 새 제품 패키지

- `impactnote/core`: 모델, JSON 저장소, 서비스, 기간, 수치 가드레일, AI, 보고서, 마이그레이션
- `impactnote/web`: FastAPI API + SPA 8화면
- `impactnote/main.py`: `impactnote` CLI
- `pyproject.toml`: 패키지·진입점·커버리지에 `impactnote` 포함, `devfolio` 호환 유지

### 2.2 패키징·배포

- Dockerfile: `impactnote/` 복사, 볼륨 경로 변경, 엔트리포인트 `impactnote`
- compose: 서비스명 `impactnote`, 신규 데이터 볼륨, 기존 DevFolio 볼륨 읽기 전용 마운트
- 검증 모드 compose(`docker-compose.verify.yml`)도 서비스명·명령 갱신

### 2.3 문서·CI

- README/GUIDE/CONTRIBUTING/PROJECT-CONTEXT/아키텍처를 현재 기준으로 재작성
- 과거 DevFolio 분석 문서는 아카이브 배너로 보존
- CI·tox·`scripts/check.sh` lint/커버리지 대상에 `impactnote` 추가

---

## 3. 검증 중 발견한 결함과 수정

| # | 증상 | 원인 | 수정 | 검증 |
| --- | --- | --- | --- | --- |
| 1 | 기록 저장 시 `form.get is not a function` 토스트 | `listValue(form, ...)` 에 `FormData` 가 아닌 form 요소 전달 | 호출부 6곳을 `listValue(data, ...)` 로 변경 | 브라우저에서 저장 성공, 목록 반영 |
| 2 | 980px 이하에서 사이드바 아래 큰 빈 공간 | `min-height:100vh` 가 1열 그리드 행을 확장 | `align-content:start` 추가 | 736px 폭 레이아웃 확인 |
| 3 | Docker 에서 마이그레이션이 0건 | `_legacy_projects()` 가 `IMPACTNOTE_LEGACY_DATA_DIR` 을 무시하고 기본 경로만 조회 | 레거시 경로 우선 읽기(ruamel + `Project.model_validate`), 없으면 폴백 | 컨테이너에서 `migrated 2/1`, 원본 해시 불변, 재실행 멱등 |
| 4 | CI·tox·check.sh 가 새 코드를 lint/커버리지하지 않음 | 경로가 `devfolio/` 로 고정 | 세 설정에 `impactnote/` 추가 | `scripts/check.sh` 통과 |

추가로 보고서 기본 템플릿(주간)과 기간(월간) 불일치, 지표 검증 안내 부재를 수정했다.

---

## 4. 테스트 결과

| 명령 | 결과 |
| --- | --- |
| `pytest -q` | **431 passed** (impactnote 30 + 레거시 401) |
| `ruff check impactnote tests` | 통과 |
| `ruff format` | 적용 완료 |
| `node --check impactnote/web/static/app.js` | 통과 |
| `scripts/check.sh` | 통과 |
| pre-commit 훅 | ruff·format·pytest 통과 |

신규 테스트가 고정하는 것:

- 기록 CRUD, 기록→성과, 근거 연결 상태(verified/partial/review)
- 지표 검증(근거·산출 기준·값 대조)
- AI 동의 차단, 실패 시 원본 보존, 수치 `[확인 필요]` 치환
- Git 후보 `needs_review`, AI 후보 확인 전 확정 불가
- 기간 집계 정확성, 템플릿·버전, 다운로드
- 마이그레이션 백업·멱등·원본 보존·레거시 경로 우선
- 브랜드 문자열, `/api/health`·`/api/meta`, 파일 권한 `0600`

---

## 5. 실행 검증 (실측)

### Docker

```
docker compose down --remove-orphans
docker compose up -d --build
→ devfolio-impactnote-1 Up, 0.0.0.0:8000->8000
GET /api/health → 200 {"status":"ok","app":"성과노트","version":"1.0.0"}
GET / → 200
GET /legacy/devfolio-data → 기존 볼륨 내용 확인(읽기 전용)
```

### 컨테이너 E2E (임시 데이터 디렉터리)

기록 생성 → 성과 생성 → 근거 연결(verified) → 지표 추가 → DOCX 보고서 생성 →
MD 다운로드(200, 본문 포함) → AI 동의 차단(409) 확인.

### 마이그레이션 (임시 레거시 데이터)

1회차 `migrated`(기록 2, 성과 1, ZIP 백업 생성) → 2회차 `already_migrated`,
원본 SHA-256 불변, `activities.json` 권한 `0600`.

### 브라우저

대시보드 렌더링 → 업무 기록 빠른 저장 → 성과 관리에서 1건 묶기 → 성과보고서 생성·미리보기.
도중에 폼 버그와 좁은 화면 레이아웃 문제를 발견해 수정 후 재확인했다.

### 검증하지 못한 것

- PDF 실출력(변환 도구·폰트 의존). DOCX 는 컨테이너에서 생성 확인.
- 실제 LLM Provider 호출(비용·키 필요). 게이트·실패·세탁 경로는 모의 호출로 검증.
- 스크린리더·200% 확대·고대비 모드.

---

## 6. 성능

측정하지 않았다. 이번 라운드는 기능 전환·정확성 검증이 목적이며, 응답 시간·대용량 데이터 성능은
별도 측정이 필요하다. (컨테이너 기동·API 응답은 정상 범위였으나 수치로 기록하지 않음)

---

## 7. 남은 위험과 후속 우선순위

1. **지표 검증 UX** — 값이 기록/근거에 없으면 확인 불가. URL 근거만 있는 경우의 확인 절차 설계 필요.
2. **PDF 산출물** — 실제 제출 환경 폰트·표 깨짐 검증.
3. **실 Provider 품질** — 동의 후 실제 호출로 분석 문체·수치 준수 확인.
4. **동시성** — JSON 저장은 프로세스 내 락만 있다. 다중 워커·다중 사용자 확장 시 저장소 교체 필요.
5. **레거시 의존** — 내보내기·AI 계층이 `devfolio/` 에 있어 인터페이스 분리가 장기 과제다.
