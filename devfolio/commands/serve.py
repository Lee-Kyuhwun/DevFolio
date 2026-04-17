"""devfolio serve — 웹 기반 Portfolio Studio 시작."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(help="웹 기반 Portfolio Studio", invoke_without_command=True)
console = Console()


@app.callback(invoke_without_command=True)
def serve(
    host: str = typer.Option("127.0.0.1", help="바인딩 호스트 (Docker: 0.0.0.0)"),
    port: int = typer.Option(8000, help="포트 번호"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="브라우저 자동 열기"),
) -> None:
    """웹 기반 Portfolio Studio를 시작합니다.

    브라우저에서 http://<host>:<port> 로 접속하세요.

    Docker에서 실행할 때는 --host 0.0.0.0 --no-open 을 사용하세요.
    """
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[bold red]오류:[/bold red] 웹 UI를 실행하려면 gui extra가 필요합니다.\n"
            "  [dim]pip install 'devfolio[gui]'[/dim]"
        )
        raise typer.Exit(1)

    from devfolio.web.app import create_app

    url = f"http://{host}:{port}"
    console.print(f"\n[bold cyan]DevFolio Portfolio Studio[/bold cyan]")
    console.print(f"  주소: [link={url}]{url}[/link]")
    console.print("  종료: Ctrl+C\n")

    if open_browser:
        import threading
        import time
        import webbrowser

        def _open():
            time.sleep(1.0)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
