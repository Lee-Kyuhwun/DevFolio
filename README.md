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

> The first build takes about 1–2 minutes. After that, the container bind-mounts your local source tree and runs with auto-reload, so most code, template, and static-file edits show up without rebuilding the image.

Open **http://localhost:8000** in your browser.

**Step 4 — Stop**

```bash
docker compose down
```

Your data is saved in Docker named volumes (`devfolio-config`, `devfolio-data`) and survives restarts.

> **When do you still need to rebuild?**
> Rebuild only when the container image itself must change, such as:
> - `pyproject.toml` dependencies changed
> - `Dockerfile` changed
> - system packages or Python extras changed
>
> In those cases:
> ```bash
> docker compose build --no-cache
> docker compose up
> ```

> For normal Python, HTML template, CSS, or JS edits, `docker compose up` is enough and the server reloads automatically.

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

> **Note:** `devfolio scan` works with pip install directly, and the web UI scan also works in Docker if the target repository is under `REPOS_DIR` (default: your home directory). In Docker, you can paste the host path as-is (`/Users/...` or `/home/...`) and DevFolio will map it to the container path automatically.
>
> To inspect scan logs in Docker:
> ```bash
> docker compose logs -f
> ```

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

## Running and Using DevFolio (step by step)

This section walks through a full first session: install → configure → open the studio → add an experience → build a document → export it. Every command and screen name below matches the current code.

### Step 1 — Check the install

```bash
devfolio --help          # command list
devfolio serve --help    # web studio options
```

If `devfolio serve` prints `웹 UI를 실행하려면 gui extra가 필요합니다`, your install is CLI-only. Add the web extra:

```bash
pip install -e ".[gui]"     # web studio only
pip install -e ".[all]"     # + AI, PDF, DOCX
```

| Extra | What it enables |
|---|---|
| (base) | CLI, YAML storage, Markdown/HTML export |
| `ai` | AI drafting via litellm |
| `pdf` | PDF export (WeasyPrint + Markdown) |
| `docx` | DOCX export |
| `gui` | FastAPI + Uvicorn web studio |

### Step 2 — First-time configuration

```bash
devfolio init            # --force to reconfigure
```

Prompts, in order:

| Prompt | Notes |
|---|---|
| Name | shown at the top of generated documents |
| Email | **required** — used as the default author filter for Git scans |
| GitHub / Blog | optional, appear in document headers |
| Use AI features? | default **No**. You can add providers later in Settings → AI |
| Provider (1–5) | Anthropic / OpenAI / Gemini / Ollama / skip for now |
| Model | numbered pick from a per-provider list |
| API key | masked input; stored in the OS keyring, falls back to an env var |
| Ollama URL | only for Ollama (default `http://localhost:11434`) |
| GitHub backup? | optional; asks for `owner/repo` and a branch |

The config is written to the OS config directory with `0600` permissions. You can skip `init` entirely and fill in the same values inside the studio under **Settings → Profile**.

### Step 3 — Start the studio

```bash
devfolio serve
```

It prints the URL, opens your browser after one second, and stops with `Ctrl+C`.

| Option | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address. Use `0.0.0.0` only inside a container (see the security note below) |
| `--port` | `8000` | Port |
| `--open` / `--no-open` | open | Auto-open the browser |
| `--reload` / `--no-reload` | no reload | Restart on code change (development only) |

Docker users should use `--host 0.0.0.0 --no-open --reload` (the entrypoint already does). If the port is busy, pick another: `devfolio serve --port 8010`.

### Step 4 — Know the six screens

The studio is a single page with hash routing. The sidebar order is the intended workflow.

| Screen | Purpose |
|---|---|
| **Dashboard** | Counts by type, document readiness, and "next actions" derived from your current state |
| **Experiences** | List + editor for every experience. Card/table view, type filter, search |
| **Generate** | 4-step wizard: document type → which experiences → tone → create session |
| **Editor** | Left rail to reorder/hide sections, right side live preview |
| **Export** | Pick template + format, export, open the output folder |
| **Settings** | Tabs: Profile · AI · Export · General · AI Logs |

