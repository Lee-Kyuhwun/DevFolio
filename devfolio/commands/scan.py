"""devfolio scan — git 저장소를 분석해 본인 커밋 기반 포트폴리오를 자동 생성한다."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from devfolio.commands.common import check_init
from devfolio.core.git_scanner import build_project_payload, scan_repo
from devfolio.core.project_manager import ProjectManager
from devfolio.core.storage import list_projects, load_config, save_project
from devfolio.exceptions import DevfolioError
from devfolio.models.project import Period, Project, Task

app = typer.Typer(help="Git 저장소 스캔 기반 포트폴리오 자동 생성", rich_markup_mode="rich")
console = Console()
pm = ProjectManager()


def _find_existing_project_by_repo(repo_url: str) -> Optional[Project]:
    if not repo_url:
        return None
    for project in list_projects():
        if project.repo_url and project.repo_url == repo_url:
            return project
    return None


def _payload_to_project(payload: dict, project_id: str) -> Project:
    tasks: list[Task] = []
    for i, task_data in enumerate(payload["tasks"]):
        tasks.append(
            Task(
                id=f"task_{i+1:03d}",
                name=task_data["name"],
                period=Period(
                    start=task_data.get("period_start") or None,
                    end=task_data.get("period_end") or None,
                ),
                problem=task_data.get("problem", ""),
                solution=task_data.get("solution", ""),
                result=task_data.get("result", ""),
                tech_used=task_data.get("tech_used", []),
                keywords=task_data.get("keywords", []),
            )
        )
    return Project(
        id=project_id,
        name=payload["name"],
        type=payload["type"],
        status=payload["status"],
        organization=payload.get("organization", ""),
        period=Period(
            start=payload.get("period_start") or None,
            end=payload.get("period_end") or None,
        ),
        role=payload.get("role", ""),
        team_size=payload.get("team_size", 1),
        tech_stack=payload.get("tech_stack", []),
        summary=payload.get("summary", ""),
        tags=payload.get("tags", []),
        tasks=tasks,
        repo_url=payload.get("repo_url", ""),
        last_commit_sha=payload.get("last_commit_sha", ""),
        scan_metrics=payload.get("scan_metrics", {}),
    )


def _print_scan_summary(payload: dict, cached: bool) -> None:
    metrics = payload.get("scan_metrics", {})
    tag = "[dim]cache hit[/dim]" if cached else "[green]new scan[/green]"
    body_lines = [
        f"[bold]{payload['name']}[/bold]  {tag}",
        f"기간: {payload.get('period_start') or '?'} ~ "
        f"{payload.get('period_end') or '현재'}",
        f"커밋: {metrics.get('commit_count', 0)}건 / "
        f"전체 대비 {metrics.get('authorship_ratio', 0)*100:.0f}%",
        f"변경: +{metrics.get('insertions', 0)} / -{metrics.get('deletions', 0)} LOC, "
        f"{metrics.get('files_touched', 0)} 파일",
        f"언어: {', '.join(metrics.get('languages', {}).keys()) or '-'}",
        f"분류: {metrics.get('categories', {}) or '-'}",
    ]
    console.print(Panel("\n".join(body_lines), title="Scan Summary", border_style="cyan"))

    table = Table(title="생성된 Task", show_lines=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("이름")
    table.add_column("기간")
    table.add_column("성과", overflow="fold")
    for i, t in enumerate(payload["tasks"], 1):
        period = f"{t.get('period_start') or '?'} ~ {t.get('period_end') or '?'}"
        table.add_row(str(i), t["name"], period, t.get("result", ""))
    console.print(table)


@app.callback(invoke_without_command=True)
def scan(
    ctx: typer.Context,
    path: Path = typer.Argument(
        Path("."),
        help="스캔할 git 저장소 경로",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    author: Optional[str] = typer.Option(
        None, "--author", "-a",
        help="필터링할 author email (미지정 시 설정의 user.email 사용)",
    ),
    refresh: bool = typer.Option(
        False, "--refresh",
        help="이미 등록된 프로젝트가 있어도 다시 스캔해서 갱신",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="저장하지 않고 분석 결과만 출력",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="확인 프롬프트 없이 바로 저장",
    ),
):
    """Git 저장소를 스캔해 본인 커밋 기반 포트폴리오 프로젝트를 자동 생성한다."""
    if ctx.invoked_subcommand is not None:
        return
    check_init()

    cfg = load_config()
    author_email = (author or cfg.user.email or "").strip()
    if not author_email:
        raise DevfolioError(
            "author email 이 설정되지 않았습니다.",
            hint="`devfolio config user set --email <...>` 또는 `--author <email>` 로 지정하세요.",
        )

    console.print(f"[dim]scanning {path} (author={author_email})...[/dim]")
    scan_result = scan_repo(path, author_email=author_email)

    existing = _find_existing_project_by_repo(scan_result.repo_url)

    # 캐시 히트: 동일 HEAD SHA 면 재분석 없이 바로 사용
    if existing and existing.last_commit_sha == scan_result.head_sha and not refresh:
        console.print(
            f"[green]✓[/green] 이미 최신 상태입니다: [bold]{existing.name}[/bold] "
            f"(sha={existing.last_commit_sha[:8]})"
        )
        payload = {
            "name": existing.name,
            "period_start": existing.period.start,
            "period_end": existing.period.end,
            "tasks": [
                {
                    "name": t.name,
                    "period_start": t.period.start,
                    "period_end": t.period.end,
                    "result": t.result,
                }
                for t in existing.tasks
            ],
            "scan_metrics": existing.scan_metrics,
        }
        _print_scan_summary(payload, cached=True)
        return

    payload = build_project_payload(scan_result)
    _print_scan_summary(payload, cached=False)

    if dry_run:
        console.print("[yellow]dry-run: 저장하지 않았습니다.[/yellow]")
        return

    if existing:
        if not yes:
            typer.confirm(
                f"기존 프로젝트 '{existing.name}'을(를) 새 스캔 결과로 갱신할까요?",
                abort=True,
            )
        updated = _payload_to_project(payload, existing.id)
        save_project(updated)
        console.print(
            f"[green]✓[/green] 갱신 완료: [bold]{updated.name}[/bold] "
            f"(sha={updated.last_commit_sha[:8]})"
        )
        return

    # 신규 등록
    project_id = pm._next_project_id(payload["name"])
    new_project = _payload_to_project(payload, project_id)
    save_project(new_project)
    console.print(
        f"[green]✓[/green] 새 프로젝트 등록: [bold]{new_project.name}[/bold] "
        f"(id={new_project.id}, sha={new_project.last_commit_sha[:8]})"
    )
    console.print(
        "[dim]`devfolio project show "
        f"{new_project.name}` 으로 확인하거나 `devfolio export` 로 내보낼 수 있습니다.[/dim]"
    )
