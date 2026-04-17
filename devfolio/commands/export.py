"""devfolio export * — 문서 내보내기 커맨드."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from devfolio.commands.common import check_init
from devfolio.core.export_engine import ExportEngine
from devfolio.core.project_manager import ProjectManager
from devfolio.core.storage import list_projects, load_config
from devfolio.core.template_engine import TemplateEngine
from devfolio.exceptions import DevfolioError

app = typer.Typer(help="문서 내보내기", rich_markup_mode="rich")
console = Console()
pm = ProjectManager()

_FORMATS = {"md", "pdf", "docx", "html", "json", "csv"}


def _do_export(content: str, fmt: str, filename: str, output: Optional[Path]) -> Path:
    engine = ExportEngine()
    format_map = {
        "md": engine.export_markdown,
        "pdf": engine.export_pdf,
        "docx": engine.export_docx,
        "html": engine.export_html,
    }

    if fmt not in format_map:
        raise DevfolioError(
            f"지원하지 않는 포맷입니다: {fmt}",
            hint=f"지원 포맷: {', '.join(sorted(format_map))}",
        )

    result_path = format_map[fmt](content, filename)

    if output:
        result_path = engine.copy_to(result_path, output)

    return result_path


@app.command("resume")
def export_resume(
    format: Optional[str] = typer.Option(None, "--format", "-f", help="출력 포맷 (md/pdf/docx/html/json)"),
    template: Optional[str] = typer.Option(None, "--template", "-t", help="템플릿 이름"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="출력 파일 경로"),
    projects_filter: Optional[str] = typer.Option(
        None, "--projects", help="포함할 프로젝트 (쉼표 구분, 기본: 전체)"
    ),
):
    """경력기술서 내보내기."""
    check_init()

    config = load_config()
    fmt = (format or config.export.default_format or "md").lower()
    template_name = template or config.export.default_template or "default"
    if fmt not in _FORMATS:
        raise DevfolioError(
            f"지원하지 않는 포맷입니다: {fmt}",
            hint=f"지원 포맷: {', '.join(sorted(_FORMATS))}",
        )

    all_projects = list_projects()
    if not all_projects:
        raise DevfolioError(
            "등록된 프로젝트가 없습니다.",
            hint="`devfolio project add`로 첫 프로젝트를 먼저 등록하세요.",
        )

    if projects_filter:
        names = {n.strip() for n in projects_filter.split(",")}
        selected = [p for p in all_projects if p.name in names or p.id in names]
        if not selected:
            raise DevfolioError(
                "지정한 프로젝트를 찾을 수 없습니다.",
                hint="`devfolio project list`로 프로젝트명과 ID를 확인하세요.",
            )
    else:
        selected = all_projects

    tmpl_engine = TemplateEngine()

    with console.status("[cyan]문서를 생성하는 중...[/cyan]"):
        try:
            content = tmpl_engine.render(
                projects=selected,
                config=config,
                template_name=template_name,
                doc_type="resume",
            )
            if fmt == "json":
                import json
                content = json.dumps(
                    [p.model_dump() for p in selected], ensure_ascii=False, indent=2
                )
                if output:
                    result = output
                else:
                    from devfolio.core.storage import EXPORTS_DIR
                    result = EXPORTS_DIR / "resume.json"
                result.write_text(content, encoding="utf-8")
            elif fmt == "csv":
                engine = ExportEngine()
                result = engine.export_csv(selected, f"resume_{template_name}")
                if output:
                    result = engine.copy_to(result, output)
            else:
                result = _do_export(content, fmt, f"resume_{template_name}", output)
        except Exception as e:
            raise DevfolioError(
                f"경력기술서를 내보낼 수 없습니다: {e}",
                hint="템플릿 이름, 출력 포맷, 선택한 프로젝트를 다시 확인하세요.",
            ) from e

    console.print(f"[bold green]✓ 내보내기 완료:[/bold green] {result}")
    console.print("[dim]다음 단계: `devfolio sync run`으로 GitHub 백업을 갱신할 수 있습니다.[/dim]")


@app.command("portfolio")
def export_portfolio(
    format: Optional[str] = typer.Option(None, "--format", "-f", help="출력 포맷 (md/html/pdf)"),
    template: Optional[str] = typer.Option(None, "--template", "-t", help="템플릿 이름"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="출력 파일 경로"),
    projects_filter: Optional[str] = typer.Option(
        None, "--projects", help="포함할 프로젝트 (쉼표 구분)"
    ),
):
    """포트폴리오 내보내기."""
    check_init()

    config = load_config()
    template_name = template or config.export.default_template or "default"
    supported_formats = {"md", "html", "pdf", "csv"}
    default_portfolio_format = (
        config.export.default_format if config.export.default_format in supported_formats else "html"
    )
    fmt = (format or default_portfolio_format).lower()
    if fmt not in supported_formats:
        raise DevfolioError(
            f"포트폴리오는 `{fmt}` 포맷을 지원하지 않습니다.",
            hint=f"지원 포맷: {', '.join(sorted(supported_formats))}",
        )
    all_projects = list_projects()
    if not all_projects:
        raise DevfolioError(
            "등록된 프로젝트가 없습니다.",
            hint="`devfolio project add`로 첫 프로젝트를 먼저 등록하세요.",
        )

    if projects_filter:
        names = {n.strip() for n in projects_filter.split(",")}
        selected = [p for p in all_projects if p.name in names or p.id in names]
        if not selected:
            raise DevfolioError(
                "지정한 프로젝트를 찾을 수 없습니다.",
                hint="`devfolio project list`로 프로젝트명과 ID를 확인하세요.",
            )
    else:
        selected = all_projects

    tmpl_engine = TemplateEngine()

    with console.status("[cyan]포트폴리오를 생성하는 중...[/cyan]"):
        try:
            if fmt == "csv":
                engine = ExportEngine()
                result = engine.export_csv(selected, f"portfolio_{template_name}")
                if output:
                    result = engine.copy_to(result, output)
            else:
                content = tmpl_engine.render(
                    projects=selected,
                    config=config,
                    template_name=template_name,
                    doc_type="portfolio",
                )
                result = _do_export(content, fmt, f"portfolio_{template_name}", output)
        except Exception as e:
            raise DevfolioError(
                f"포트폴리오를 내보낼 수 없습니다: {e}",
                hint="템플릿 이름, 출력 포맷, 선택한 프로젝트를 다시 확인하세요.",
            ) from e

    console.print(f"[bold green]✓ 내보내기 완료:[/bold green] {result}")
    console.print("[dim]다음 단계: `devfolio sync run`으로 GitHub 백업을 갱신할 수 있습니다.[/dim]")


@app.command("project")
def export_project(
    name: str = typer.Argument(..., help="프로젝트명"),
    format: str = typer.Option("md", "--format", "-f", help="출력 포맷 (md/pdf/docx/html)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="출력 파일 경로"),
):
    """단일 프로젝트 한 장 요약 내보내기."""
    check_init()

    fmt = format.lower()
    project = pm.get_project_or_raise(name)

    config = load_config()
    tmpl_engine = TemplateEngine()

    with console.status("[cyan]문서를 생성하는 중...[/cyan]"):
        try:
            content = tmpl_engine.render_project(project=project, config=config)
            result = _do_export(content, fmt, f"project_{project.id}", output)
        except Exception as e:
            raise DevfolioError(
                f"프로젝트 문서를 내보낼 수 없습니다: {e}",
                hint="출력 포맷과 템플릿 상태를 확인하세요.",
            ) from e

    console.print(f"[bold green]✓ 내보내기 완료:[/bold green] {result}")
