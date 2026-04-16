"""devfolio ai * — AI 기반 문서 생성 커맨드."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm

from devfolio.core.ai_service import AIService
from devfolio.core.project_manager import ProjectManager
from devfolio.core.storage import is_initialized, list_projects, load_config

app = typer.Typer(help="AI 기능", rich_markup_mode="rich")
generate_app = typer.Typer(help="AI 문서 생성")
app.add_typer(generate_app, name="generate")

console = Console()
pm = ProjectManager()


def _check_init():
    if not is_initialized():
        console.print(
            "[red]오류:[/red] DevFolio가 초기화되지 않았습니다. "
            "[bold]devfolio init[/bold] 을 먼저 실행하세요."
        )
        raise typer.Exit(1)


def _get_service() -> AIService:
    config = load_config()
    if not config.default_ai_provider:
        console.print(
            "[red]오류:[/red] AI Provider가 설정되지 않았습니다.\n"
            "  [dim]devfolio config ai set[/dim] 으로 설정하세요."
        )
        raise typer.Exit(1)
    return AIService(config)


@generate_app.command("task")
def generate_task(
    project: str = typer.Argument(..., help="프로젝트명"),
    task: str = typer.Option(..., "--task", "-t", help="작업명"),
    lang: str = typer.Option("ko", "--lang", "-l", help="언어 (ko/en/both)"),
    provider: Optional[str] = typer.Option(None, "--provider", help="AI Provider 오버라이드"),
    refresh: bool = typer.Option(False, "--refresh", "-r", help="캐시 무시하고 재생성"),
):
    """작업 내역 → 경력기술서 bullet point 생성."""
    _check_init()

    proj = pm.get_project(project)
    if not proj:
        console.print(f"[red]오류:[/red] 프로젝트를 찾을 수 없습니다: [bold]{project}[/bold]")
        raise typer.Exit(1)

    task_obj = next(
        (t for t in proj.tasks if t.name == task or t.id == task), None
    )
    if not task_obj:
        console.print(f"[red]오류:[/red] 작업 내역을 찾을 수 없습니다: [bold]{task}[/bold]")
        raise typer.Exit(1)

    if task_obj.ai_generated_text and not refresh:
        console.print("[cyan]캐시된 AI 문구가 있습니다.[/cyan] (재생성: --refresh)\n")
        console.print(task_obj.ai_generated_text)
        return

    service = _get_service()
    config = load_config()

    with console.status("[cyan]AI가 문구를 생성하는 중...[/cyan]"):
        try:
            result = service.generate_task_text(
                task=task_obj,
                lang=lang,
                provider_name=provider or config.default_ai_provider,
                force_refresh=refresh,
            )
        except Exception as e:
            console.print(f"[red]오류:[/red] {e}")
            raise typer.Exit(1)

    console.print("\n[bold green]── AI 생성 결과 ──[/bold green]\n")
    console.print(result)

    if Confirm.ask("\n이 문구를 저장하시겠습니까?", default=True):
        pm.save_task_ai_text(proj.name, task_obj.name, result)
        console.print("[bold green]✓ 저장되었습니다.[/bold green]")


@generate_app.command("project")
def generate_project(
    project: str = typer.Argument(..., help="프로젝트명"),
    lang: str = typer.Option("ko", "--lang", "-l", help="언어 (ko/en/both)"),
    provider: Optional[str] = typer.Option(None, "--provider", help="AI Provider 오버라이드"),
):
    """프로젝트 전체 요약 문단 생성."""
    _check_init()

    proj = pm.get_project(project)
    if not proj:
        console.print(f"[red]오류:[/red] 프로젝트를 찾을 수 없습니다: [bold]{project}[/bold]")
        raise typer.Exit(1)

    service = _get_service()
    config = load_config()

    with console.status("[cyan]AI가 프로젝트 요약을 생성하는 중...[/cyan]"):
        try:
            result = service.generate_project_summary(
                project=proj,
                lang=lang,
                provider_name=provider or config.default_ai_provider,
            )
        except Exception as e:
            console.print(f"[red]오류:[/red] {e}")
            raise typer.Exit(1)

    console.print("\n[bold green]── AI 생성 결과 ──[/bold green]\n")
    console.print(result)


@generate_app.command("resume")
def generate_resume(
    lang: str = typer.Option("ko", "--lang", "-l", help="언어 (ko/en/both)"),
    provider: Optional[str] = typer.Option(None, "--provider", help="AI Provider 오버라이드"),
    projects_filter: Optional[str] = typer.Option(
        None, "--projects", help="포함할 프로젝트 (쉼표 구분, 기본: 전체)"
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="저장 파일 경로"),
):
    """전체 경력기술서 AI 생성."""
    _check_init()

    all_projects = list_projects()
    if not all_projects:
        console.print("[yellow]등록된 프로젝트가 없습니다.[/yellow]")
        raise typer.Exit(1)

    if projects_filter:
        names = {n.strip() for n in projects_filter.split(",")}
        selected = [p for p in all_projects if p.name in names or p.id in names]
    else:
        selected = all_projects

    config = load_config()
    service = AIService(config)

    with console.status("[cyan]AI가 경력기술서를 생성하는 중...[/cyan]"):
        try:
            result = service.generate_full_resume(
                projects=selected,
                user_name=config.user.name,
                lang=lang,
                provider_name=provider or config.default_ai_provider,
            )
        except Exception as e:
            console.print(f"[red]오류:[/red] {e}")
            raise typer.Exit(1)

    console.print("\n[bold green]── AI 생성 결과 ──[/bold green]\n")
    console.print(result)

    if output:
        output.write_text(result, encoding="utf-8")
        console.print(f"\n[bold green]✓ 저장되었습니다:[/bold green] {output}")
    elif Confirm.ask("\n파일로 저장하시겠습니까?", default=True):
        from devfolio.core.storage import EXPORTS_DIR
        save_path = EXPORTS_DIR / "resume_ai.md"
        save_path.write_text(result, encoding="utf-8")
        console.print(f"[bold green]✓ 저장되었습니다:[/bold green] {save_path}")


@app.command("match-jd")
def match_jd(
    jd_file: Optional[Path] = typer.Option(None, "--file", "-f", help="채용 공고 파일 경로"),
    jd_text: Optional[str] = typer.Option(None, "--text", "-t", help="채용 공고 텍스트"),
    projects_filter: Optional[str] = typer.Option(
        None, "--projects", help="비교할 프로젝트 (쉼표 구분, 기본: 전체)"
    ),
    provider: Optional[str] = typer.Option(None, "--provider", help="AI Provider 오버라이드"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="결과 저장 경로"),
):
    """채용 공고 JD와 포트폴리오 매칭 분석."""
    _check_init()

    if not jd_file and not jd_text:
        console.print("[red]오류:[/red] --file 또는 --text 옵션을 지정하세요.")
        raise typer.Exit(1)

    if jd_file:
        if not jd_file.exists():
            console.print(f"[red]오류:[/red] 파일을 찾을 수 없습니다: {jd_file}")
            raise typer.Exit(1)
        jd_content = jd_file.read_text(encoding="utf-8")
    else:
        jd_content = jd_text  # type: ignore

    all_projects = list_projects()
    if not all_projects:
        console.print("[yellow]등록된 프로젝트가 없습니다.[/yellow]")
        raise typer.Exit(1)

    if projects_filter:
        names = {n.strip() for n in projects_filter.split(",")}
        selected = [p for p in all_projects if p.name in names or p.id in names]
    else:
        selected = all_projects

    service = _get_service()
    config = load_config()

    with console.status("[cyan]AI가 JD를 분석하는 중...[/cyan]"):
        try:
            result = service.match_job_description(
                jd_text=jd_content,
                projects=selected,
                provider_name=provider or config.default_ai_provider,
            )
        except Exception as e:
            console.print(f"[red]오류:[/red] {e}")
            raise typer.Exit(1)

    console.print("\n[bold green]── JD 매칭 분석 결과 ──[/bold green]\n")
    console.print(result)

    if output:
        output.write_text(result, encoding="utf-8")
        console.print(f"\n[bold green]✓ 저장되었습니다:[/bold green] {output}")


@app.command("refine")
def refine(
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="개선할 파일 경로"),
    text: Optional[str] = typer.Option(None, "--text", "-t", help="개선할 텍스트"),
    provider: Optional[str] = typer.Option(None, "--provider", help="AI Provider 오버라이드"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="결과 저장 경로"),
):
    """기존 문구 AI 개선."""
    _check_init()

    if not file and not text:
        console.print("[red]오류:[/red] --file 또는 --text 옵션을 지정하세요.")
        raise typer.Exit(1)

    if file:
        if not file.exists():
            console.print(f"[red]오류:[/red] 파일을 찾을 수 없습니다: {file}")
            raise typer.Exit(1)
        content = file.read_text(encoding="utf-8")
    else:
        content = text  # type: ignore

    service = _get_service()
    config = load_config()

    with console.status("[cyan]AI가 문구를 개선하는 중...[/cyan]"):
        try:
            result = service.refine_text(
                text=content,
                provider_name=provider or config.default_ai_provider,
            )
        except Exception as e:
            console.print(f"[red]오류:[/red] {e}")
            raise typer.Exit(1)

    console.print("\n[bold green]── 개선된 문구 ──[/bold green]\n")
    console.print(result)

    if output:
        output.write_text(result, encoding="utf-8")
        console.print(f"\n[bold green]✓ 저장되었습니다:[/bold green] {output}")
    elif file and Confirm.ask("\n원본 파일을 개선된 내용으로 덮어쓰시겠습니까?", default=False):
        file.write_text(result, encoding="utf-8")
        console.print(f"[bold green]✓ 저장되었습니다:[/bold green] {file}")
