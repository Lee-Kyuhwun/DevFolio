# 성과노트 (ImpactNote) — AGENTS.md

회사 업무 기록·근거 관리·제출용 성과보고서 도구 (Python, 로컬 우선).

- 제품 본체: `impactnote/`
- 호환 계층: `devfolio/` (기존 CLI/API/YAML/내보내기/AI 신뢰성, 삭제 금지)
- 기준 문서: `README.md`, `docs/impactnote.md`, `docs/04-architecture.md`

## Ponytail Engineering Mode (FULL, 기본)

- 공식 원문: `docs/ponytail/` (MIT, commit `96608e078b2d5ea607c5c3b8b5a54d1c1fba6846`)
- 기본 강도는 **FULL**이다. 사용자가 `Ponytail lite|full|ultra|off`를 말하면 그 세션에서만 바꾼다.
- 작업 순서: Understand → Reuse → Simplify → Implement → Verify → Review → Report.
- 가장 작은 완전한 변경을 우선하고, 요청하지 않은 기능·추상화·의존성·설정을 추가하지 않는다.
- 호출자·테스트·fixture·문서까지 확인한다. 단순화를 이유로 검증·보안·접근성·오류 처리를 줄이지 않는다.
- 기존 코드와 패턴을 재사용한다. `devfolio/` 호환 계층은 dead code처럼 보여도 삭제하지 않는다.
- `Ponytail Review`/`코드 검토`: 미커밋 diff → 없으면 최근 커밋; 수정 없이 Must/Should/Nice 보고서.
- `Ponytail Audit`: 저장소 전체를 조사해 중요도순 보고서; 요청 없이 전체 재작성 금지.
- `Ponytail Debt`: `shortcut:`/`ponytail:` 주석을 파일·제한·업그레이드 시점과 함께 기록.
- `Ponytail Gain`: 공식 벤치마크 또는 실제 전후 측정값만 사용하고, 이 저장소의 절감량을 만들어내지 않는다.
- 이 환경에는 Ponytail 플러그인 런타임·슬래시 명령·자동 훅이 없다. 파일·Git·테스트 도구로 수동 재현하며, 실행한 척하지 않는다.
- 충돌 시 ImpactNote의 제품 가드레일·보안·호환성 규칙이 Ponytail보다 우선한다.

## 브랜치 & 워크플로우 규칙

- **작업 브랜치**: 항상 로컬 `main` 브랜치에서 직접 작업한다
- **별도 브랜치 금지**: `claude/*` 등의 자동 생성 브랜치를 따서 작업하지 않는다
- **커밋 후 push**: 변경이 완료되면 `git push origin main` 으로 바로 푸시한다
- PR/feature 브랜치가 필요할 경우 사용자가 명시적으로 요청할 때만 생성한다

## 커밋 규칙

- AI 에이전트가 작성한 커밋은 `Co-Authored-By:` 트레일러로 표시한다 (협업 방식: `docs/ai-collaboration.md`)
- 커밋 메시지는 무엇을 왜 바꿨는지 간결하게 쓴다 (한국어)

## 필수 명령어

```bash
# 설치
pip install -e ".[dev]"   # 개발 환경
pip install -e ".[all]"   # 모든 기능
make hooks                 # git pre-commit 훅 설치 (클론 후 1회)
make check                 # 커밋 전 검증: ruff + format + pytest -x (훅과 동일)

# 테스트
pytest                                        # 전체 (2026-11-15 기준 465개)
pytest tests/test_impactnote.py -q --no-cov   # 성과노트 회귀만
scripts/check.sh                              # CI 와 동일한 검증

# 로컬 실행
impactnote init
impactnote serve            # http://127.0.0.1:8000
impactnote migrate          # DevFolio 데이터 이전 (백업·멱등)

# Docker
docker compose up -d --build
```

## 프로젝트 구조

```
impactnote/
├── __init__.py            # APP_NAME/APP_NAME_EN/APP_SLUG/__version__
├── main.py                # Typer CLI (cli()) — version/init/serve/migrate/activity/achievement/report
├── core/
│   ├── models.py          # Activity, Achievement, Evidence, Metric, Goal, Report, AIAnalysis, Settings
│   ├── store.py           # JsonStore(원자적 쓰기, 0600), 데이터/설정/레거시 경로
│   ├── service.py         # ImpactService — CRUD, 상태 계산, 기간 집계, 대시보드
│   ├── periods.py         # 주/월/분기/반기/연/사용자 지정 기간
│   ├── metrics.py         # 수치 주장 추출·검증·[확인 필요] 치환
│   ├── ai.py              # AI 동의 게이트, 분석 저장, Git 후보
│   ├── report.py          # 템플릿 A~E, 버전, MD/DOCX/PDF/TXT/CSV
│   └── migrate.py         # DevFolio → Activity/Achievement (ZIP 백업·멱등)
└── web/
    ├── app.py             # create_app(): "/", "/static", "/api"
    ├── api.py             # REST 계약
    └── static/            # index.html, app.js, app.css, favicon.svg

devfolio/                  # 레거시 호환: YAML 저장소, CLI/API, export_engine, ai_service
evals/impact/              # NVIDIA Ground Truth 평가 하네스
tests/test_impactnote.py   # 성과노트 회귀 테스트
tests/                     # 레거시 + AI 평가 회귀 (2026-11-15 기준 465개)
docs/impactnote.md         # 설계·가드레일·API·마이그레이션
```

