# DevFolio

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![CI](https://github.com/Lee-Kyuhwun/DevFolio/actions/workflows/ci.yml/badge.svg)

**Language:** [English](#english) | [한국어](#한국어)

## English

DevFolio is a local-first portfolio and resume studio for developers, with a serve-first web workflow, optional AI-assisted writing, and GitHub backup sync.

## What Is DevFolio?

DevFolio helps you manage your career content as data first.

Instead of rewriting the same resume and portfolio over and over, you keep your projects, tasks, summaries, and export settings in structured YAML-backed records. From there, you can:

- initialize a local workspace with guided prompts
- paste raw project notes into the local web studio and turn them into editable AI drafts
- review and edit project/task drafts before saving anything permanently
- add and update projects and detailed task history from the CLI when you want automation-friendly workflows
- import existing YAML or JSON project files as an advanced migration path
- generate AI-assisted bullet points, summaries, and JD matching reports
- export resumes and portfolios to Markdown, HTML, PDF, DOCX, or JSON
- sync source data and generated artifacts to a GitHub backup repository

## Why DevFolio?

Most resume tools optimize for document editing first. DevFolio takes the opposite approach:

- keep your experience in structured project records
- reuse the same source data across resume, portfolio, and AI workflows
- keep everything local by default
- opt into GitHub backup only when you want it

This makes it easier to update one project once and reuse it across multiple outputs.

## Features

### Portfolio Studio workflow

- `devfolio serve` opens a local Portfolio Studio at `http://127.0.0.1:8000`
- paste free-form project notes, build AI drafts, review them, preview the result, then save/export
- preview works on unsaved draft data, so you can check the output before committing it to storage

### Guided setup

- `devfolio init` walks through user profile, optional AI provider setup, and optional GitHub sync setup.

### Project and task management

- `devfolio project add|list|show|edit|delete`
- `devfolio task add|list|show|edit|delete`
- project and task periods support in-progress records
- duplicate project name collisions are prevented safely

### Import, backup, and restore

- import project data from YAML or JSON with `devfolio data import`
- YAML/JSON import is positioned as advanced import for migration, backup restore, or batch entry
- export all stored projects to JSON with `devfolio data export-json`
- back up and restore local DevFolio data as ZIP archives

### AI-assisted writing

- generate task bullet points
- generate project summaries
- generate a full resume draft
- refine existing text
- analyze portfolio fit against a job description

AI support is optional and works with Anthropic, OpenAI, Gemini, and Ollama.

### Multi-format export

- export resumes with `devfolio export resume`
- export portfolios with `devfolio export portfolio`
- export single-project summaries with `devfolio export project`
- supported formats: `md`, `html`, `pdf`, `docx`, `json`, `csv`
- `--format csv` outputs Excel-compatible UTF-8 BOM encoded spreadsheets

### GitHub backup sync

- `devfolio sync setup`
- `devfolio sync status`
- `devfolio sync run`

Sync stores raw DevFolio data plus generated Markdown and HTML artifacts in a dedicated GitHub repository.

### Internationalization (i18n)

- built-in Korean and English string catalogs
- switch language with `DEVFOLIO_LANG=ko|en` environment variable
- defaults to Korean

### Logging

- structured log output via Python stdlib logging
- control verbosity with `DEVFOLIO_LOG_LEVEL=DEBUG|INFO|WARNING|ERROR`

### Web-based Portfolio Studio

- `devfolio serve` starts the browser-based Portfolio Studio at `http://127.0.0.1:8000`
- manage draft intake, saved projects, preview/export, plus settings from one place
- no local Python needed with Docker — use `docker compose up`

### Docker support

- official `Dockerfile` included (python:3.12-slim + WeasyPrint + CJK fonts)
- run without a local Python setup

### Template inheritance

- Jinja2 block inheritance: `base.md.j2` → `{% block header/projects/footer %}`
- customize individual sections without duplicating the full template

## Getting Started

Choose the method that fits your setup. **Docker** is the easiest — no Python installation needed. **pip** gives you the full CLI including `devfolio scan`.

---

### Method A — Docker (Web UI only, easiest)

> **Requires:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
> Check with: `docker --version`

**Step 1 — Clone the repository**

```bash
git clone https://github.com/Lee-Kyuhwun/DevFolio.git
cd DevFolio
```

**Step 2 — (Optional) Create a `.env` file if you want AI features**

```bash
# create .env in the DevFolio folder — leave blank lines for keys you don't have
cat > .env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
EOF
```

> You can skip this step and add keys later from the web UI settings page.

**Step 3 — Start the web UI**

```bash
docker compose up --build
```

> The first build takes about 1–2 minutes. Subsequent starts are instant.

Open **http://localhost:8000** in your browser.

**Step 4 — Stop**

```bash
docker compose down
```

Your data is saved in Docker named volumes (`devfolio-config`, `devfolio-data`) and survives restarts.

> **If you see errors after pulling new code**, rebuild the image:
> ```bash
> docker compose build --no-cache
> docker compose up
> ```

---

### Method B — pip install (full CLI + scan)

> **Requires:** Python 3.11 or newer.
> Check with: `python3 --version`

**Step 1 — Clone the repository**

```bash
git clone https://github.com/Lee-Kyuhwun/DevFolio.git
cd DevFolio
```

**Step 2 — Create a virtual environment (recommended)**

```bash
python3 -m venv .venv
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows
```

> A virtual environment keeps DevFolio's dependencies isolated from your system Python. You need to activate it each time you open a new terminal (`source .venv/bin/activate`).

**Step 3 — Install**

```bash
pip install -e ".[all]"
```

This installs the `devfolio` command plus all optional features (AI, PDF, DOCX, web UI).

Minimum install (CLI only, no AI/PDF/web):

```bash
pip install -e .
```

**Step 4 — Verify the install**

```bash
devfolio --help
```

If you see the help output, the install succeeded.

---

## Quick Start (after install)

### 1. Initialize DevFolio

```bash
devfolio init
```

This creates your local config and walks you through:
- your name and **email** (required — used to identify your own commits during scanning)
- optional AI provider setup (Anthropic / OpenAI / Gemini / Ollama)
- optional GitHub backup sync

### 2. Scan a git repository — auto-generate your portfolio

```bash
devfolio scan /path/to/your-project
```

DevFolio reads the git history, filters commits authored by **your email**, computes contribution metrics, and saves a portfolio project automatically.

```
scanning /path/to/your-project (author=you@example.com)...
╭─── Scan Summary ──────────────────────────────────────────╮
│ your-project  new scan                                     │
│ 기간: 2025-01 ~ 2026-04                                    │
│ 커밋: 42건 / 전체 대비 87%                                 │
│ 변경: +12430 / -3201 LOC, 95 파일                         │
│ 언어: Python, TypeScript, Go                               │
│ 분류: {'feat': 28, 'fix': 9, 'perf': 5}                   │
╰────────────────────────────────────────────────────────────╯
✓ 새 프로젝트 등록: your-project (sha=a1b2c3d4)
```

Running `devfolio scan` again on the same repository with no new commits returns the cached result instantly. Use `--refresh` to force a re-scan.

```bash
devfolio scan .                          # scan current directory
devfolio scan ~/projects/my-app          # scan by path
devfolio scan . --author you@work.com    # override email
devfolio scan . --refresh                # force re-scan
devfolio scan . --dry-run                # preview without saving
devfolio scan . --yes                    # skip confirmation prompt
```

> **Note:** `devfolio scan` requires the pip install method (Method B). It cannot access local directories from inside Docker without extra volume mount configuration.

### 3. Open the web studio

```bash
devfolio serve          # pip install
# or
docker compose up       # Docker
```

Browse to **http://localhost:8000** to review scanned projects, edit drafts, preview, and export.

### 4. Export a resume or portfolio

```bash
devfolio export resume
devfolio export portfolio --format pdf
```

### 5. (Optional) Add projects or tasks manually via CLI

```bash
devfolio project add
devfolio task add --project "My Project"
```

### 6. (Optional) Configure GitHub backup sync

```bash
devfolio sync setup --repo your-account/devfolio-backup
devfolio sync run
```

---

## Installation

## Import Existing Data

YAML and JSON import are intended for advanced import, migration, or backup restore.

DevFolio ships with a sample YAML file:

```bash
devfolio data import examples/connected_car_gateway.yaml
```

You can also import JSON files:

```bash
devfolio data import ./my-projects.json
```

## Command Overview

### Core workflows

- `devfolio init`
- `devfolio serve`
- `devfolio scan <path>` — git scan → auto-generate portfolio project
- `devfolio project add|list|show|edit|delete`
- `devfolio task add|list|show|edit|delete`

### AI workflows

- `devfolio ai generate task`
- `devfolio ai generate project`
- `devfolio ai generate resume`
- `devfolio ai refine`
- `devfolio ai match-jd`

### Export workflows

- `devfolio export resume --format md|html|pdf|docx|json|csv`
- `devfolio export portfolio --format md|html|pdf|csv`
- `devfolio export project`

### Data workflows

- `devfolio data backup`
- `devfolio data restore`
- `devfolio data import` (advanced import)
- `devfolio data export-json`

### GitHub backup workflows

- `devfolio sync setup`
- `devfolio sync status`
- `devfolio sync run`

### Configuration workflows

- `devfolio config show`
- `devfolio config set-default`
- `devfolio config ai set|list|test|remove`

### Web UI

- `devfolio serve`
- `devfolio serve --host 0.0.0.0 --port 8000 --no-open`

## AI Support

DevFolio supports these providers:

- Anthropic
- OpenAI
- Gemini
- Ollama

AI is optional. You can use DevFolio as a local-only portfolio and resume manager without configuring any provider.

Heavy AI dependencies are loaded lazily, so the base CLI stays lighter unless you explicitly install AI extras.

## Data and Privacy

DevFolio stores project data locally using `platformdirs`.

- config is stored in the OS-specific user config directory
- project data, exports, templates, and sync state are stored in the OS-specific user data directory
- a legacy `~/.devfolio/` path is still recognized automatically

API keys use a keyring-first approach with environment-variable fallback.

GitHub sync is explicit opt-in. Nothing is pushed to GitHub unless you configure sync and run `devfolio sync run`.

## Development

### Local development setup

```bash
pip install -e ".[dev]"
pytest
```

`pytest` runs the project test suite with coverage options defined in `pyproject.toml`.

### Makefile shortcuts

```bash
make dev      # install dev dependencies
make test     # run pytest with coverage
make lint     # ruff check
make format   # ruff format
make all      # lint + type check + test
```

### Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
```

Runs ruff, trailing-whitespace, and YAML checks on every commit.

### Multi-version testing

```bash
tox           # test against Python 3.11, 3.12, 3.13
tox -e lint   # lint only
tox -e type   # mypy type check only
```

### Architecture snapshot

- `devfolio/main.py`: Typer CLI entrypoint and global error handling
- `devfolio/commands/`: user-facing command groups
- `devfolio/models/`: Pydantic v2 models for config, projects, tasks, and periods
- `devfolio/core/`: storage, export, template, AI, sync, and project management logic
- `devfolio/templates/`: built-in Jinja templates
- `devfolio/log.py`: stdlib logging wrapper — level controlled by `DEVFOLIO_LOG_LEVEL`
- `devfolio/i18n.py`: lightweight string catalog — locale set via `DEVFOLIO_LANG`
- `devfolio/locales/`: `ko.py` and `en.py` string catalogs
- `devfolio/commands/common.py`: shared `check_init()` utility
- `devfolio/web/`: FastAPI Portfolio Studio — routes, Jinja2 templates, static assets

### Contributor expectations

- use Pydantic v2 helpers such as `model_validate()` and `model_dump()`
- use `ruamel.yaml` for YAML handling
- keep heavyweight dependencies lazily imported where appropriate
- raise user-facing failures through `DevfolioError` subclasses

For contribution workflow details, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Limitations / Current Status

- Python 3.11+ is required
- CI runs on Python 3.11, 3.12, and 3.13 via GitHub Actions
- the project is a source-first CLI tool, not a hosted web service
- PDF export may require additional platform-specific system libraries depending on your environment

## Contributing

Contributions are welcome. For setup, coding expectations, and pull request guidance, see [CONTRIBUTING.md](CONTRIBUTING.md).

For large feature changes, open an issue or discussion first so scope and direction are aligned before implementation.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

---

## 한국어

DevFolio는 개발자를 위한 로컬 우선 포트폴리오/경력기술서 스튜디오입니다. `devfolio serve` 기반 웹 흐름을 중심으로, 필요하면 AI 문구 생성과 GitHub 백업 동기화까지 함께 사용할 수 있습니다.

## DevFolio란?

DevFolio는 경력 문서를 "문서"보다 "데이터"로 먼저 관리할 수 있게 설계되어 있습니다.

이력서나 포트폴리오를 매번 새로 쓰는 대신, 프로젝트, 작업 내역, 요약, 출력 설정을 YAML 기반 구조화 데이터로 저장합니다. 그 다음 이 데이터를 바탕으로 다음 작업을 할 수 있습니다.

- 대화형 초기 설정으로 로컬 작업 공간 구성
- 자유 텍스트 작업물을 웹 스튜디오에 붙여넣고 AI 초안으로 구조화
- 저장 전에 프로젝트/작업 초안을 검토하고 수정
- 필요하면 CLI로 프로젝트와 세부 작업 이력 추가 및 수정
- YAML 또는 JSON 프로젝트 데이터 가져오기 (고급 import / 이관용)
- AI 기반 bullet point, 요약, JD 매칭 결과 생성
- Markdown, HTML, PDF, DOCX, JSON 형식으로 문서 내보내기
- 원본 데이터와 산출물을 GitHub 백업 저장소에 동기화

## 왜 DevFolio인가?

대부분의 이력서 도구는 문서 편집을 먼저 생각합니다. DevFolio는 반대로 접근합니다.

- 경력을 구조화된 프로젝트 데이터로 관리
- 하나의 원본 데이터를 이력서, 포트폴리오, AI 워크플로우에 재사용
- 기본적으로 로컬 우선 저장
- 필요할 때만 GitHub 백업 동기화 사용

이 방식이면 프로젝트 하나를 한 번만 수정해도 여러 산출물에 재활용할 수 있습니다.

## 주요 기능

### Portfolio Studio 기본 흐름

- `devfolio serve` 로 로컬 Portfolio Studio를 `http://127.0.0.1:8000` 에서 실행
- 작업물 붙여넣기 → AI draft 생성 → 검토/수정 → preview/export 까지 한 화면 흐름으로 진행
- 저장 전 draft 상태에서도 preview 가능

### 대화형 초기 설정

- `devfolio init` 으로 사용자 정보, 선택적 AI 설정, 선택적 GitHub sync 설정을 한 번에 진행합니다.

### 프로젝트 / 작업 내역 관리

- `devfolio project add|list|show|edit|delete`
- `devfolio task add|list|show|edit|delete`
- 진행 중인 프로젝트와 작업 기간 표현 지원
- 중복 프로젝트 이름 충돌을 안전하게 방지

### 가져오기 / 백업 / 복원

- `devfolio data import` 로 YAML 또는 JSON 프로젝트 데이터 가져오기
- YAML/JSON import는 일반 입력 경로가 아니라 기존 데이터 이관, 백업 복원, 일괄 입력용 고급 기능
- `devfolio data export-json` 로 전체 프로젝트 JSON 내보내기
- ZIP 기반 전체 데이터 백업 및 복원

### AI 기반 문구 생성

- 작업 내역 bullet point 생성
- 프로젝트 요약 생성
- 전체 경력기술서 초안 생성
- 기존 문구 개선
- JD와 포트폴리오 매칭 분석

AI 기능은 선택 사항이며 Anthropic, OpenAI, Gemini, Ollama를 지원합니다.

### 다중 포맷 내보내기

- `devfolio export resume`
- `devfolio export portfolio`
- `devfolio export project`
- 지원 포맷: `md`, `html`, `pdf`, `docx`, `json`, `csv`
- `--format csv`: Excel 호환 UTF-8 BOM 인코딩으로 출력

### GitHub 백업 동기화

- `devfolio sync setup`
- `devfolio sync status`
- `devfolio sync run`

동기화는 DevFolio 원본 데이터와 생성된 Markdown / HTML 산출물을 전용 GitHub 저장소에 보관합니다.

### 다국어 지원 (i18n)

- 한국어 / 영어 문자열 카탈로그 내장
- `DEVFOLIO_LANG=ko|en` 환경변수로 언어 전환
- 기본값: 한국어

### 로깅

- Python stdlib logging 기반 구조화 출력
- `DEVFOLIO_LOG_LEVEL=DEBUG|INFO|WARNING|ERROR` 로 상세도 제어

### 웹 기반 Portfolio Studio

- `devfolio serve` 로 브라우저 Portfolio Studio를 `http://127.0.0.1:8000` 에서 실행
- intake, 저장된 프로젝트, preview/export, 설정을 한 화면에서 관리
- Docker에서는 `docker compose up` 한 명령으로 실행 가능

### Docker 지원

- `Dockerfile` 제공 (python:3.12-slim + WeasyPrint + CJK fonts)
- 로컬 Python 설치 없이 실행 가능

### 템플릿 상속

- Jinja2 block 상속: `base.md.j2` → `{% block header/projects/footer %}`
- 전체 템플릿 복사 없이 특정 섹션만 커스터마이징 가능

## 시작하기

설치 방법은 두 가지입니다. **Docker**는 Python 설치 없이 가장 빠르게 시작할 수 있습니다. **pip**은 `devfolio scan` 을 포함한 모든 기능을 사용할 수 있습니다.

---

### 방법 A — Docker (웹 UI 전용, 가장 쉬움)

> **필요:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) 설치 및 실행 중이어야 합니다.
> 설치 확인: `docker --version`

**1단계 — 저장소 클론**

```bash
git clone https://github.com/Lee-Kyuhwun/DevFolio.git
cd DevFolio
```

**2단계 — (선택) AI 기능을 사용하려면 `.env` 파일 생성**

```bash
# DevFolio 폴더 안에 .env 파일 생성 — 없는 키는 빈칸으로 두면 됩니다
cat > .env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
EOF
```

> 이 단계를 건너뛰어도 됩니다. 나중에 웹 UI 설정 페이지에서 추가할 수 있습니다.

**3단계 — 웹 UI 시작**

```bash
docker compose up --build
```

> 처음 빌드는 1~2분 소요됩니다. 이후 재시작은 즉시 됩니다.

브라우저에서 **http://localhost:8000** 으로 접속하세요.

**4단계 — 종료**

```bash
docker compose down
```

데이터는 Docker named volume (`devfolio-config`, `devfolio-data`) 에 저장되어 재시작 후에도 유지됩니다.

> **새 코드를 받은 뒤 에러가 나면** 이미지를 다시 빌드하세요:
> ```bash
> docker compose build --no-cache
> docker compose up
> ```

---

### 방법 B — pip 설치 (전체 CLI + scan 기능)

> **필요:** Python 3.11 이상.
> 버전 확인: `python3 --version`

**1단계 — 저장소 클론**

```bash
git clone https://github.com/Lee-Kyuhwun/DevFolio.git
cd DevFolio
```

**2단계 — 가상 환경 생성 (권장)**

```bash
python3 -m venv .venv
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows
```

> 가상 환경을 사용하면 DevFolio 의존성이 시스템 Python과 분리됩니다.
> 터미널을 새로 열 때마다 `source .venv/bin/activate` 로 활성화해야 합니다.

**3단계 — 설치**

```bash
pip install -e ".[all]"
```

AI, PDF, DOCX, 웹 UI 를 포함한 모든 기능을 설치합니다.

CLI 전용 최소 설치 (AI/PDF/웹 UI 제외):

```bash
pip install -e .
```

**4단계 — 설치 확인**

```bash
devfolio --help
```

도움말이 출력되면 설치가 완료된 것입니다.

---

## 빠른 시작 (설치 후)

### 1. DevFolio 초기화

```bash
devfolio init
```

로컬 설정 파일을 만들고 아래 항목을 순서대로 안내합니다:
- 이름 및 **이메일** (필수 — git 저장소 스캔 시 본인 커밋을 식별하는 데 사용됩니다)
- AI Provider 설정 (Anthropic / OpenAI / Gemini / Ollama) — 선택
- GitHub 백업 sync 설정 — 선택

### 2. Git 저장소 스캔 — 포트폴리오 자동 생성

```bash
devfolio scan /path/to/your-project
```

DevFolio가 git 이력을 읽고 **본인 이메일로 작성된 커밋만** 필터링해 기여 지표를 산출한 뒤, 포트폴리오 프로젝트를 자동으로 저장합니다.

```
scanning /path/to/your-project (author=you@example.com)...
╭─── Scan Summary ──────────────────────────────────────────╮
│ your-project  new scan                                     │
│ 기간: 2025-01 ~ 2026-04                                    │
│ 커밋: 42건 / 전체 대비 87%                                 │
│ 변경: +12430 / -3201 LOC, 95 파일                         │
│ 언어: Python, TypeScript, Go                               │
│ 분류: {'feat': 28, 'fix': 9, 'perf': 5}                   │
╰────────────────────────────────────────────────────────────╯
✓ 새 프로젝트 등록: your-project (sha=a1b2c3d4)
```

같은 저장소를 다시 스캔할 때 새 커밋이 없으면 캐시에서 즉시 결과를 반환합니다 (재분석 없음).
`--refresh` 를 사용하면 HEAD SHA 변경 여부에 관계없이 강제로 재분석합니다.

```bash
devfolio scan .                          # 현재 디렉터리 스캔
devfolio scan ~/projects/my-app          # 경로 지정
devfolio scan . --author you@work.com    # 이메일 직접 지정
devfolio scan . --refresh                # 강제 재스캔
devfolio scan . --dry-run                # 저장 없이 미리보기
devfolio scan . --yes                    # 확인 없이 바로 저장
```

> **참고:** `devfolio scan` 은 pip 설치 방법(방법 B)에서만 사용 가능합니다.
> Docker 환경에서는 별도 볼륨 마운트 없이 로컬 디렉터리를 접근할 수 없습니다.

### 3. 웹 스튜디오 열기

```bash
devfolio serve          # pip 설치 후
# 또는
docker compose up       # Docker 사용 시
```

**http://localhost:8000** 에서 스캔된 프로젝트를 확인하고, 초안 편집 및 내보내기를 할 수 있습니다.

### 4. 이력서/포트폴리오 내보내기

```bash
devfolio export resume
devfolio export portfolio --format pdf
```

### 5. (선택) CLI로 프로젝트/작업 직접 입력

```bash
devfolio project add
devfolio task add --project "My Project"
```

### 6. (선택) GitHub 백업 sync 설정

```bash
devfolio sync setup --repo your-account/devfolio-backup
devfolio sync run
```

---

## 설치 세부 옵션

## 기존 데이터 가져오기

YAML/JSON import는 고급 import, 이관, 백업 복원 용도입니다.

예시 YAML 파일이 함께 제공됩니다.

```bash
devfolio data import examples/connected_car_gateway.yaml
```

JSON 파일도 가져올 수 있습니다.

```bash
devfolio data import ./my-projects.json
```

## 명령 개요

### 기본 워크플로우

- `devfolio init`
- `devfolio serve`
- `devfolio scan <경로>` — git 스캔 → 포트폴리오 자동 생성
- `devfolio project add|list|show|edit|delete`
- `devfolio task add|list|show|edit|delete`

### AI 워크플로우

- `devfolio ai generate task`
- `devfolio ai generate project`
- `devfolio ai generate resume`
- `devfolio ai refine`
- `devfolio ai match-jd`

### 내보내기 워크플로우

- `devfolio export resume --format md|html|pdf|docx|json|csv`
- `devfolio export portfolio --format md|html|pdf|csv`
- `devfolio export project`

### 데이터 워크플로우

- `devfolio data backup`
- `devfolio data restore`
- `devfolio data import` (고급 import)
- `devfolio data export-json`

### GitHub 백업 워크플로우

- `devfolio sync setup`
- `devfolio sync status`
- `devfolio sync run`

### 설정 워크플로우

- `devfolio config show`
- `devfolio config set-default`
- `devfolio config ai set|list|test|remove`

### 웹 UI

- `devfolio serve`
- `devfolio serve --host 0.0.0.0 --port 8000 --no-open`

## AI 지원

DevFolio는 다음 Provider를 지원합니다.

- Anthropic
- OpenAI
- Gemini
- Ollama

AI는 필수가 아닙니다. Provider를 하나도 설정하지 않고 로컬 전용 포트폴리오/이력서 관리 도구로만 사용해도 됩니다.

무거운 AI 의존성은 lazy import 방식으로 불러오므로, AI extra를 설치하지 않아도 기본 CLI는 상대적으로 가볍게 유지됩니다.

## 데이터와 프라이버시

DevFolio는 `platformdirs` 기반으로 로컬에 데이터를 저장합니다.

- config는 OS별 사용자 config 디렉터리에 저장
- 프로젝트 데이터, export 결과, 템플릿, sync 상태는 OS별 사용자 data 디렉터리에 저장
- 레거시 `~/.devfolio/` 경로도 자동 인식

API 키는 keyring 우선, 환경 변수 fallback 방식으로 관리합니다.

GitHub sync는 명시적 opt-in 기능입니다. sync를 설정하고 `devfolio sync run`을 실행하기 전에는 아무 것도 GitHub로 푸시되지 않습니다.

## 개발

### 로컬 개발 환경

```bash
pip install -e ".[dev]"
pytest
```

`pytest`는 `pyproject.toml`에 정의된 테스트/커버리지 설정을 사용합니다.

### Makefile 단축 명령

```bash
make dev      # 개발 의존성 설치
make test     # pytest + coverage 실행
make lint     # ruff check 실행
make format   # ruff format 실행
make all      # lint + type check + test 전체 실행
```

### Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
```

커밋마다 ruff, trailing-whitespace, YAML 검사를 자동으로 실행합니다.

### 멀티버전 테스트

```bash
tox           # Python 3.11, 3.12, 3.13 전체 테스트
tox -e lint   # lint only
tox -e type   # mypy type check only
```

### 아키텍처 개요

- `devfolio/main.py`: Typer CLI 진입점과 전역 오류 처리
- `devfolio/commands/`: 사용자-facing 명령 그룹
- `devfolio/models/`: config, project, task, period용 Pydantic v2 모델
- `devfolio/core/`: storage, export, template, AI, sync, project management 로직
- `devfolio/templates/`: 내장 Jinja 템플릿
- `devfolio/log.py`: stdlib logging wrapper — `DEVFOLIO_LOG_LEVEL` 로 레벨 제어
- `devfolio/i18n.py`: 경량 문자열 카탈로그 — `DEVFOLIO_LANG` 으로 로케일 설정
- `devfolio/locales/`: `ko.py` 및 `en.py` 문자열 카탈로그
- `devfolio/commands/common.py`: 공통 `check_init()` 유틸리티
- `devfolio/web/`: FastAPI Portfolio Studio — 라우터, Jinja2 템플릿, 정적 파일

### 기여 시 기대 사항

- `model_validate()`, `model_dump()` 같은 Pydantic v2 helper 사용
- YAML 처리는 `ruamel.yaml` 사용
- 무거운 의존성은 필요할 때 lazy import 유지
- 사용자에게 보이는 오류는 `DevfolioError` 하위 클래스로 처리

기여 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 현재 상태 / 제한 사항

- Python 3.11+ 필요
- CI는 GitHub Actions에서 Python 3.11, 3.12, 3.13 매트릭스로 실행됨
- 이 프로젝트는 호스팅형 서비스가 아니라 소스 중심 CLI 도구임
- PDF export는 환경에 따라 추가 시스템 라이브러리가 필요할 수 있음

## 기여하기

기여는 언제든 환영합니다. 개발 환경 설정, 코딩 규칙, PR 가이드는 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

규모가 큰 기능 변경은 구현 전에 issue 또는 discussion으로 먼저 방향을 맞추는 것을 권장합니다.

## 라이선스

이 프로젝트는 MIT License를 따릅니다. 자세한 내용은 [LICENSE](LICENSE)를 참고하세요.
