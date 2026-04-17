"""devfolio sync * — GitHub 백업 동기화."""

from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt

from devfolio.commands.common import check_init
from devfolio.core.storage import load_config, save_config
from devfolio.core.sync_service import SyncService
from devfolio.models.config import SyncConfig

app = typer.Typer(help="GitHub 백업 동기화", rich_markup_mode="rich")
console = Console()


@app.command("setup")
def sync_setup(
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="GitHub 저장소 URL 또는 owner/repo"),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="동기화 브랜치 (기본: main)"),
):
    """GitHub 백업 저장소 연결."""
    check_init()

    config = load_config()
    repo_input = repo or Prompt.ask(
        "GitHub 저장소 URL 또는 owner/repo",
        default=config.sync.repo_url or "",
    )
    branch_name = (branch or Prompt.ask("동기화 브랜치", default=config.sync.branch or "main")).strip() or "main"
    normalized = SyncService.normalize_repo_url(repo_input)

    config.sync = SyncConfig(enabled=True, repo_url=normalized, branch=branch_name)
    save_config(config)

    service = SyncService(config)
    with console.status("[cyan]GitHub 저장소 연결을 확인하는 중...[/cyan]"):
        service.validate_remote_access()

    console.print(f"[bold green]✓[/bold green] GitHub 동기화 저장소가 연결되었습니다: {normalized}")
    console.print(f"[dim]브랜치: {branch_name} | 실행: `devfolio sync run`[/dim]")


@app.command("status")
def sync_status() -> None:
    """현재 GitHub 동기화 설정 및 마지막 실행 상태 조회."""
    check_init()

    service = SyncService(load_config())
    status = service.get_status()

    console.print("\n[bold cyan]── GitHub Sync 상태 ──[/bold cyan]")
    console.print(f"  활성화: {'예' if status['enabled'] else '아니오'}")
    console.print(f"  저장소: {status['repo_url'] or '미설정'}")
    console.print(f"  브랜치: {status['branch'] or 'main'}")
    console.print(f"  로컬 저장소: {status['repo_dir']}")
    console.print(f"  로컬 clone 존재: {'예' if status['repo_exists'] else '아니오'}")
    console.print(f"  마지막 상태: {status['last_status'] or '기록 없음'}")
    console.print(f"  마지막 동기화: {status['last_synced_at'] or '기록 없음'}")
    console.print(f"  마지막 커밋: {status['last_commit'] or '기록 없음'}")
    if status["last_error"]:
        console.print(f"  최근 오류: [red]{status['last_error']}[/red]")


@app.command("run")
def sync_run() -> None:
    """현재 DevFolio 데이터를 GitHub 백업 저장소로 동기화."""
    check_init()

    service = SyncService(load_config())
    with console.status("[cyan]GitHub 백업을 동기화하는 중...[/cyan]"):
        result = service.run()

    if result["changed"]:
        console.print("[bold green]✓ GitHub 동기화가 완료되었습니다.[/bold green]")
        console.print(f"  커밋: {result['commit']}")
        console.print(f"  저장소: {result['repo_dir']}")
    else:
        console.print("[bold green]✓ 변경 사항이 없어 GitHub 동기화는 건너뛰었습니다.[/bold green]")
        console.print(f"  저장소: {result['repo_dir']}")
