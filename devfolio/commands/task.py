"""devfolio task * — 작업 내역 관리 커맨드."""

from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from devfolio.core.project_manager import ProjectManager
from devfolio.core.storage import is_initialized
from devfolio.exceptions import DevfolioNotInitializedError

app = typer.Typer(help="작업 내역 관리", rich_markup_mode="rich")
console = Console()
pm = ProjectManager()


def _check_init():
    if not is_initialized():
        raise DevfolioNotInitializedError()


def _do_add_task(project_name: str):
    """대화형 작업 내역 입력 (내부 재사용 함수)."""
    console.print("\n[bold cyan]── 작업 내역 등록 ──[/bold cyan]\n")
    console.print("[dim]기간과 상세 설명은 비워둘 수 있고, 나중에 `task edit`로 보완할 수 있습니다.[/dim]\n")

    task_name = Prompt.ask("작업명")
    period_start = Prompt.ask("시작 월 (YYYY-MM)", default="")
    period_end = Prompt.ask("종료 월 (YYYY-MM, 진행 중이면 Enter)", default="") or None

    console.print("\n[dim]문제 상황 (AS-IS): 기존의 문제점이나 배경을 설명하세요[/dim]")
    problem = Prompt.ask("문제 상황", default="")

    console.print("[dim]해결 방법 (TO-BE): 어떻게 해결했는지 설명하세요[/dim]")
    solution = Prompt.ask("해결 방법", default="")

    console.print("[dim]성과/지표: 수치화된 결과가 있으면 포함하세요 (예: 응답속도 40% 개선)[/dim]")
    result = Prompt.ask("성과/지표", default="")

    tech_used_str = Prompt.ask("사용 기술 (쉼표 구분)", default="")
    keywords_str = Prompt.ask("키워드 태그 (쉼표 구분, 선택)", default="")

    tech_used = [s.strip() for s in tech_used_str.split(",") if s.strip()]
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]

    task = pm.add_task(
        project_name=project_name,
        name=task_name,
        period_start=period_start,
        period_end=period_end,
        problem=problem,
        solution=solution,
        result=result,
        tech_used=tech_used,
        keywords=keywords,
    )

    if task:
        console.print(f"\n[bold green]✓ 작업 내역 등록 완료![/bold green] ID: [dim]{task.id}[/dim]")
        console.print(
            f"[dim]다음 단계: `devfolio ai generate task \"{project_name}\" --task \"{task.name}\"` "
            f"또는 `devfolio export resume`[/dim]"
        )
    else:
        console.print(f"[red]오류:[/red] 프로젝트를 찾을 수 없습니다: {project_name}")

    return task


@app.command("add")
def add_task(
    project: str = typer.Option(..., "--project", "-p", help="프로젝트명"),
):
    """작업 내역 등록."""
    _check_init()

    proj = pm.get_project_or_raise(project)

    console.print(f"\n프로젝트: [bold]{proj.name}[/bold]")
    _do_add_task(proj.name)

    while Confirm.ask("\n추가 작업 내역을 등록하시겠습니까?", default=False):
        _do_add_task(proj.name)


@app.command("list")
def list_tasks(
    project: str = typer.Argument(..., help="프로젝트명 또는 ID"),
):
    """프로젝트의 작업 내역 목록 조회."""
    _check_init()

    proj = pm.get_project_or_raise(project)

    if not proj.tasks:
        console.print(f"[yellow]'{proj.name}'에 등록된 작업 내역이 없습니다.[/yellow]")
        return

    table = Table(
        title=f"{proj.name} — 작업 내역",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("작업명", style="bold")
    table.add_column("기간")
    table.add_column("사용 기술", overflow="fold")
    table.add_column("AI 문구", justify="center")

    for task in proj.tasks:
        table.add_row(
            task.name,
            task.period.display(),
            ", ".join(task.tech_used),
            "[green]✓[/green]" if task.ai_generated_text else "[dim]-[/dim]",
        )

    console.print(table)


@app.command("show")
def show_task(
    project: str = typer.Argument(..., help="프로젝트명"),
    task_name: str = typer.Argument(..., help="작업명"),
):
    """작업 내역 상세 조회."""
    _check_init()

    proj, task = pm.get_task_or_raise(project, task_name)

    console.print(f"\n[bold cyan]── {task.name} ──[/bold cyan]")
    console.print(f"  ID: [dim]{task.id}[/dim]")
    console.print(f"  기간: {task.period.display()}")
    console.print(f"\n  [bold]문제 상황[/bold]: {task.problem}")
    console.print(f"  [bold]해결 방법[/bold]: {task.solution}")
    console.print(f"  [bold]성과[/bold]: {task.result}")
    console.print(f"  [bold]사용 기술[/bold]: {', '.join(task.tech_used)}")
    console.print(f"  [bold]키워드[/bold]: {', '.join(task.keywords) or '없음'}")

    if task.ai_generated_text:
        console.print(f"\n  [bold green]AI 생성 문구:[/bold green]")
        console.print(task.ai_generated_text)


@app.command("edit")
def edit_task(
    project: str = typer.Argument(..., help="프로젝트명"),
    task_name: str = typer.Argument(..., help="작업명"),
):
    """작업 내역 수정."""
    _check_init()

    _, task = pm.get_task_or_raise(project, task_name)

    console.print(f"\n[bold cyan]── {task.name} 수정 ──[/bold cyan]")
    console.print("[dim](변경하지 않으려면 Enter)[/dim]\n")

    new_name = Prompt.ask("작업명", default=task.name)
    new_problem = Prompt.ask("문제 상황", default=task.problem)
    new_solution = Prompt.ask("해결 방법", default=task.solution)
    new_result = Prompt.ask("성과/지표", default=task.result)
    new_tech = Prompt.ask("사용 기술 (쉼표 구분)", default=", ".join(task.tech_used))
    new_keywords = Prompt.ask("키워드 (쉼표 구분)", default=", ".join(task.keywords))

    updated = pm.update_task(
        project_name=project,
        task_name=task_name,
        name=new_name,
        problem=new_problem,
        solution=new_solution,
        result=new_result,
        tech_used=[s.strip() for s in new_tech.split(",") if s.strip()],
        keywords=[k.strip() for k in new_keywords.split(",") if k.strip()],
    )

    if updated:
        console.print("\n[bold green]✓ 수정되었습니다.[/bold green]")
        if task.ai_generated_text:
            console.print(
                "[yellow]⚠ 내용이 변경되어 AI 캐시가 초기화되었습니다. "
                "`devfolio ai generate task`로 다시 생성하세요.[/yellow]"
            )
    else:
        console.print("[red]수정에 실패했습니다.[/red]")


@app.command("delete")
def delete_task(
    project: str = typer.Argument(..., help="프로젝트명"),
    task_name: str = typer.Argument(..., help="작업명"),
    yes: bool = typer.Option(False, "--yes", "-y", help="확인 프롬프트 건너뜀"),
):
    """작업 내역 삭제."""
    _check_init()
    _, task = pm.get_task_or_raise(project, task_name)

    if not yes:
        if not Confirm.ask(
            f"[red]'{task.name}'[/red] 작업 내역을 삭제하시겠습니까?"
        ):
            console.print("[yellow]취소되었습니다.[/yellow]")
            return

    pm.delete_task(project_name=project, task_name=task_name)
    console.print(f"[bold green]✓[/bold green] '{task.name}' 삭제되었습니다.")
