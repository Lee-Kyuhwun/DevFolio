# Contributing to ImpactNote (성과노트)

Thanks for contributing. 성과노트는 회사 업무 기록·근거 관리·제출용 성과보고서를 만드는
로컬 우선 도구입니다. 기존 DevFolio 자산은 호환 계층으로 유지합니다.

## Development Setup

```bash
git clone https://github.com/Lee-Kyuhwun/DevFolio.git
cd DevFolio
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,all]"
make hooks          # pre-commit hook (once per clone)
scripts/check.sh    # ruff + format check + pytest -x
```

Docker 로 실행할 때:

```bash
docker compose up -d --build     # http://localhost:8000
```

The project targets Python 3.11 or newer.

## Where Things Live

| 경로 | 역할 |
| --- | --- |
| `impactnote/core/` | 도메인 모델, JSON 저장소, 서비스, 기간 집계, 수치 가드레일, AI, 보고서, 마이그레이션 |
| `impactnote/web/` | FastAPI 라우터와 SPA(`static/index.html`, `app.js`, `app.css`) |
| `impactnote/main.py` | `impactnote` CLI (version/init/serve/migrate/activity/achievement/report) |
| `devfolio/` | 레거시 CLI·API·YAML 저장소·내보내기·AI 신뢰성 자산 (호환용, 삭제 금지) |
| `tests/test_impactnote.py` | 새 제품 회귀 테스트 (수치·AI·보고서·마이그레이션·브랜드) |
| `docs/impactnote.md` | 설계, 가드레일, API, 마이그레이션 |

## Project Conventions

- Pydantic v2 `model_validate()` / `model_dump()` 를 사용하고 dict 를 직접 조작하지 않는다.
- YAML 은 `ruamel.yaml` 로 읽는다(레거시 데이터 보존).
- 무거운 의존성(docxtpl, weasyprint, litellm)은 함수 내에서 lazy import 한다.
- 새 저장소는 `impactnote.core.store.JsonStore` 를 쓰고 파일 권한 `0600` 을 유지한다.
- 사용자에게 보이는 실패는 원인과 다음 행동을 함께 안내한다.
- DevFolio 데이터는 **읽기 전용**이다. 마이그레이션은 백업을 만들고 원본을 수정하지 않는다.

## Guardrails (변경 시 특히 주의)

1. 근거 없는 수치가 보고서 본문에 들어가면 안 된다(`impactnote/core/metrics.py`).
2. AI/Git 후보는 사용자가 `confirmed=true` 로 확인하기 전까지 `verified` 가 되면 안 된다.
3. AI 호출은 `Settings.external_ai_consent` 와 `allowed_providers` 를 통과해야 한다.
4. AI 실패 시 원본 Activity 는 그대로 남아야 한다.
5. 마이그레이션은 재실행해도 중복 생성되지 않아야 한다(`source_ref`).

이 규칙을 바꾸는 PR 은 `tests/test_impactnote.py` 에 근거 테스트를 함께 추가한다.

## Pull Request Guidance

- 변경은 작게 유지하고, 동작 변경에는 테스트를 붙인다.
- `scripts/check.sh` 통과를 확인한다(ruff + format + pytest).
- CLI/API/화면 동작이 바뀌면 `README.md` 또는 `docs/impactnote.md` 를 같은 PR 에서 갱신한다.
- DevFolio 호환 경로(`devfolio/`)를 건드리면 기존 401개 테스트가 계속 통과하는지 확인한다.

## Areas That Commonly Need Tests

- Activity/Achievement/Evidence/Metric CRUD 와 상태 계산
- 수치 가드레일(허용/치환)과 보고서 본문 포함 여부
- AI 동의 게이트, Provider 제한, 실패 시 원본 보존
- 기간 집계(주/월/분기/반기/연/사용자 지정)
- 보고서 템플릿·버전·다운로드
- DevFolio → ImpactNote 마이그레이션(백업·멱등·원본 보존)

## Documentation

사용자 흐름이 바뀌면 `README.md` 와 `docs/impactnote.md` 를 갱신한다.
과거 DevFolio 분석·장애 기록은 수정하지 않고 아카이브 배너로 현재 기준을 안내한다.
