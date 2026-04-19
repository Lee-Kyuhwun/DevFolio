"""Jinja2 기반 문서 템플릿 렌더링."""

import html as html_mod
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from devfolio.core.storage import TEMPLATES_DIR
from devfolio.exceptions import DevfolioTemplateError
from devfolio.models.config import Config
from devfolio.models.project import Project

# 패키지 내장 템플릿 디렉터리
_BUILTIN_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# 내장 폴백 맵 — doc_type별로 분리
_BUILTIN_FALLBACK: dict[str, str]  # 선언만; 아래 문자열 상수 정의 후 할당

_STACK_LAYER_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "인터페이스 레이어",
        ("html", "css", "javascript", "typescript", "react", "vue", "next.js", "nextjs", "svelte"),
        "사용자 입력, 결과 미리보기, 화면 상호작용을 담당합니다.",
    ),
    (
        "애플리케이션 레이어",
        ("python", "java", "go", "fastapi", "django", "flask", "spring", "express", "node", "typer", "rich"),
        "핵심 비즈니스 로직, 명령 실행, 요청 처리 흐름을 담당합니다.",
    ),
    (
        "데이터 및 설정 레이어",
        ("pydantic", "ruamel.yaml", "yaml", "sqlite", "postgres", "mysql", "redis", "keyring"),
        "데이터 구조화, 검증, 로컬 저장, 비밀정보 관리를 담당합니다.",
    ),
    (
        "문서 및 렌더링 레이어",
        ("jinja2", "markdown", "weasyprint", "python-docx", "docx"),
        "포트폴리오/이력서 템플릿 구성과 문서 렌더링을 담당합니다.",
    ),
    (
        "외부 연동 및 배포 레이어",
        ("litellm", "openai", "anthropic", "gemini", "github", "docker", "uvicorn", "nginx"),
        "외부 AI, 동기화, 실행 환경과의 연동을 담당합니다.",
    ),
)


def _project_text_blob(project: Project) -> str:
    task_bits = []
    for task in project.tasks:
        task_bits.extend([task.name, task.problem, task.solution, task.result])
        task_bits.extend(task.tech_used)
        task_bits.extend(task.keywords)
    values = [
        project.name,
        project.summary,
        project.role,
        project.organization,
        *project.tech_stack,
        *project.tags,
        *task_bits,
    ]
    return " ".join(str(value or "") for value in values).lower()


def _stack_layers(project: Project) -> list[tuple[str, list[str], str]]:
    tech_stack = [item for item in project.tech_stack if item]
    normalized_map = {item.lower(): item for item in tech_stack}
    layers: list[tuple[str, list[str], str]] = []
    used: set[str] = set()

    for title, keywords, description in _STACK_LAYER_RULES:
        matched = [
            original
            for lowered, original in normalized_map.items()
            if lowered not in used and any(keyword in lowered for keyword in keywords)
        ]
        if matched:
            layers.append((title, matched, description))
            used.update(item.lower() for item in matched)

    remaining = [item for item in tech_stack if item.lower() not in used]
    if remaining:
        layers.append(("기타 구성 요소", remaining, "프로젝트에 필요한 보조 도구와 라이브러리로 사용되었습니다."))

    if not layers and tech_stack:
        layers.append(("기술 스택", tech_stack, "프로젝트 전반에 사용된 핵심 기술입니다."))

    return layers


def describe_tech_stack(project: Project) -> str:
    layers = _stack_layers(project)
    if not layers:
        return "- 별도 기술 스택 정보가 없습니다."
    return "\n".join(
        f"- **{title}**: {', '.join(items)} — {description}"
        for title, items, description in layers
    )


