# DevFolio — CLAUDE.md

개발자 포트폴리오 & 경력기술서 자동화 CLI (Python).

## 브랜치 & 워크플로우 규칙

- **작업 브랜치**: 항상 로컬 `main` 브랜치에서 직접 작업한다
- **claude/ 브랜치 금지**: `claude/*` worktree 브랜치를 따서 작업하지 않는다
- **커밋 후 push**: 변경이 완료되면 `git push origin main` 으로 바로 푸시한다
- PR/feature 브랜치가 필요할 경우 사용자가 명시적으로 요청할 때만 생성한다

## 필수 명령어

```bash
# 설치
pip install -e ".[dev]"  # 개발 환경
pip install -e ".[all]"  # 모든 기능

# 테스트
pytest                    # 전체 테스트 + 커버리지
pytest -x                 # 첫 실패 시 중단
pytest tests/test_X.py    # 특정 파일만

# 로컬 실행
python -m devfolio.main init
devfolio --help           # 설치 후
```

## 프로젝트 구조

```
devfolio/
├── main.py              # CLI 진입점 (cli() 함수)
├── exceptions.py        # 커스텀 예외 (DevfolioError 하위 클래스)
├── log.py               # stdlib logging wrapper (DEVFOLIO_LOG_LEVEL 제어)
├── i18n.py              # 문자열 카탈로그 (DEVFOLIO_LANG 제어)
├── locales/             # ko.py / en.py 문자열 카탈로그
├── models/
│   ├── project.py       # Project, Task, Period (Pydantic v2)
│   └── config.py        # Config, AIProviderConfig (Pydantic v2)
├── core/
│   ├── storage.py       # YAML 저장소 (platformdirs 경로)
│   ├── project_manager.py  # Project/Task CRUD
│   ├── ai_service.py    # litellm 래퍼 (lazy import)
│   ├── template_engine.py  # Jinja2 렌더링
│   ├── export_engine.py    # MD/PDF/DOCX/HTML/JSON/CSV 내보내기
│   └── sync_service.py  # GitHub 백업 동기화
├── commands/            # Typer 서브 커맨드
│   ├── common.py        # check_init() 공통 유틸리티
│   ├── init_cmd.py      # devfolio init
│   ├── project.py       # devfolio project *
│   ├── task.py          # devfolio task *
│   ├── config.py        # devfolio config *
│   ├── ai.py            # devfolio ai *
│   ├── export.py        # devfolio export *
│   ├── sync.py          # devfolio sync *
│   └── data.py          # devfolio data *
├── utils/
│   └── security.py      # API 키 3단계 폴백 (keyring→env→None)
└── templates/           # 내장 Jinja2 템플릿 (.j2)
    ├── base.md.j2       # 베이스 템플릿 (block 상속)
    └── ...
```

## 핵심 규칙

### ✅ 항상
- Pydantic `model_validate()` / `model_dump()` 사용 (dict 직접 조작 금지)
- `ruamel.yaml` YAML 로드 (yaml.safe_load 아님 — 주석 보존용)
- 오류 시 `DevfolioError` 하위 클래스로 raise, hint 포함
- 무거운 라이브러리(litellm, weasyprint, docxtpl)는 함수 내에서 lazy import
- 설정 파일 권한 `0o600` 유지

### ⚠️ 확인 후 진행
- 기존 YAML 파일 덮어쓰기
- AI API 호출 (비용 발생)

### 🚫 절대 금지
- `yaml.load()` 사용 (반드시 ruamel.yaml 또는 `yaml.safe_load`)
- API 키 평문 로그 출력
- `to_dict()` / `from_dict()` 직접 구현 (Pydantic 메서드 사용)

## 데이터 경로 (platformdirs)

| OS | 설정 | 데이터 |
|----|------|--------|
| macOS | `~/Library/Preferences/devfolio/` | `~/Library/Application Support/devfolio/` |
| Linux | `~/.config/devfolio/` | `~/.local/share/devfolio/` |
| Windows | `%APPDATA%/devfolio/devfolio/` | `%LOCALAPPDATA%/devfolio/devfolio/` |

레거시 경로(`~/.devfolio/`)도 자동 인식.
