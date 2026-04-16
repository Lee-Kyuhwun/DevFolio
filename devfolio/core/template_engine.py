"""Jinja2 기반 문서 템플릿 렌더링."""

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
                autoescape=select_autoescape([]),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        else:
            self._env = None

    def _render_str(self, template_str: str, **context) -> str:
        env = Environment(
            autoescape=select_autoescape([]),
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
        context = {"project": project, "user": config.user}

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