**Settings → AI Logs** shows every AI request (provider, model, latency, character counts, status) without leaving the app.

### Step 5 — Add an experience (three ways)

An *experience* is any project or case you want to reuse across documents. Types: **실무 / 개인 / 학습 / 토이** (work / personal / study / toy).

**A. Type it in**

1. **Experiences → 새 경험 추가**
2. The editor has five sections; fill them in any order:

| Section | What goes in it |
|---|---|
| Import / Intake | raw text or a Git repo path (see B and C) |
| Basics | type, status, priority (1–5), title, organization, role, team size, period, **document targets** |
| Narrative | one-line summary, summary, background, problem, target users, goals, non-goals |
| Tasks & Tech | tech stack and per-task problem → solution → result |
| Links & Delivery | canonical links (GitHub/demo/docs/video), extra links, tags, raw notes |

3. **Save.** Draft values are read from the form when you click a button, so switch sections freely before saving.

> **document targets matter**: an experience only appears in the Generate step for the document types you tick (이력서 / 경력기술서 / 포트폴리오). If it is missing from a document, this is the first thing to check.

**B. Paste free-form notes (needs an AI provider)**

1. **Experiences → 새 경험 추가 → Import / Intake**
2. Paste project notes into the textarea
3. **텍스트로 초안 생성** — the draft fields are filled for you; review and edit before saving

**C. Scan a Git repository**

1. **Import / Intake → Git Scan**
2. Enter a **local** repository path (remote URLs are rejected — clone first). **찾아보기** opens a folder picker.
3. Author email defaults to `user.email` from your config. Only commits by that email are counted.
4. Leave **AI 분석 포함** on for a deeper read of README/key files, or off for a fast metrics-only scan.
5. **Git 스캔 불러오기** → the result fills the form. **It is not saved automatically** — review, then Save.

CLI equivalent:

```bash
devfolio scan . --dry-run      # preview without saving
devfolio scan .                # confirm, then save
devfolio scan . --refresh      # ignore the HEAD-SHA cache
devfolio scan . --author you@work.com
```

### Step 6 — Build a document

**Generate** is a four-step wizard:

1. **Document type** — 이력서 (1–2 pages) · 경력기술서 (per-project detail) · 포트폴리오 (case studies)
2. **Experiences** — tick what to include. **"{type} 추천 선택"** pre-selects everything tagged for that document type.
3. **Tone** — 실무 중심 · 기술 중심 · 문제 해결 중심 · 성과 중심
4. **Create session** — opens with a preview already rendered

You can revisit any step with the stepper at the top.

### Step 7 — Refine in the Editor

- Drag section rows to change order
- Use the **표시** toggle to hide an experience from this document without deleting it
- Switch document type on the fly with the segmented control in the preview header
- **미리보기 새로고침** re-renders on demand (changes are also debounced automatically)

The preview is generated from **saved** experiences and uses the same renderer as the real export, so what you see is what you get.

### Step 8 — Export

**Export** → choose template and format → **문서 내보내기** → **폴더 열기**.

| Document | Formats |
|---|---|
| 이력서 (resume) | `md` `html` `pdf` `docx` `json` `csv` |
| 경력기술서 (career) | `md` `html` `pdf` `docx` `json` `csv` |
| 포트폴리오 (portfolio) | `md` `html` `pdf` `csv` |

Templates: `default`, `compact`, plus `achievement` for resumes. Files are written as `<document>_<template>.<ext>` in the exports directory, or in the folder set under **Settings → Export**.

### Step 9 — Back up

```bash
devfolio data backup            # ZIP of config + data
devfolio data export-json       # all projects as one JSON file
devfolio sync setup --repo your-account/devfolio-backup
devfolio sync run               # opt-in only; nothing leaves your machine before this
```

