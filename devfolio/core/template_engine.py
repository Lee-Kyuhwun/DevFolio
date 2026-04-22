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


def _unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        cleaned = " ".join(str(value or "").split())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        results.append(cleaned)
    return results


def _task_texts(project: Project, attribute: str) -> list[str]:
    return _unique_texts([str(getattr(task, attribute, "") or "") for task in project.tasks])


def _project_text_blob(project: Project) -> str:
    task_bits = []
    for task in project.tasks:
        task_bits.extend([task.name, task.problem, task.solution, task.result])
        task_bits.extend(task.tech_used)
        task_bits.extend(task.keywords)
    flow_bits = []
    for step in project.user_flow:
        flow_bits.extend([step.title, step.description])
    feature_bits = []
    for feature in project.features:
        feature_bits.extend([feature.name, feature.user_value, feature.implementation])
    case_bits = []
    for case in project.problem_solving_cases:
        case_bits.extend(
            [case.title, case.situation, case.cause, case.action, case.decision_reason, case.result, case.metric]
        )
        case_bits.extend(case.tech_used)
    values = [
        project.name,
        project.one_line_summary,
        project.summary,
        project.role,
        project.organization,
        project.overview.background,
        project.overview.problem,
        *project.overview.target_users,
        *project.overview.goals,
        *project.overview.non_goals,
        *project.tech_stack,
        *project.tags,
        *flow_bits,
        project.architecture.summary,
        *feature_bits,
        *case_bits,
        *project.performance_security_operations.performance,
        *project.performance_security_operations.security,
        *project.performance_security_operations.operations,
        *project.results.qualitative,
        *project.retrospective.what_went_well,
        *project.retrospective.what_was_hard,
        *project.retrospective.what_i_learned,
        *project.retrospective.next_steps,
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
    detail_sections = [
        ("프론트엔드", project.tech_stack_detail.frontend),
        ("백엔드", project.tech_stack_detail.backend),
        ("데이터베이스", project.tech_stack_detail.database),
        ("인프라", project.tech_stack_detail.infra),
        ("도구", project.tech_stack_detail.tools),
    ]
    detail_lines = [
        f"- **{title}**: {item.name} — {item.reason}"
        for title, items in detail_sections
        for item in items
        if item.name or item.reason
    ]
    if detail_lines:
        return "\n".join(detail_lines)

    layers = _stack_layers(project)
    if not layers:
        return "- 별도 기술 스택 정보가 없습니다."
    return "\n".join(
        f"- **{title}**: {', '.join(items)} — {description}"
        for title, items, description in layers
    )


def describe_project_purpose(project: Project) -> str:
    if project.overview.background or project.overview.problem or project.overview.goals:
        parts: list[str] = []
        if project.overview.background:
            parts.append(project.overview.background.strip())
        if project.overview.problem:
            parts.append(f"핵심적으로는 {project.overview.problem.strip()} 문제를 해결하는 데 초점을 맞췄습니다.")
        if project.overview.goals:
            parts.append(f"주요 목표는 {', '.join(project.overview.goals[:3])}입니다.")
        return " ".join(parts)

    summary = " ".join((project.summary or "").split())
    problems = _task_texts(project, "problem")
    results = _task_texts(project, "result")

    sentences: list[str] = []
    if summary:
        if summary[-1] not in ".!?。！？":
            summary += "."
        sentences.append(summary)

    if problems:
        sentences.append(
            f"이 프로젝트는 {', '.join(problems[:2])} 같은 문제를 줄이고, "
            "사용자가 하나의 일관된 흐름 안에서 작업을 이어갈 수 있도록 설계했습니다."
        )
    else:
        sentences.append(
            "이 프로젝트는 흩어진 작업 과정을 구조화된 흐름으로 묶고, "
            "같은 원천 데이터를 반복 재사용할 수 있는 기반을 만드는 데 목적이 있습니다."
        )

    if results:
        sentences.append(
            f"이를 통해 {', '.join(results[:2])} 같은 결과로 이어지는 제품 구조를 만들었습니다."
        )

    return " ".join(sentences)


def describe_problem_definition(project: Project) -> str:
    lines: list[str] = []
    if project.overview.background:
        lines.append(f"- **배경**: {project.overview.background}")
    if project.overview.problem:
        lines.append(f"- **핵심 문제**: {project.overview.problem}")
    if project.overview.target_users:
        lines.append(f"- **대상 사용자**: {', '.join(project.overview.target_users)}")
    if project.overview.goals:
        lines.append(f"- **목표**: {', '.join(project.overview.goals)}")
    if project.overview.non_goals:
        lines.append(f"- **비범위**: {', '.join(project.overview.non_goals)}")
    if lines:
        return "\n".join(lines)

    problems = _task_texts(project, "problem")
    if problems:
        return "\n".join(f"- {problem}" for problem in problems[:3])
    return "- 프로젝트 배경과 문제 정의 정보가 아직 구체적으로 정리되지 않았습니다."


def describe_user_flow(project: Project) -> str:
    if project.user_flow:
        return "\n".join(
            f"{step.step}. **{step.title or f'단계 {step.step}'}** — {step.description}"
            for step in sorted(project.user_flow, key=lambda item: item.step)
        )

    text_blob = _project_text_blob(project)

    has_setup = any(keyword in text_blob for keyword in ("init", "setup", "config", "설정", "api key"))
    has_scan = any(keyword in text_blob for keyword in ("scan", "git", "repository", "저장소"))
    has_ai = any(keyword in text_blob for keyword in ("ai", "llm", "draft", "요약", "bullet", "litellm", "openai", "anthropic", "gemini"))
    has_preview = any(keyword in text_blob for keyword in ("preview", "미리보기", "review", "검토"))
    has_export = any(keyword in text_blob for keyword in ("export", "내보내기", "pdf", "html", "docx", "markdown", "csv"))
    has_sync = any(keyword in text_blob for keyword in ("sync", "backup", "github", "동기화", "백업"))

    steps: list[str] = []
    if has_setup:
        steps.append("사용자가 초기 설정을 마치고 작업 환경을 준비합니다.")

    if has_scan:
        steps.append("Git 저장소를 스캔하거나 프로젝트 정보를 입력해 원천 데이터를 수집합니다.")
    else:
        steps.append("프로젝트 데이터와 작업 내역을 구조화해 입력합니다.")

    if has_ai:
        steps.append("AI draft, 요약, task bullet을 생성하고 사람이 검토하며 문구를 다듬습니다.")
    else:
        steps.append("구조화된 데이터를 바탕으로 핵심 내용을 검토하고 정리합니다.")

    if has_preview:
        steps.append("preview로 문서 결과를 확인하고 저장 전 품질을 점검합니다.")

    if has_export:
        steps.append("필요한 형식으로 export해 이력서, 포트폴리오, 프로젝트 문서로 전환합니다.")
    elif not has_preview:
        steps.append("결과를 검토하고 다음 작업 단계로 연결합니다.")

    if has_sync:
        steps.append("필요 시 GitHub sync로 원본 데이터와 산출물을 백업합니다.")

    return "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))


def describe_architecture_details(project: Project) -> str:
    lines: list[str] = []
    if project.architecture.summary:
        lines.append(project.architecture.summary)
    if project.architecture.components:
        lines.append("### 구성 요소")
        lines.extend(
            f"- **{component.name}**: {component.role}"
            for component in project.architecture.components
            if component.name or component.role
        )
    if project.architecture.data_model:
        lines.append("### 데이터 모델")
        lines.extend(
            f"- **{entity.entity}**: {', '.join(entity.fields)}"
            for entity in project.architecture.data_model
            if entity.entity or entity.fields
        )
    if project.architecture.api_examples:
        lines.append("### API 예시")
        lines.extend(
            f"- **{api.method} {api.path}**: {api.purpose}"
            for api in project.architecture.api_examples
            if api.path or api.purpose
        )
    return "\n".join(lines) if lines else "- 아키텍처 세부 설명은 다이어그램과 함께 보완할 수 있습니다."


def describe_features(project: Project) -> str:
    if project.features:
        return "\n".join(
            f"- **{feature.name}**: {feature.user_value} 구현은 {feature.implementation}"
            for feature in project.features
            if feature.name or feature.user_value or feature.implementation
        )

    if project.tasks:
        return "\n".join(
            f"- **{task.name}**: {task.result or task.solution or task.problem}"
            for task in project.tasks[:4]
        )
    return "- 핵심 기능 정보가 아직 정리되지 않았습니다."


def describe_problem_solving_cases(project: Project) -> str:
    if project.problem_solving_cases:
        blocks = []
        for case in project.problem_solving_cases:
            title = case.title or "문제 해결 사례"
            lines = [f"### {title}"]
            if case.situation:
                lines.append(f"- **문제 상황**: {case.situation}")
            if case.cause:
                lines.append(f"- **원인**: {case.cause}")
            if case.action:
                lines.append(f"- **해결 방식**: {case.action}")
            if case.decision_reason:
                lines.append(f"- **기술적 판단**: {case.decision_reason}")
            if case.result:
                lines.append(f"- **결과**: {case.result}")
            if case.metric:
                lines.append(f"- **지표**: {case.metric}")
            if case.tech_used:
                lines.append(f"- **사용 기술**: {', '.join(case.tech_used)}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    if project.tasks:
        blocks = []
        for task in project.tasks:
            lines = [f"### {task.name}"]
            if task.ai_generated_text:
                lines.append(task.ai_generated_text)
            if task.problem:
                lines.append(f"- **문제 상황**: {task.problem}")
            if task.solution:
                lines.append(f"- **해결 방식**: {task.solution}")
            if task.result:
                lines.append(f"- **결과**: {task.result}")
            if task.tech_used:
                lines.append(f"- **사용 기술**: {', '.join(task.tech_used)}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    return "- 문제 해결 사례가 아직 정리되지 않았습니다."


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


def summarize_project_outcomes(project: Project) -> str:
    bullets: list[str] = []

    for metric in project.results.quantitative:
        if metric.metric_name or metric.impact:
            bullets.append(
                f"- **{metric.metric_name or '지표'}**: {metric.before or '-'} → {metric.after or '-'}"
                f"{' · ' + metric.impact if metric.impact else ''}"
            )
    bullets.extend(f"- {item}" for item in project.results.qualitative if item)
    if bullets:
        return "\n".join(bullets)

    results = _task_texts(project, "result")
    text_blob = _project_text_blob(project)
    bullets = [f"- {result}" for result in results[:3]]

    if not bullets and any(keyword in text_blob for keyword in ("export", "내보내기", "template", "jinja2")):
        bullets.append("- 구조화된 프로젝트 데이터를 여러 문서 형식으로 재사용할 수 있는 기반을 만들었습니다.")
    if not bullets and any(keyword in text_blob for keyword in ("sync", "backup", "github", "동기화", "백업")):
        bullets.append("- 로컬 작업 결과와 백업 흐름을 분리해 운영 안정성과 복원 가능성을 높였습니다.")
    if not bullets and any(keyword in text_blob for keyword in ("ai", "llm", "draft", "litellm")):
        bullets.append("- 구조화된 데이터를 AI 생성 흐름과 연결해 문서 작성 생산성을 높일 수 있는 기반을 마련했습니다.")
    if not bullets:
        bullets.append("- 핵심 기능을 하나의 일관된 흐름으로 정리해 이후 확장과 유지보수에 유리한 구조를 만들었습니다.")

    return "\n".join(bullets)


def describe_operational_considerations(project: Project) -> str:
    parts: list[str] = []
    if project.performance_security_operations.performance:
        parts.append(
            "- **성능**: " + "; ".join(project.performance_security_operations.performance)
        )
    if project.performance_security_operations.security:
        parts.append(
            "- **보안**: " + "; ".join(project.performance_security_operations.security)
        )
    if project.performance_security_operations.operations:
        parts.append(
            "- **운영**: " + "; ".join(project.performance_security_operations.operations)
        )
    return "\n".join(parts) if parts else "- 성능·보안·운영 고려사항은 추후 보강 가능합니다."


def describe_retrospective(project: Project) -> str:
    sections: list[str] = []
    mapping = (
        ("잘된 점", project.retrospective.what_went_well),
        ("어려웠던 점", project.retrospective.what_was_hard),
        ("배운 점", project.retrospective.what_i_learned),
        ("다음 단계", project.retrospective.next_steps),
    )
    for title, items in mapping:
        if items:
            sections.append(f"### {title}\n" + "\n".join(f"- {item}" for item in items))
    return "\n\n".join(sections) if sections else "- 회고 내용은 추후 프로젝트 진행 과정에 맞춰 보강할 수 있습니다."


def describe_links_and_assets(project: Project) -> str:
    items: list[str] = []
    if project.links.github:
        items.append(f"- **GitHub**: {project.links.github}")
    if project.links.demo:
        items.append(f"- **Demo**: {project.links.demo}")
    if project.links.docs:
        items.append(f"- **Docs**: {project.links.docs}")
    if project.links.video:
        items.append(f"- **Video**: {project.links.video}")
    for screenshot in project.assets.screenshots:
        items.append(f"- **스크린샷 · {screenshot.title or '이미지'}**: {screenshot.description} ({screenshot.path})")
    for diagram in project.assets.diagrams:
        items.append(f"- **다이어그램 · {diagram.title or '다이어그램'}**: {diagram.description} ({diagram.path})")
    return "\n".join(items) if items else "- 링크나 스크린샷 자산은 아직 등록되지 않았습니다."


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
            "describe_project_purpose": describe_project_purpose,
            "describe_problem_definition": describe_problem_definition,
            "describe_user_flow": describe_user_flow,
            "describe_tech_stack": describe_tech_stack,
            "describe_architecture_details": describe_architecture_details,
            "describe_features": describe_features,
            "describe_problem_solving_cases": describe_problem_solving_cases,
            "build_architecture_diagram": build_architecture_diagram,
            "summarize_project_outcomes": summarize_project_outcomes,
            "describe_operational_considerations": describe_operational_considerations,
            "describe_retrospective": describe_retrospective,
            "describe_links_and_assets": describe_links_and_assets,
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
            "describe_project_purpose": describe_project_purpose,
            "describe_problem_definition": describe_problem_definition,
            "describe_user_flow": describe_user_flow,
            "describe_tech_stack": describe_tech_stack,
            "describe_architecture_details": describe_architecture_details,
            "describe_features": describe_features,
            "describe_problem_solving_cases": describe_problem_solving_cases,
            "build_architecture_diagram": build_architecture_diagram,
            "summarize_project_outcomes": summarize_project_outcomes,
            "describe_operational_considerations": describe_operational_considerations,
            "describe_retrospective": describe_retrospective,
            "describe_links_and_assets": describe_links_and_assets,
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

{% if project.one_line_summary %}> {{ project.one_line_summary }}{% endif %}

{{ project.summary }}

## 왜 만들었는지

{{ describe_project_purpose(project) }}

## 문제 정의

{{ describe_problem_definition(project) }}

## 사용자 흐름

{{ describe_user_flow(project) }}

## 기술 스택 및 선정 이유

{{ describe_tech_stack(project) }}

## 아키텍처

```mermaid
{{ build_architecture_diagram(project) }}
```

{{ describe_architecture_details(project) }}

## 핵심 기능

{{ describe_features(project) }}

## 문제 해결 사례

{{ describe_problem_solving_cases(project) }}

## 성능 / 보안 / 운영 고려사항

{{ describe_operational_considerations(project) }}

## 결과 및 성과

{{ summarize_project_outcomes(project) }}

## 회고

{{ describe_retrospective(project) }}

## 링크 및 참고 자료

{{ describe_links_and_assets(project) }}
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

### 프로젝트 개요

{% if project.one_line_summary %}> {{ project.one_line_summary }}{% endif %}

{{ project.summary }}

- **기간**: {{ project.period.display() }}
- **역할**: {{ project.role }}
- **기술 스택**: {{ project.tech_stack | join(", ") }}

### 왜 만들었는지

{{ describe_project_purpose(project) }}

### 문제 정의

{{ describe_problem_definition(project) }}

### 사용자 흐름

{{ describe_user_flow(project) }}

### 기술 스택 및 선정 이유

{{ describe_tech_stack(project) }}

### 아키텍처

```mermaid
{{ build_architecture_diagram(project) }}
```

{{ describe_architecture_details(project) }}

### 핵심 기능

{{ describe_features(project) }}

### 문제 해결 사례

{{ describe_problem_solving_cases(project) }}

### 성능 / 보안 / 운영 고려사항

{{ describe_operational_considerations(project) }}

### 결과 및 확장성

{{ summarize_project_outcomes(project) }}

### 회고

{{ describe_retrospective(project) }}

### 링크 및 참고 자료

{{ describe_links_and_assets(project) }}

---
{% endfor %}
"""

# doc_type → 내장 폴백 문자열 매핑
# 반드시 상수 선언 후에 위치해야 함
_BUILTIN_FALLBACK: dict[str, str] = {
    "resume": _BUILTIN_RESUME_DEFAULT,
    "career": _BUILTIN_RESUME_DEFAULT,
    "portfolio": _BUILTIN_PORTFOLIO_DEFAULT,
}
