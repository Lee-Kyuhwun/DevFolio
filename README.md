# DevFolio

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

**Language:** [English](#english) | [한국어](#한국어)

## English

DevFolio is a CLI for building developer portfolios and resumes from structured project and task data, with optional AI-assisted writing and GitHub backup sync.

## What Is DevFolio?

DevFolio helps you manage your career content as data first.

Instead of rewriting the same resume and portfolio over and over, you store your projects, tasks, summaries, and export settings in structured YAML-backed records. From there, you can:

- initialize a local workspace with guided prompts
- add and update projects and detailed task history
- import existing YAML or JSON project files
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

### Guided setup

- `devfolio init` walks through user profile, optional AI provider setup, and optional GitHub sync setup.

### Project and task management

- `devfolio project add|list|show|edit|delete`
- `devfolio task add|list|show|edit|delete`
- project and task periods support in-progress records
- duplicate project name collisions are prevented safely

### Import, backup, and restore

- import project data from YAML or JSON with `devfolio data import`
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
- supported output formats depend on the command and installed extras

### GitHub backup sync

- `devfolio sync setup`
- `devfolio sync status`
- `devfolio sync run`

Sync stores raw DevFolio data plus generated Markdown and HTML artifacts in a dedicated GitHub repository.

## Installation

DevFolio is currently intended to run from source.

### Requirements

- Python 3.11 or newer
- `git` for GitHub sync workflows
- optional system dependencies for PDF export depending on your platform

### Clone the repository

```bash
git clone https://github.com/Lee-Kyuhwun/DevFolio.git
cd DevFolio
```

### Base install

```bash
pip install -e .
```

### Optional extras

AI features:

```bash
pip install -e ".[ai]"
```

PDF export:

```bash
pip install -e ".[pdf]"
```

All optional runtime features:

```bash
pip install -e ".[all]"
```

Development setup:

```bash
pip install -e ".[dev]"
```

## Quick Start

### 1. Initialize DevFolio

```bash
devfolio init
```

This creates your local config and walks through profile, AI, and optional GitHub backup setup.

### 2. Add a project

```bash
devfolio project add
```

### 3. Add a task to that project

```bash
devfolio task add --project "My Project"
```

### 4. Export a resume

```bash
devfolio export resume
```

### 5. Optionally configure GitHub backup sync

```bash
devfolio sync setup --repo your-account/devfolio-backup
devfolio sync run
```

## Import Existing Data

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
- `devfolio project add|list|show|edit|delete`
- `devfolio task add|list|show|edit|delete`

### AI workflows

- `devfolio ai generate task`
- `devfolio ai generate project`
- `devfolio ai generate resume`
- `devfolio ai refine`
- `devfolio ai match-jd`

### Export workflows

- `devfolio export resume`
- `devfolio export portfolio`
- `devfolio export project`

### Data workflows

- `devfolio data backup`
- `devfolio data restore`
- `devfolio data import`
- `devfolio data export-json`

### GitHub backup workflows

- `devfolio sync setup`
- `devfolio sync status`
- `devfolio sync run`

### Configuration workflows

- `devfolio config show`
- `devfolio config set-default`
- `devfolio config ai set|list|test|remove`

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

### Architecture snapshot

- `devfolio/main.py`: Typer CLI entrypoint and global error handling
- `devfolio/commands/`: user-facing command groups
- `devfolio/models/`: Pydantic v2 models for config, projects, tasks, and periods
- `devfolio/core/`: storage, export, template, AI, sync, and project management logic
- `devfolio/templates/`: built-in Jinja templates

### Contributor expectations

- use Pydantic v2 helpers such as `model_validate()` and `model_dump()`
- use `ruamel.yaml` for YAML handling
- keep heavyweight dependencies lazily imported where appropriate
- raise user-facing failures through `DevfolioError` subclasses

For contribution workflow details, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Limitations / Current Status

- Python 3.11+ is required
- the repository does not currently include CI workflows or CI badges
- the project is a source-first CLI tool, not a hosted web service
- PDF export may require additional platform-specific system libraries depending on your environment

## Contributing

Contributions are welcome. For setup, coding expectations, and pull request guidance, see [CONTRIBUTING.md](CONTRIBUTING.md).

For large feature changes, open an issue or discussion first so scope and direction are aligned before implementation.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

---

## 한국어

DevFolio는 구조화된 프로젝트/작업 데이터를 기반으로 개발자 포트폴리오와 경력기술서를 만드는 CLI 도구입니다. 필요하면 AI 문구 생성과 GitHub 백업 동기화도 함께 사용할 수 있습니다.

## DevFolio란?

DevFolio는 경력 문서를 "문서"보다 "데이터"로 먼저 관리할 수 있게 설계되어 있습니다.

이력서나 포트폴리오를 매번 새로 쓰는 대신, 프로젝트, 작업 내역, 요약, 출력 설정을 YAML 기반 구조화 데이터로 저장합니다. 그 다음 이 데이터를 바탕으로 다음 작업을 할 수 있습니다.

- 대화형 초기 설정으로 로컬 작업 공간 구성
- 프로젝트와 세부 작업 이력 추가 및 수정
- YAML 또는 JSON 프로젝트 데이터 가져오기
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

### 대화형 초기 설정

- `devfolio init` 으로 사용자 정보, 선택적 AI 설정, 선택적 GitHub sync 설정을 한 번에 진행합니다.

### 프로젝트 / 작업 내역 관리

- `devfolio project add|list|show|edit|delete`
- `devfolio task add|list|show|edit|delete`
- 진행 중인 프로젝트와 작업 기간 표현 지원
- 중복 프로젝트 이름 충돌을 안전하게 방지

### 가져오기 / 백업 / 복원

- `devfolio data import` 로 YAML 또는 JSON 프로젝트 데이터 가져오기
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
- 설치한 extra에 따라 여러 출력 포맷 사용 가능

### GitHub 백업 동기화

- `devfolio sync setup`
- `devfolio sync status`
- `devfolio sync run`

동기화는 DevFolio 원본 데이터와 생성된 Markdown / HTML 산출물을 전용 GitHub 저장소에 보관합니다.

## 설치

현재 DevFolio는 소스 기반 실행을 기준으로 합니다.

### 요구 사항

- Python 3.11 이상
- GitHub sync 사용 시 `git`
- 환경에 따라 PDF export용 추가 시스템 라이브러리

### 저장소 클론

```bash
git clone https://github.com/Lee-Kyuhwun/DevFolio.git
cd DevFolio
```

### 기본 설치

```bash
pip install -e .
```

### 선택적 extras

AI 기능:

```bash
pip install -e ".[ai]"
```

PDF export:

```bash
pip install -e ".[pdf]"
```

모든 선택 기능:

```bash
pip install -e ".[all]"
```

개발 환경:

```bash
pip install -e ".[dev]"
```

## 빠른 시작

### 1. DevFolio 초기화

```bash
devfolio init
```

이 명령은 로컬 설정 파일을 만들고 사용자 정보, AI, 선택적 GitHub 백업 설정까지 안내합니다.

### 2. 프로젝트 추가

```bash
devfolio project add
```

### 3. 프로젝트에 작업 내역 추가

```bash
devfolio task add --project "My Project"
```

### 4. 이력서 내보내기

```bash
devfolio export resume
```

### 5. 필요하면 GitHub 백업 sync 설정

```bash
devfolio sync setup --repo your-account/devfolio-backup
devfolio sync run
```

## 기존 데이터 가져오기

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
- `devfolio project add|list|show|edit|delete`
- `devfolio task add|list|show|edit|delete`

### AI 워크플로우

- `devfolio ai generate task`
- `devfolio ai generate project`
- `devfolio ai generate resume`
- `devfolio ai refine`
- `devfolio ai match-jd`

### 내보내기 워크플로우

- `devfolio export resume`
- `devfolio export portfolio`
- `devfolio export project`

### 데이터 워크플로우

- `devfolio data backup`
- `devfolio data restore`
- `devfolio data import`
- `devfolio data export-json`

### GitHub 백업 워크플로우

- `devfolio sync setup`
- `devfolio sync status`
- `devfolio sync run`

### 설정 워크플로우

- `devfolio config show`
- `devfolio config set-default`
- `devfolio config ai set|list|test|remove`

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

### 아키텍처 개요

- `devfolio/main.py`: Typer CLI 진입점과 전역 오류 처리
- `devfolio/commands/`: 사용자-facing 명령 그룹
- `devfolio/models/`: config, project, task, period용 Pydantic v2 모델
- `devfolio/core/`: storage, export, template, AI, sync, project management 로직
- `devfolio/templates/`: 내장 Jinja 템플릿

### 기여 시 기대 사항

- `model_validate()`, `model_dump()` 같은 Pydantic v2 helper 사용
- YAML 처리는 `ruamel.yaml` 사용
- 무거운 의존성은 필요할 때 lazy import 유지
- 사용자에게 보이는 오류는 `DevfolioError` 하위 클래스로 처리

기여 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 현재 상태 / 제한 사항

- Python 3.11+ 필요
- 현재 저장소에는 CI workflow / CI badge가 포함되어 있지 않음
- 이 프로젝트는 호스팅형 서비스가 아니라 소스 중심 CLI 도구임
- PDF export는 환경에 따라 추가 시스템 라이브러리가 필요할 수 있음

## 기여하기

기여는 언제든 환영합니다. 개발 환경 설정, 코딩 규칙, PR 가이드는 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

규모가 큰 기능 변경은 구현 전에 issue 또는 discussion으로 먼저 방향을 맞추는 것을 권장합니다.

## 라이선스

이 프로젝트는 MIT License를 따릅니다. 자세한 내용은 [LICENSE](LICENSE)를 참고하세요.