### Using the CLI only (no browser)

| Task | Command |
|---|---|
| Add a project | `devfolio project add` |
| Add work under a project | `devfolio task add --project "My Project"` |
| List / show / edit / delete | `devfolio project list\|show\|edit\|delete` |
| Generate with AI | `devfolio ai generate task\|project\|resume` |
| Refine text / match a JD | `devfolio ai refine`, `devfolio ai match-jd` |
| Export | `devfolio export resume --format pdf` |
| Providers | `devfolio config ai set\|list\|test\|remove` |
| Settings | `devfolio config show`, `devfolio config set-default` |

Every group has its own help: `devfolio <group> --help`.

### Where your data lives

| OS | Config | Data (projects, exports, logs) |
|---|---|---|
| macOS | `~/Library/Preferences/devfolio/` | `~/Library/Application Support/devfolio/` |
| Linux | `~/.config/devfolio/` | `~/.local/share/devfolio/` |
| Windows | `%APPDATA%/devfolio/devfolio/` | `%LOCALAPPDATA%/devfolio/devfolio/` |

A legacy `~/.devfolio/` directory is still recognized. One project = one YAML file under `projects/`.

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `gui extra가 필요합니다` | web extra not installed | `pip install -e ".[gui]"` |
| `Address already in use` | port 8000 taken | `devfolio serve --port 8010` |
| "원격 Git URL은 바로 스캔할 수 없습니다" | a URL was entered instead of a path | clone it locally, then scan the folder |
| Git scan finds no commits | author email mismatch | pass `--author you@other.com`, or fix Settings → Profile |
| An experience never shows up in a document | no document target ticked | Basics → Document Targets |
| "폴더 열기" does nothing in Docker | no desktop file manager in the container | open the path on the host, or read the file from the mounted volume |
| AI provider test fails | key not stored, or keyring unavailable | set `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` in the environment |
| PDF export errors | WeasyPrint system libraries missing | see the PDF note below, or use `--format html` |
| `DEVFOLIO_LANG` has no effect | locale is read at startup | restart the command |

### Security and cost notes

- The web API has **no authentication**. Keep the default `127.0.0.1` binding. `--host 0.0.0.0` exposes your portfolio data to everyone on the network.
- Nothing is uploaded unless you configure and run `sync run`.
- AI features spend real credits. Each call is charged to your provider key, and the provider's daily limits apply.
- API keys are never written into YAML; they go to the OS keyring or an environment variable.

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

### Model fallback and quality gate

AI analysis does not stop at the first failure. When a model is deprecated, rate-limited, or returns an unusable response:

- deprecated models are blocked permanently, transient failures are blocked for a cooldown window
- the call moves to the next model candidate, then to the next provider
- retries apply only to transient errors and stay inside a 90-second budget for the whole analysis
- a response counts as complete only if it passes a deterministic quality gate (schema, required fields, and tech-stack/number claims traceable to the repository)
- if every provider fails, the Git scaffold is still returned and the analysis is reported as incomplete — never presented as an AI result

| Variable | Default | Effect |
|---|---|---|
| `DEVFOLIO_AI_TIME_BUDGET` | `90` | total seconds for one analysis, including retries and fallbacks |
| `DEVFOLIO_AI_MODEL_RETRIES` | `1` | extra attempts on the same model for transient errors |
| `DEVFOLIO_AI_MAX_MODELS` | `3` | model candidates tried per provider |
| `DEVFOLIO_AI_COOLDOWN` | `300` | how long a transiently failing model stays out |
| `DEVFOLIO_AI_PROVIDER_FALLBACK` | `1` | `0` disables switching to another provider |
| `DEVFOLIO_AI_ALLOW_THIRD_PARTY` | `1` | `0` keeps your data away from the bundled pollinations endpoint |

