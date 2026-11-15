# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다. [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따릅니다.

## [1.0.0] — 2026-11-15

### Changed
- 제품을 **성과노트(ImpactNote)** 로 전환: 개발자 포트폴리오 생성기 → 회사 업무 기록·근거 관리·제출용 성과보고서 도구
- 새 도메인: Activity / Achievement / Evidence / Metric / Goal / Report / AIAnalysis
- 진입점 `impactnote` 추가, 기존 `devfolio` CLI·API·데이터는 호환 계층으로 유지
- Docker 서비스·볼륨·문서 브랜드 변경, DevFolio 데이터는 읽기 전용 마이그레이션 원본으로 마운트

### Added
- 근거 없는 수치 차단(`[확인 필요]` 치환) + 검증 지표만 본문에 사용하는 보고서 파이프라인
- AI 전송 동의·허용 Provider 게이트(기본 차단), AI 실패 시 원본 기록 보존
- Git 커밋 기반 성과 후보 추출(`needs_review`, 사용자 확인 전 확정 불가)
- 보고서 템플릿 A~E, 기간 선택(주/월/분기/반기/연/사용자 지정), 버전·제출 상태, MD/DOCX/PDF/TXT/CSV
- DevFolio → ImpactNote 마이그레이션(ZIP 백업·멱등·원본 보존)
- `impactnote` 패키지·CLI·Docker 서비스, 레거시 데이터 읽기 전용 마운트
- CI·tox·`scripts/check.sh` 에 `impactnote` lint/커버리지 포함
- 문서 체계 정비: README·GUIDE·설계·아키텍처 현재화, 과거 DevFolio 문서는 아카이브 배너로 보존

## [Unreleased]

### Added
- 웹 기반 설정 GUI (`devfolio serve` — FastAPI + Jinja2, 포트 8000)
- `docker-compose.yml` — 한 명령으로 GUI 실행 (`docker compose up`)
- `gui` extra — `pip install 'devfolio[gui]'` (fastapi, uvicorn)
- GitHub Actions CI/CD 파이프라인 (Python 3.11/3.12/3.13 매트릭스, lint, 테스트)
- 로깅 프레임워크 (`DEVFOLIO_LOG_LEVEL` 환경변수로 레벨 제어)
- Export 경로 검증 (path traversal 방지)
- Git branch 이름 유효성 검사
- Makefile 및 pre-commit hooks 설정
- i18n 프레임워크 (`devfolio/i18n.py` + `locales/ko.py`, `locales/en.py`)
- CSV Export 포맷 — `devfolio export resume --format csv` / `devfolio export portfolio --format csv`
- 템플릿 상속/블록 시스템 (`base.md.j2` → `{% block header/projects/footer %}`)
- Docker 지원 (`Dockerfile`, `.dockerignore`)
- tox.ini — Python 3.11/3.12/3.13 멀티버전 테스트
- `devfolio/commands/common.py` — `check_init()` 공통 유틸리티
- `Config.timezone` 필드 — 타임존 설정 가능화

### Fixed
- Jinja2 autoescape 비활성화 → HTML 템플릿에 대해 autoescape 활성화 (XSS 방지)
- HTML title injection 취약점 수정 (`html.escape` 적용)
- `_simple_md_to_html` fallback에서 사용자 데이터 HTML escape 누락 수정
- 손상된 프로젝트 파일을 조용히 건너뛰던 동작 → 경고 로그 출력

### Changed
- 의존성 버전 상한 추가 (주요 라이브러리 major version 변경 방지)
- CLI 명령 함수에 return type hints 추가
- `_check_init()` 중복 제거 → 공통 유틸리티로 통합
- 하드코딩된 타임존(Asia/Seoul) → 설정 파일에서 읽도록 변경

## [0.1.0] - 2025-01-01

### Added
- 프로젝트/태스크 CRUD (CLI 기반)
- 경력기술서/포트폴리오 내보내기 (Markdown, PDF, DOCX, HTML, JSON)
- AI 기반 텍스트 생성 (litellm: Anthropic, OpenAI, Gemini, Ollama)
- GitHub 백업 동기화
- Jinja2 기반 템플릿 시스템
- Keyring 기반 API 키 보안 관리
- YAML 기반 프로젝트 데이터 저장
- Interactive 초기 설정 (`devfolio init`)
- ZIP 백업/복원
- JD 매칭 분석
