# Changelog

이 프로젝트의 주요 변경 사항을 기록합니다. [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따릅니다.

## [Unreleased]

### Added
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