See [`docs/ai-reliability.md`](docs/ai-reliability.md) for the failure policy table and operations guide.

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

> **참고:** `devfolio scan` 명령은 pip 설치 방식에서 바로 사용할 수 있고, 웹 UI의 Git 분석도 대상 저장소가 `REPOS_DIR` 아래에 있으면 Docker에서 사용할 수 있습니다. Docker에서는 `/Users/...` 또는 `/home/...` 같은 호스트 경로를 그대로 붙여넣으면 컨테이너 경로로 자동 매핑을 시도합니다.
>
> Docker에서 스캔 로그를 보려면:
> ```bash
> docker compose logs -f
> ```

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

## 실행하고 사용하는 방법 (처음부터 끝까지)

설치 확인 → 최초 설정 → 스튜디오 실행 → 경험 추가 → 문서 생성 → 내보내기까지 순서대로 설명합니다. 아래 명령과 화면 이름은 모두 현재 코드 기준입니다.

### 1단계 — 설치 확인

```bash
devfolio --help          # 사용 가능한 명령 목록
devfolio serve --help    # 웹 스튜디오 옵션
```

`devfolio serve` 실행 시 `웹 UI를 실행하려면 gui extra가 필요합니다`라는 메시지가 나오면 CLI만 설치된 상태입니다.

```bash
pip install -e ".[gui]"     # 웹 스튜디오만 추가
pip install -e ".[all]"     # AI · PDF · DOCX 까지 전부
```

| Extra | 켜지는 기능 |
|---|---|
| (기본) | CLI, YAML 저장소, Markdown/HTML 내보내기 |
| `ai` | litellm 기반 AI 초안 생성 |
| `pdf` | PDF 내보내기 (WeasyPrint + Markdown) |
| `docx` | DOCX 내보내기 |
| `gui` | FastAPI + Uvicorn 웹 스튜디오 |

### 2단계 — 최초 설정

```bash
devfolio init            # 다시 설정하려면 --force
```

질문 순서는 다음과 같습니다.

| 질문 | 설명 |
|---|---|
| 이름 | 문서 상단 프로필에 사용됩니다 |
| 이메일 | **필수** — Git 스캔에서 본인 커밋을 고르는 기본 값입니다 |
| GitHub / 블로그 | 선택 사항. 문서 헤더에 들어갑니다 |
| AI 기능 사용? | 기본값 **아니오**. 나중에 웹 설정 화면에서 추가할 수 있습니다 |
| Provider 선택 (1~5) | Anthropic / OpenAI / Gemini / Ollama / 나중에 설정 |
| 모델 선택 | provider별 목록에서 번호로 선택 |
| API 키 | 입력 내용이 가려집니다. OS 키체인에 저장되고, 실패하면 환경변수를 씁니다 |
| Ollama URL | Ollama를 고른 경우만 (기본 `http://localhost:11434`) |
| GitHub 백업? | 선택. `owner/repo`와 브랜치를 묻습니다 |

설정 파일은 OS 설정 디렉터리에 `0600` 권한으로 저장됩니다. `init`을 건너뛰고 웹 화면의 **Settings → Profile**에서 같은 값을 입력해도 됩니다.

### 3단계 — 스튜디오 실행

```bash
devfolio serve
```