def build_architecture_diagram(project: Project) -> str:
    text_blob = _project_text_blob(project)
    tech_stack = {item.lower(): item for item in project.tech_stack if item}

    has_ui = any(keyword in tech_stack for keyword in ("html", "css", "javascript", "typescript", "react", "vue", "next.js", "nextjs", "svelte"))
    has_cli = any(keyword in tech_stack for keyword in ("typer", "rich", "click")) or "cli" in text_blob
    has_storage = any(keyword in text_blob for keyword in ("yaml", "sqlite", "postgres", "mysql", "redis", "keyring", "storage", "저장"))
    has_export = any(keyword in text_blob for keyword in ("jinja2", "markdown", "docx", "pdf", "export", "template", "문서", "내보내기"))
    has_ai = any(keyword in text_blob for keyword in ("litellm", "openai", "anthropic", "gemini", "ai", "llm"))
    has_sync = any(keyword in text_blob for keyword in ("github", "sync", "backup", "동기화", "백업"))

    lines = ["flowchart LR", '    user["사용자"]']
    entry_nodes: list[str] = []

    if has_ui:
        ui_stack = [tech_stack[key] for key in ("html", "css", "javascript", "typescript", "react", "vue", "next.js", "nextjs", "svelte") if key in tech_stack]
        label = "Web Studio"
        if ui_stack:
            label += "\\n" + " · ".join(ui_stack[:3])
        lines.append(f'    web["{label}"]')
        lines.append("    user --> web")
        entry_nodes.append("web")

    if has_cli:
        cli_stack = [tech_stack[key] for key in ("typer", "rich", "click") if key in tech_stack]
        label = "CLI"
        if cli_stack:
            label += "\\n" + " · ".join(cli_stack[:2])
        lines.append(f'    cli["{label}"]')
        lines.append("    user --> cli")
        entry_nodes.append("cli")

    core_stack = [item for item in project.tech_stack if item.lower() in {"python", "java", "go", "fastapi", "django", "flask", "spring", "express", "node", "pydantic"}]
    core_label = "Core Application"
    if core_stack:
        core_label += "\\n" + " · ".join(core_stack[:3])
    lines.append(f'    core["{core_label}"]')

    if entry_nodes:
        for entry in entry_nodes:
            lines.append(f"    {entry} --> core")
    else:
        lines.append("    user --> core")

    if has_storage:
        storage_stack = [item for item in project.tech_stack if item.lower() in {"ruamel.yaml", "yaml", "sqlite", "postgres", "mysql", "redis", "keyring", "pydantic"}]
        label = "Local Storage / Config"
        if storage_stack:
            label += "\\n" + " · ".join(storage_stack[:3])
        lines.append(f'    storage["{label}"]')
        lines.append("    core --> storage")

    if has_export:
        export_stack = [item for item in project.tech_stack if item.lower() in {"jinja2", "markdown", "weasyprint", "python-docx"}]
        label = "Template / Export"
        if export_stack:
            label += "\\n" + " · ".join(export_stack[:3])
        lines.append(f'    export["{label}"]')
        lines.append("    core --> export")

    if has_ai:
        ai_stack = [item for item in project.tech_stack if item.lower() in {"litellm", "openai", "anthropic", "gemini"}]
        label = "AI Providers"
        if ai_stack:
            label += "\\n" + " · ".join(ai_stack[:3])
        lines.append(f'    ai["{label}"]')
        lines.append("    core --> ai")

    if has_sync:
        lines.append('    sync["GitHub / External Sync"]')
        lines.append("    core --> sync")

    return "\n".join(lines)


