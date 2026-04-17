"""DevFolio CLI 진입점 — 전역 오류 핸들러 포함."""

import sys

import typer
from rich.console import Console
from rich.panel import Panel

from devfolio.commands import ai, config, data, export, project, sync, task
from devfolio.commands.init_cmd import run_init
from devfolio.commands import serve as serve_cmd
from devfolio.exceptions import DevfolioError
from devfolio.i18n import init_from_config

app = typer.Typer(
    name="devfolio",
    help="[bold cyan]DevFolio[/bold cyan] — 개발자 포트폴리오 & 경력기술서 자동화 시스템",
    add_completion=False,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,  # 전역 핸들러로 처리
)

console = Console(stderr=True)

# 서브 커맨드 등록
app.add_typer(project.app, name="project", help="프로젝트 CRUD")
app.add_typer(task.app, name="task", help="작업 내역 CRUD")
app.add_typer(config.app, name="config", help="설정 관리 (AI Provider 등)")
app.add_typer(ai.app, name="ai", help="AI 문서 생성 / JD 매칭 / 문구 개선")
app.add_typer(export.app, name="export", help="Markdown / PDF / DOCX / HTML 내보내기")
app.add_typer(data.app, name="data", help="백업 / 복원 / YAML·JSON 가져오기")
app.add_typer(sync.app, name="sync", help="GitHub 백업 동기화")
app.add_typer(serve_cmd.app, name="serve", help="웹 기반 설정 GUI 시작")


@app.command("init")
def init(
    force: bool = typer.Option(False, "--force", "-f", help="이미 초기화된 경우에도 재설정"),
):
    """DevFolio 최초 설정 (대화형)."""
    run_init(force=force)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """DevFolio — 개발자 포트폴리오 & 경력기술서 자동화 시스템"""
    if ctx.invoked_subcommand is None:
        console_out = Console()
        console_out.print(ctx.get_help())


def cli():
    """CLI 진입점 — 전역 DevfolioError 처리."""
    # config가 있으면 언어 설정을 i18n에 반영
    try:
        from devfolio.core.storage import is_initialized, load_config
        if is_initialized():
            cfg = load_config()
            init_from_config(cfg.default_language)
    except Exception:
        pass  # config 없어도 기본 로케일(ko)로 진행

    try:
        app()
    except DevfolioError as e:
        console.print(f"\n[bold red]오류:[/bold red] {e.message}")
        if e.hint:
            console.print(f"  [dim]→ {e.hint}[/dim]\n")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]취소되었습니다.[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    cli()