주소를 출력하고 1초 뒤 브라우저를 자동으로 엽니다. 종료는 `Ctrl+C`입니다.

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--host` | `127.0.0.1` | 바인딩 주소. `0.0.0.0`은 컨테이너 안에서만 사용하세요(아래 보안 항목 참고) |
| `--port` | `8000` | 포트 번호 |
| `--open` / `--no-open` | 자동 열기 | 브라우저 자동 실행 여부 |
| `--reload` / `--no-reload` | 꺼짐 | 코드 변경 시 자동 재시작(개발용) |

Docker에서는 `--host 0.0.0.0 --no-open --reload` 조합을 사용합니다(이미지 진입점에 설정되어 있습니다). 포트가 이미 사용 중이면 `devfolio serve --port 8010`처럼 바꾸면 됩니다.

### 4단계 — 화면 구조 익히기

스튜디오는 해시 라우팅을 쓰는 단일 페이지이고, 사이드바 순서가 곧 작업 순서입니다.

| 화면 | 역할 |
|---|---|
| **Dashboard** | 유형별 개수, 문서 준비 상태, 현재 상태에서 다음에 할 일 안내 |
| **Experiences** | 경험 목록과 편집기. 카드/표 보기, 유형 필터, 검색 |
| **Generate** | 4단계 마법사: 문서 종류 → 포함할 경험 → 톤 → 세션 생성 |
| **Editor** | 왼쪽 레일에서 순서·표시 여부 조정, 오른쪽에 실시간 미리보기 |
| **Export** | 템플릿·포맷 선택, 내보내기, 출력 폴더 열기 |
| **Settings** | Profile · AI · Export · General · AI Logs 탭 |

**Settings → AI Logs** 에서는 AI 요청 기록(provider, 모델, 지연 시간, 문자 수, 성공 여부)을 앱 안에서 바로 확인할 수 있습니다.

### 5단계 — 경험 추가하기 (세 가지 방법)

여기서 *경험*은 여러 문서에 재사용할 프로젝트·사례 하나를 말합니다. 유형은 **실무 / 개인 / 학습 / 토이** 입니다.

**A. 직접 입력**

1. **Experiences → 새 경험 추가**
2. 편집기는 5개 섹션으로 나뉩니다. 순서대로 채우지 않아도 됩니다.

| 섹션 | 넣는 내용 |
|---|---|
| Import / Intake | 원본 텍스트 또는 Git 저장소 경로 (B·C 방법) |
| Basics | 유형, 상태, 중요도(1~5), 경험명, 소속, 역할, 팀 규모, 기간, **문서 대상** |
| Narrative | 한 줄 소개, 요약, 배경, 핵심 문제, 대상 사용자, 목표, 비범위 |
| Tasks & Tech | 기술 스택과 작업별 문제 → 해결 → 결과 |
| Links & Delivery | 대표 링크(GitHub/demo/docs/video), 추가 링크, 태그, 원본 메모 |

3. **저장**. 입력값은 버튼을 누를 때 폼에서 읽으므로, 저장 전에 섹션을 자유롭게 오가도 됩니다.

> **문서 대상이 중요합니다.** 체크한 문서 종류(이력서 / 경력기술서 / 포트폴리오)에서만 Generate 단계에 나타납니다. 특정 문서에 경험이 보이지 않는다면 이 항목을 먼저 확인하세요.

**B. 자유 텍스트 붙여넣기 (AI Provider 필요)**

1. **Experiences → 새 경험 추가 → Import / Intake**
2. 프로젝트 설명을 텍스트 영역에 붙여넣습니다
3. **텍스트로 초안 생성** → 초안 필드가 채워집니다. 저장 전에 반드시 검토·수정하세요

**C. Git 저장소 스캔**

1. **Import / Intake → Git Scan**
2. **로컬** 저장소 경로를 입력합니다(원격 URL은 거부됩니다 — 먼저 clone 하세요). **찾아보기**로 폴더를 선택할 수 있습니다
3. 작성자 이메일은 설정의 `user.email`이 기본값입니다. 그 이메일의 커밋만 집계됩니다
4. **AI 분석 포함**을 켜면 README·핵심 파일까지 읽어 분석하고, 끄면 지표만 빠르게 계산합니다
5. **Git 스캔 불러오기** → 결과가 폼에 채워집니다. **자동 저장되지 않으므로** 검토 후 저장하세요

CLI로 같은 작업을 할 수 있습니다.

```bash
devfolio scan . --dry-run      # 저장 없이 미리보기
devfolio scan .                # 확인 후 저장
devfolio scan . --refresh      # HEAD SHA 캐시 무시
devfolio scan . --author you@work.com
```

### 6단계 — 문서 만들기

**Generate**는 4단계입니다.

1. **문서 종류** — 이력서(1~2장) · 경력기술서(프로젝트별 상세) · 포트폴리오(케이스 스터디)
2. **경험 선택** — 포함할 경험을 체크합니다. **"{종류} 추천 선택"** 은 해당 문서 대상으로 표시된 경험을 한 번에 선택합니다
3. **톤** — 실무 중심 · 기술 중심 · 문제 해결 중심 · 성과 중심
4. **세션 생성** — 미리보기가 이미 렌더링된 상태로 넘어갑니다

상단 스테퍼로 이전 단계를 다시 조정할 수 있습니다.

### 7단계 — 편집기에서 다듬기

- 섹션을 드래그해 순서를 바꿉니다
- **표시** 토글로 이 문서에서만 경험을 숨깁니다(삭제 아님)
- 미리보기 헤더의 세그먼트로 문서 종류를 즉시 바꿉니다
- **미리보기 새로고침**으로 다시 렌더링합니다(변경 시 자동 갱신도 됩니다)

미리보기는 **저장된** 경험으로 만들어지고 실제 내보내기와 같은 렌더러를 쓰므로, 보이는 결과가 곧 산출물입니다.

### 8단계 — 내보내기

**Export** → 템플릿·포맷 선택 → **문서 내보내기** → **폴더 열기**.

| 문서 | 지원 포맷 |
|---|---|
| 이력서 (resume) | `md` `html` `pdf` `docx` `json` `csv` |
| 경력기술서 (career) | `md` `html` `pdf` `docx` `json` `csv` |
| 포트폴리오 (portfolio) | `md` `html` `pdf` `csv` |

템플릿은 `default`, `compact`이고 이력서는 `achievement`도 지원합니다. 파일은 `<문서>_<템플릿>.<확장자>` 이름으로 exports 디렉터리(**Settings → Export**에서 변경 가능)에 저장됩니다.

### 9단계 — 백업

```bash
devfolio data backup            # 설정 + 데이터 ZIP
devfolio data export-json       # 전체 프로젝트를 JSON 하나로
devfolio sync setup --repo your-account/devfolio-backup
devfolio sync run               # 선택 기능. 실행 전에는 아무것도 전송되지 않습니다
```

### 브라우저 없이 CLI만 쓰기

| 작업 | 명령 |
|---|---|
| 프로젝트 추가 | `devfolio project add` |
| 프로젝트에 작업 추가 | `devfolio task add --project "My Project"` |
| 조회·수정·삭제 | `devfolio project list\|show\|edit\|delete` |
| AI 생성 | `devfolio ai generate task\|project\|resume` |
| 문구 개선 / JD 매칭 | `devfolio ai refine`, `devfolio ai match-jd` |
| 내보내기 | `devfolio export resume --format pdf` |
| Provider 관리 | `devfolio config ai set\|list\|test\|remove` |
| 설정 확인 | `devfolio config show`, `devfolio config set-default` |

각 그룹의 세부 옵션은 `devfolio <그룹> --help`로 확인할 수 있습니다.

### 데이터가 저장되는 위치

| OS | 설정 | 데이터(프로젝트·산출물·로그) |
|---|---|---|
| macOS | `~/Library/Preferences/devfolio/` | `~/Library/Application Support/devfolio/` |
| Linux | `~/.config/devfolio/` | `~/.local/share/devfolio/` |
| Windows | `%APPDATA%/devfolio/devfolio/` | `%LOCALAPPDATA%/devfolio/devfolio/` |

레거시 `~/.devfolio/` 경로도 인식합니다. 프로젝트 1건이 `projects/` 아래 YAML 파일 1개로 저장됩니다.

### 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `gui extra가 필요합니다` | 웹 extra 미설치 | `pip install -e ".[gui]"` |
| `Address already in use` | 8000 포트 사용 중 | `devfolio serve --port 8010` |
| "원격 Git URL은 바로 스캔할 수 없습니다" | 경로 대신 URL 입력 | 로컬에 clone 후 그 폴더를 스캔 |
| Git 스캔에서 커밋이 0건 | 작성자 이메일 불일치 | `--author you@other.com` 지정 또는 Settings → Profile 수정 |
| 경험이 특정 문서에 안 나옴 | 문서 대상 미선택 | Basics → Document Targets |
| Docker에서 "폴더 열기"가 동작 안 함 | 컨테이너에 파일 탐색기 없음 | 호스트에서 경로를 열거나 마운트된 볼륨에서 파일 확인 |
| AI Provider 테스트 실패 | 키 미저장 또는 키체인 없음 | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` 환경변수 설정 |
| PDF 내보내기 오류 | WeasyPrint 시스템 라이브러리 누락 | 아래 PDF 안내를 보거나 `--format html` 사용 |
| `DEVFOLIO_LANG`이 반영되지 않음 | 로케일은 시작 시에만 읽음 | 명령을 다시 실행 |