class TemplateEngine:
    def __init__(self):
        search_paths: list[str] = []
        if TEMPLATES_DIR.exists():
            search_paths.append(str(TEMPLATES_DIR))
        if _BUILTIN_TEMPLATES_DIR.exists():
            search_paths.append(str(_BUILTIN_TEMPLATES_DIR))

        if search_paths:
            self._env: Optional[Environment] = Environment(
                loader=FileSystemLoader(search_paths),
                autoescape=select_autoescape(
                    enabled_extensions=("html", "htm"),
                    default_for_string=False,
                    default=False,
                ),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        else:
            self._env = None

    def _render_str(self, template_str: str, **context) -> str:
        env = Environment(
            autoescape=select_autoescape(
                enabled_extensions=("html", "htm"),
                default_for_string=False,
                default=False,
            ),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        return env.from_string(template_str).render(**context)

    def _load_template(self, filename: str):
        """템플릿 로드. TemplateNotFound 외 예외는 그대로 전파."""
        if self._env is None:
            raise TemplateNotFound(filename)
        return self._env.get_template(filename)

    def render(
        self,
        projects: list[Project],
        config: Config,
        template_name: str = "default",
        doc_type: str = "resume",
    ) -> str:
        """다수 프로젝트를 포함하는 문서 렌더링.

        탐색 순서:
        1. {doc_type}_{template_name}.md.j2
        2. {doc_type}_default.md.j2  (지정 템플릿 없을 때만)
        3. 내장 문자열 폴백 (doc_type별로 분리)
        """
        context = {
            "projects": projects,
            "user": config.user,
            "config": config,
            "describe_tech_stack": describe_tech_stack,
            "build_architecture_diagram": build_architecture_diagram,
        }

        # 1단계: 정확한 이름 매칭
        primary = f"{doc_type}_{template_name}.md.j2"
        try:
            return self._load_template(primary).render(**context)
        except TemplateNotFound:
            pass  # 없으면 기본 템플릿으로
        except Exception as e:
            # 파일은 있지만 렌더링 오류 → 명시적으로 알림
            raise DevfolioTemplateError(primary) from e

        # 2단계: {doc_type}_default.md.j2 폴백 (지정 템플릿이 default가 아닌 경우만)
        if template_name != "default":
            default_file = f"{doc_type}_default.md.j2"
            try:
                return self._load_template(default_file).render(**context)
            except TemplateNotFound:
                pass
            except Exception as e:
                raise DevfolioTemplateError(default_file) from e

        # 3단계: 내장 문자열 (doc_type별 분리)
        fallback_str = _BUILTIN_FALLBACK.get(doc_type, _BUILTIN_RESUME_DEFAULT)
        return self._render_str(fallback_str, **context)

    def render_project(self, project: Project, config: Config) -> str:
        """단일 프로젝트 한 장 요약 렌더링."""
        context = {
            "project": project,
            "user": config.user,
            "describe_tech_stack": describe_tech_stack,
            "build_architecture_diagram": build_architecture_diagram,
        }

        try:
            return self._load_template("project_single.md.j2").render(**context)
        except TemplateNotFound:
            pass
        except Exception as e:
            raise DevfolioTemplateError("project_single.md.j2") from e

        return self._render_str(_BUILTIN_PROJECT_SINGLE, **context)


# ---------------------------------------------------------------------------
# 내장 템플릿 문자열 (파일 없을 때 폴백)
# ---------------------------------------------------------------------------

_BUILTIN_RESUME_DEFAULT = """\
# {{ user.name }} 경력기술서
{% if user.email %}
- 이메일: {{ user.email }}
{%- endif %}
{% if user.github %}
- GitHub: {{ user.github }}
{%- endif %}
{% if user.blog %}
- 블로그: {{ user.blog }}
{%- endif %}

---

## 프로젝트 이력

{% for project in projects %}
### {{ project.name }}

| 항목 | 내용 |
|------|------|
| 기간 | {{ project.period.display() }} |
| 유형 | {{ project.type_display() }} |
| 소속 | {{ project.organization }} |
| 역할 | {{ project.role }} |
| 팀 규모 | {{ project.team_size }}명 |
| 기술 스택 | {{ project.tech_stack | join(", ") }} |

**프로젝트 개요**

{{ project.summary }}

{% if project.tasks %}
**주요 작업 내역**

{% for task in project.tasks %}
#### {{ task.name }}
{% if task.period.start %}*기간: {{ task.period.display() }}*{% endif %}

{% if task.ai_generated_text %}
{{ task.ai_generated_text }}
{% else %}
- **문제 상황**: {{ task.problem }}
- **해결 방법**: {{ task.solution }}
- **성과**: {{ task.result }}
- **사용 기술**: {{ task.tech_used | join(", ") }}
{% endif %}
{% endfor %}
{% endif %}

---
{% endfor %}
"""

_BUILTIN_PROJECT_SINGLE = """\
# {{ project.name }}

| 항목 | 내용 |
|------|------|
| 기간 | {{ project.period.display() }} |
| 소속 | {{ project.organization }} |
| 역할 | {{ project.role }} |
| 팀 규모 | {{ project.team_size }}명 |
| 기술 스택 | {{ project.tech_stack | join(", ") }} |
| 상태 | {{ project.status_display() }} |

## 프로젝트 개요

{{ project.summary }}

## 기술 스택 구성

{{ describe_tech_stack(project) }}

## 아키텍처

```mermaid
{{ build_architecture_diagram(project) }}
```

## 주요 작업 내역

{% for task in project.tasks %}
### {{ task.name }}
{% if task.period.start %}*기간: {{ task.period.display() }}*{% endif %}

{% if task.ai_generated_text %}
{{ task.ai_generated_text }}
{% else %}
**문제 상황**

{{ task.problem }}

**해결 방법**

{{ task.solution }}

**성과**

{{ task.result }}

**사용 기술**: {{ task.tech_used | join(", ") }}
{% endif %}
{% endfor %}
"""

_BUILTIN_PORTFOLIO_DEFAULT = """\
# {{ user.name }} 포트폴리오
{% if user.email %}
- 이메일: {{ user.email }}
{%- endif %}
{% if user.github %}
- GitHub: {{ user.github }}
{%- endif %}

---

{% for project in projects %}
## {{ loop.index }}. {{ project.name }}

> {{ project.summary }}

- **기간**: {{ project.period.display() }}
- **역할**: {{ project.role }}
- **기술 스택**: {{ project.tech_stack | join(", ") }}

### 기술 스택 구성

{{ describe_tech_stack(project) }}

### 아키텍처

```mermaid
{{ build_architecture_diagram(project) }}
```

{% for task in project.tasks %}
**{{ task.name }}**: {{ task.result }}
{% endfor %}

---
{% endfor %}
"""

# doc_type → 내장 폴백 문자열 매핑
# 반드시 상수 선언 후에 위치해야 함
_BUILTIN_FALLBACK: dict[str, str] = {
    "resume": _BUILTIN_RESUME_DEFAULT,
    "portfolio": _BUILTIN_PORTFOLIO_DEFAULT,
}
