"""devfolio project * — 프로젝트 관리 커맨드."""

from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from devfolio.commands.common import check_init
from devfolio.core.project_manager import ProjectManager

app = typer.Typer(help="프로젝트 관리", rich_markup_mode="rich")
console = Console()
pm = ProjectManager()

_TYPE_CHOICES = {"1": "company", "2": "side", "3": "course"}
_STATUS_CHOICES = {"1": "done", "2": "in_progress", "3": "planned"}
_TYPE_LABELS = {"company": "회사 업무", "side": "사이드 프로젝트", "course": "인강/학습"}
_STATUS_LABELS = {"done": "완료", "in_progress": "진행 중", "planned": "예정"}


@app.command("add")
def add_project(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="프로젝트명"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="유형 (company/side/course)"),
):
    """새 프로젝트 등록."""
    check_init()

    console.print("\n[bold cyan]── 새 프로젝트 등록 ──[/bold cyan]\n")
    console.print("[dim]Enter를 누르면 선택 항목은 비워둘 수 있고, 나중에 `project edit`로 수정할 수 있습니다.[/dim]\n")

    name = name or Prompt.ask("프로젝트명")

    if not type:
        console.print("프로젝트 유형:")
        console.print("  [bold]1[/bold]  회사 업무 (company)")
        console.print("  [bold]2[/bold]  사이드 프로젝트 (side)")
        console.print("  [bold]3[/bold]  인강/학습 (course)")
        type = _TYPE_CHOICES[Prompt.ask("번호 선택", choices=["1", "2", "3"], default="1")]

    organization = Prompt.ask("소속/주관", default="")
    period_start = Prompt.ask("시작 월 (YYYY-MM, 선택)", default="")
    period_end = Prompt.ask("종료 월 (YYYY-MM, 진행 중이면 Enter)", default="") or None

    console.print("상태:")
    console.print("  [bold]1[/bold]  완료 (done)")
    console.print("  [bold]2[/bold]  진행 중 (in_progress)")
    console.print("  [bold]3[/bold]  예정 (planned)")
    status_key = Prompt.ask("번호 선택", choices=["1", "2", "3"], default="1")
    status = _STATUS_CHOICES[status_key]

    role = Prompt.ask("역할 (예: 백엔드 개발자)", default="")
    team_size_str = Prompt.ask("팀 규모 (명)", default="1")
    tech_stack_str = Prompt.ask("기술 스택 (쉼표 구분, 선택)", default="")
    summary = Prompt.ask("프로젝트 한 줄 요약", default="")
    tags_str = Prompt.ask("태그 (쉼표 구분, 선택)", default="")

    try:
        team_size = int(team_size_str)
        if team_size < 1:
            console.print("[yellow]⚠ 팀 규모는 1 이상이어야 합니다. 기본값 1로 설정합니다.[/yellow]")
            team_size = 1
    except ValueError:
        console.print(f"[yellow]⚠ '{team_size_str}'은(는) 유효한 숫자가 아닙니다. 기본값 1로 설정합니다.[/yellow]")
        team_size = 1

    tech_stack = [s.strip() for s in tech_stack_str.split(",") if s.strip()]
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]

    project = pm.create_project(
        name=name,
        type=type,
        status=status,
        organization=organization,
        period_start=period_start,
        period_end=period_end,
        role=role,
        team_size=team_size,
        tech_stack=tech_stack,
        summary=summary,
        tags=tags,
    )

    console.print(
        f"\n[bold green]✓ 프로젝트 등록 완료![/bold green] "
        f"ID: [dim]{project.id}[/dim]"
    )
    console.print(
        f"[dim]다음 단계: `devfolio task add --project \"{project.name}\"` "
        f"또는 `devfolio export resume`[/dim]"
    )

    if Confirm.ask("\n작업 내역을 바로 추가하시겠습니까?", default=False):
        _add_task_interactive(project.name)


def _add_task_interactive(project_name: str) -> None:
    """task add를 프로젝트 추가 흐름 내에서 재사용."""
    from devfolio.commands.task import _do_add_task
    _do_add_task(project_name)


@app.command("list")
def list_projects(
    stack: Optional[str] = typer.Option(None, "--stack", help="기술 스택 필터"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="유형 필터 (company/side/course)"),
    tag: Optional[str] = typer.Option(None, "--tag", help="태그 필터"),
):
    """전체 프로젝트 목록 조회."""
    check_init()

    projects = pm.list_projects(
        stack_filter=stack, type_filter=type, tag_filter=tag
    )

    if not projects:
        console.print("[yellow]등록된 프로젝트가 없습니다.[/yellow]")
        console.print("  [dim]devfolio project add[/dim] 로 첫 프로젝트를 등록하세요.")
        return

    table = Table(title="프로젝트 목록", show_header=True, header_style="bold cyan")
    table.add_column("프로젝트명", style="bold")
    table.add_column("유형")
    table.add_column("기간")
    table.add_column("상태")
    table.add_column("기술 스택", overflow="fold")
    table.add_column("작업 수", justify="right")

    for p in projects:
        table.add_row(
            p.name,
            _TYPE_LABELS.get(p.type, p.type),
            p.period.display(),
            _STATUS_LABELS.get(p.status, p.status),
            ", ".join(p.tech_stack[:4]) + ("..." if len(p.tech_stack) > 4 else ""),
            str(len(p.tasks)),
        )

    console.print(table)