### 보안·비용 관련 주의

- 웹 API에는 **인증이 없습니다.** 기본값인 `127.0.0.1` 바인딩을 유지하세요. `--host 0.0.0.0`은 같은 네트워크의 누구나 경력 데이터를 읽고 쓸 수 있게 노출합니다.
- `sync`를 설정하고 `sync run`을 실행하기 전까지는 아무것도 외부로 전송되지 않습니다.
- AI 기능은 실제 크레딧을 사용합니다. 호출마다 등록한 provider 키로 과금되며, provider의 일일 한도가 적용됩니다.
- API 키는 YAML에 기록되지 않습니다. OS 키체인 또는 환경변수로만 관리됩니다.

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

### 모델 자동 전환과 품질 검증

AI 분석은 첫 실패에서 멈추지 않습니다. 모델이 폐기되었거나, 속도 제한에 걸렸거나, 쓸 수 없는 응답을 돌려주면:

- 폐기된 모델은 **영구 차단**, 일시 장애는 Cooldown 동안만 차단합니다
- 다음 모델 후보로, 그다음에는 다음 Provider로 넘어갑니다
- 재시도는 일시 오류에만 적용하고, 분석 전체 90초 예산을 넘지 않습니다
- 응답은 결정론적 품질 검증(스키마·필수 필드, 기술 스택과 수치의 저장소 근거)을 통과해야만 완료로 인정됩니다
- 모든 Provider가 실패하면 Git 스캔 결과는 그대로 돌려주고, AI 분석은 **미완료로 표시**합니다 (AI 결과처럼 꾸미지 않습니다)

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `DEVFOLIO_AI_TIME_BUDGET` | `90` | 분석 1회 전체 시간 예산(초), 재시도·전환 포함 |
| `DEVFOLIO_AI_MODEL_RETRIES` | `1` | 일시 오류일 때 같은 모델 추가 시도 횟수 |
| `DEVFOLIO_AI_MAX_MODELS` | `3` | Provider당 시도할 모델 후보 수 |
| `DEVFOLIO_AI_COOLDOWN` | `300` | 일시 장애 모델을 제외하는 시간(초) |
| `DEVFOLIO_AI_PROVIDER_FALLBACK` | `1` | `0`이면 다른 Provider로 전환하지 않음 |
| `DEVFOLIO_AI_ALLOW_THIRD_PARTY` | `1` | `0`이면 내장 pollinations로 데이터를 보내지 않음 |

실패 분류표와 운영 절차는 [`docs/ai-reliability.md`](docs/ai-reliability.md)에 정리되어 있습니다.

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