## 핵심 규칙

### ✅ 항상
- 실서비스 장애나 에이전트 실수를 고치면 같은 커밋에서 `docs/agent-incidents.md` 항목과 `test_incNN_` 회귀 테스트를 추가한다 ("기존 장치가 못 막은 이유" 필수, 조치를 되돌리면 테스트가 실패하는지 확인)
- Pydantic `model_validate()` / `model_dump()` 사용 (dict 직접 조작 금지)
- `ruamel.yaml` YAML 로드 (yaml.safe_load 아님 — 주석 보존용)
- 오류 시 `DevfolioError` 하위 클래스로 raise, hint 포함 (레거시) / `NotFound`·`ValueError` 를 API 에서 사용자 메시지로 변환 (impactnote)
- 무거운 라이브러리(litellm, weasyprint, docxtpl)는 함수 내에서 lazy import
- 저장 파일 권한 `0o600` 유지 (`JsonStore`), 설정 파일도 동일
- 로깅은 `devfolio.log.get_logger(__name__)` 사용
- 모든 command 함수에 `-> None` 반환 타입 명시
- DevFolio 데이터는 읽기 전용으로만 접근하고, 이전은 백업 후 멱등하게 수행한다

### 🔒 제품 가드레일 (변경 시 테스트 필수)
- 근거 없는 수치가 보고서 본문에 들어가면 안 된다 (`core/metrics.py`, `core/report.py`)
- AI/Git 후보는 사용자가 `confirmed=true` 로 확인하기 전까지 `verified` 가 되면 안 된다 (`_apply_status`)
- AI 호출은 `Settings.external_ai_consent` 와 `allowed_providers` 를 통과해야 한다 (기본 차단)
- AI 실패 시 원본 Activity 는 변경되지 않아야 한다 (`AIAnalysis.status="failed"`)
- 마이그레이션은 재실행해도 중복 생성되지 않아야 한다 (`source_ref`, `migration.json`)

### ⚠️ 확인 후 진행
- 기존 YAML/JSON 파일 덮어쓰기
- AI API 호출 (비용 발생)
- DevFolio 원본 데이터에 쓰기 (원칙적으로 금지)

### 🚫 절대 금지
- `yaml.load()` 사용 (반드시 ruamel.yaml 또는 `yaml.safe_load`)
- API 키 평문 로그 출력·커밋
- `to_dict()` / `from_dict()` 직접 구현 (Pydantic 메서드 사용)
- HTML 출력에 사용자 데이터 미이스케이프 삽입 (XSS 방지)
- `../` 포함 export 경로 허용 (path traversal 방지)
- 검증되지 않은 수치를 보고서 본문에 넣기

## 환경변수

| 변수 | 값 | 설명 |
|------|----|------|
| `IMPACTNOTE_DATA_DIR` | 경로 | 데이터 디렉터리 재정의 (테스트·Docker) |
| `IMPACTNOTE_CONFIG_DIR` | 경로 | 설정 디렉터리 재정의 |
| `IMPACTNOTE_LEGACY_DATA_DIR` | 경로 | DevFolio 원본 데이터 위치 |
| `IMPACTNOTE_LEGACY_CONFIG_DIR` | 경로 | DevFolio 원본 설정 위치 |
| `IMPACTNOTE_LOG_LEVEL` | `DEBUG\|INFO\|WARNING\|ERROR` | 로그 상세도 |
| `IMPACTNOTE_LANG` | `ko\|en` | UI 언어 |
| `GROQ_API_KEY` 등 | 키 | AI Provider 키 (동의 후에만 사용) |
| `DEVFOLIO_LOG_LEVEL`, `DEVFOLIO_LANG` | — | 레거시 계층용 (호환 유지) |

## 데이터 경로 (platformdirs)

| OS | 설정 | 데이터 |
|----|------|--------|
| macOS | `~/Library/Preferences/impactnote/` | `~/Library/Application Support/impactnote/` |
| Linux | `~/.config/impactnote/` | `~/.local/share/impactnote/` |
| Windows | `%APPDATA%/impactnote/impactnote/` | `%LOCALAPPDATA%/impactnote/impactnote/` |

DevFolio 원본은 `devfolio` 경로(및 레거시 `~/.devfolio/`)를 읽기 전용으로 사용한다.