@app.command("show")
def show_project(
    name: str = typer.Argument(..., help="프로젝트명 또는 ID"),
):
    """프로젝트 상세 조회."""
    check_init()

    project = pm.get_project_or_raise(name)

    console.print(f"\n[bold cyan]── {project.name} ──[/bold cyan]")
    console.print(f"  ID: [dim]{project.id}[/dim]")
    console.print(f"  유형: {_TYPE_LABELS.get(project.type, project.type)}")
    console.print(f"  기간: {project.period.display()}")
    console.print(f"  상태: {_STATUS_LABELS.get(project.status, project.status)}")
    console.print(f"  소속: {project.organization}")
    console.print(f"  역할: {project.role}")
    console.print(f"  팀 규모: {project.team_size}명")
    console.print(f"  기술 스택: {', '.join(project.tech_stack)}")
    console.print(f"  태그: {', '.join(project.tags) or '없음'}")
    console.print(f"\n  [bold]요약[/bold]: {project.summary}")

    if project.tasks:
        console.print(f"\n  [bold]작업 내역 ({len(project.tasks)}개)[/bold]")
        for task in project.tasks:
            ai_indicator = " [green]✓AI[/green]" if task.ai_generated_text else ""
            console.print(f"    • {task.name}{ai_indicator}")
            console.print(f"      기간: {task.period.display()}")
            if task.keywords:
                console.print(f"      키워드: {', '.join(task.keywords)}")
    else:
        console.print("\n  [yellow]등록된 작업 내역이 없습니다.[/yellow]")
        console.print(
            f"  [dim]devfolio task add --project \"{project.name}\"[/dim]"
        )


@app.command("edit")
def edit_project(
    name: str = typer.Argument(..., help="프로젝트명 또는 ID"),
):
    """프로젝트 정보 수정."""
    check_init()

    project = pm.get_project_or_raise(name)

    console.print(f"\n[bold cyan]── {project.name} 수정 ──[/bold cyan]")
    console.print("[dim](변경하지 않으려면 Enter)[/dim]\n")

    new_name = Prompt.ask("프로젝트명", default=project.name)
    new_org = Prompt.ask("소속/주관", default=project.organization)
    new_start = Prompt.ask("시작 월 (YYYY-MM)", default=project.period.start or "")
    new_end = Prompt.ask("종료 월 (YYYY-MM, 진행 중이면 빈 값)", default=project.period.end or "")
    new_role = Prompt.ask("역할", default=project.role)
    new_size = Prompt.ask("팀 규모", default=str(project.team_size))
    new_stack = Prompt.ask("기술 스택 (쉼표 구분)", default=", ".join(project.tech_stack))
    new_summary = Prompt.ask("한 줄 요약", default=project.summary)
    new_tags = Prompt.ask("태그 (쉼표 구분)", default=", ".join(project.tags))

    from devfolio.models.project import Period

    updated = pm.rename_project(
        name,
        new_name=new_name,
        organization=new_org,
        period=Period(start=new_start or None, end=new_end or None),
        role=new_role,
        team_size=int(new_size) if new_size.isdigit() else project.team_size,
        tech_stack=[s.strip() for s in new_stack.split(",") if s.strip()],
        summary=new_summary,
        tags=[t.strip() for t in new_tags.split(",") if t.strip()],
    )

    if updated.id != project.id:
        console.print(
            f"\n[bold green]✓ 수정되었습니다.[/bold green] "
            f"[dim]ID 변경: {project.id} → {updated.id}[/dim]"
        )
    else:
        console.print("\n[bold green]✓ 수정되었습니다.[/bold green]")


@app.command("delete")
def delete_project(
    name: str = typer.Argument(..., help="프로젝트명 또는 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="확인 프롬프트 건너뜀"),
):
    """프로젝트 삭제."""
    check_init()

    project = pm.get_project_or_raise(name)

    if not yes:
        if not Confirm.ask(
            f"[red]'{project.name}'[/red] 프로젝트와 모든 작업 내역을 삭제하시겠습니까?"
        ):
            console.print("[yellow]취소되었습니다.[/yellow]")
            return

    pm.delete_project(name)
    console.print(f"[bold green]✓[/bold green] '{project.name}' 삭제되었습니다.")
