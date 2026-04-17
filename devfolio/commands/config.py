"""devfolio config * — 설정 관리 커맨드."""

from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from devfolio.core.storage import load_config, save_config
from devfolio.models.config import AIProviderConfig
from devfolio.utils.security import delete_api_key, mask_api_key, store_api_key

app = typer.Typer(help="설정 관리", rich_markup_mode="rich")
ai_app = typer.Typer(help="AI Provider 설정")
app.add_typer(ai_app, name="ai")

console = Console()

_PROVIDER_MODELS: dict[str, list[str]] = {
    "anthropic": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-haiku-4-5-20251001"],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    "gemini": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"],
    "ollama": ["llama3.2", "llama3.1", "mistral", "deepseek-coder"],
}


@ai_app.command("set")
def ai_set(
    provider: Optional[str] = typer.Option(None, "--provider", help="Provider 이름"),
):
    """AI Provider 및 API 키 설정."""
    config = load_config()

    if not provider:
        console.print("AI Provider를 선택하세요:")
        console.print("  [bold]1[/bold]  Anthropic (Claude)")
        console.print("  [bold]2[/bold]  OpenAI (GPT)")
        console.print("  [bold]3[/bold]  Google (Gemini)")
        console.print("  [bold]4[/bold]  Ollama (로컬 실행)")
        choice = Prompt.ask("번호 선택", choices=["1", "2", "3", "4"])
        provider_map = {"1": "anthropic", "2": "openai", "3": "gemini", "4": "ollama"}
        provider = provider_map[choice]

    models = _PROVIDER_MODELS.get(provider, [])
    if models:
        console.print(f"\n모델을 선택하세요 [{provider}]:")
        for i, m in enumerate(models, 1):
            console.print(f"  [bold]{i}[/bold]  {m}")
        idx = Prompt.ask(
            "번호 선택",
            choices=[str(i) for i in range(1, len(models) + 1)],
            default="1",
        )
        model = models[int(idx) - 1]
    else:
        model = Prompt.ask("모델명 입력")

    provider_cfg = AIProviderConfig(name=provider, model=model, key_stored=False)

    if provider == "ollama":
        base_url = Prompt.ask("Ollama 서버 URL", default="http://localhost:11434")
        provider_cfg.base_url = base_url
    else:
        api_key = Prompt.ask(f"{provider} API 키", password=True)
        if api_key:
            ok = store_api_key(provider, api_key)
            provider_cfg.key_stored = ok
            if not ok:
                console.print("[yellow]⚠ 키체인 저장 실패. 환경 변수로 관리하세요.[/yellow]")
            else:
                console.print("[green]✓ API 키가 키체인에 저장되었습니다.[/green]")

    config.upsert_provider(provider_cfg)
    if not config.default_ai_provider:
        config.default_ai_provider = provider

    save_config(config)
    console.print(f"[bold green]✓[/bold green] {provider} ({model}) 등록 완료.")

    if Confirm.ask(f"'{provider}'를 기본 Provider로 설정하시겠습니까?", default=True):
        config.default_ai_provider = provider
        save_config(config)


@ai_app.command("list")
def ai_list() -> None:
    """등록된 AI Provider 목록 조회."""
    config = load_config()

    if not config.ai_providers:
        console.print("[yellow]등록된 AI Provider가 없습니다.[/yellow]")
        console.print("  [dim]devfolio config ai set[/dim] 으로 등록하세요.")
        return

    table = Table(title="AI Provider 목록", header_style="bold cyan")
    table.add_column("Provider")
    table.add_column("모델")
    table.add_column("API 키")
    table.add_column("기본값", justify="center")

    for p in config.ai_providers:
        from devfolio.utils.security import get_api_key
        api_key = get_api_key(p.name) if p.name != "ollama" else None
        key_display = mask_api_key(api_key) if api_key else ("[dim]없음[/dim]" if p.name != "ollama" else "[dim]불필요[/dim]")
        is_default = "[green]✓[/green]" if p.name == config.default_ai_provider else ""
        table.add_row(p.name, p.model, key_display, is_default)

    console.print(table)


@ai_app.command("test")
def ai_test(
    provider: Optional[str] = typer.Option(None, "--provider", help="테스트할 Provider"),
):
    """AI Provider 연결 테스트."""
    config = load_config()

    from devfolio.core.ai_service import AIService
    service = AIService(config)

    provider_name = provider or config.default_ai_provider
    if not provider_name:
        console.print("[red]오류:[/red] 테스트할 Provider가 설정되지 않았습니다.")
        raise typer.Exit(1)

    console.print(f"[dim]{provider_name} 연결 테스트 중...[/dim]")

    with console.status(f"[cyan]{provider_name}에 연결 중...[/cyan]"):
        ok, message = service.test_connection(provider_name)

    if ok:
        console.print(f"[bold green]✓ 연결 성공![/bold green] 응답: {message[:100]}")
    else:
        console.print(f"[bold red]✗ 연결 실패[/bold red]\n  {message}")
        raise typer.Exit(1)


@ai_app.command("remove")
def ai_remove(
    provider: str = typer.Argument(..., help="제거할 Provider 이름"),
    yes: bool = typer.Option(False, "--yes", "-y"),
):
    """AI Provider 제거."""
    config = load_config()

    existing = config.get_provider(provider)
    if not existing:
        console.print(f"[red]오류:[/red] 등록되지 않은 Provider: {provider}")
        raise typer.Exit(1)

    if not yes:
        if not Confirm.ask(f"[red]'{provider}'[/red] Provider를 제거하시겠습니까?"):
            console.print("[yellow]취소되었습니다.[/yellow]")
            return

    config.ai_providers = [p for p in config.ai_providers if p.name != provider]
    if config.default_ai_provider == provider:
        config.default_ai_provider = config.ai_providers[0].name if config.ai_providers else ""
    delete_api_key(provider)
    save_config(config)
    console.print(f"[bold green]✓[/bold green] '{provider}' 제거되었습니다.")


@app.command("show")
def show_config() -> None:
    """현재 설정 전체 조회."""
    config = load_config()

    console.print("\n[bold cyan]── DevFolio 설정 ──[/bold cyan]")
    console.print(f"  버전: {config.version}")
    console.print(f"  기본 AI Provider: {config.default_ai_provider or '없음'}")
    console.print(f"  기본 언어: {config.default_language}")
    console.print(f"  기본 출력 포맷: {config.export.default_format}")
    console.print(f"  출력 디렉터리: {config.export.output_dir}")
    console.print(f"\n  [bold]사용자 정보[/bold]")
    console.print(f"    이름: {config.user.name}")
    console.print(f"    이메일: {config.user.email}")
    console.print(f"    GitHub: {config.user.github}")
    console.print(f"    블로그: {config.user.blog}")
    console.print(f"\n  [bold]GitHub Sync[/bold]")
    console.print(f"    활성화: {'예' if config.sync.enabled else '아니오'}")
    console.print(f"    저장소: {config.sync.repo_url or '미설정'}")
    console.print(f"    브랜치: {config.sync.branch}")


@app.command("set-default")
def set_default(
    format: Optional[str] = typer.Option(None, "--format", help="기본 출력 포맷 (pdf/docx/md/html)"),
    lang: Optional[str] = typer.Option(None, "--lang", help="기본 언어 (ko/en/both)"),
    provider: Optional[str] = typer.Option(None, "--provider", help="기본 AI Provider"),
):
    """기본값 설정."""
    config = load_config()
    changed = False

    if format:
        valid_formats = {"pdf", "docx", "md", "html", "json"}
        if format not in valid_formats:
            console.print(f"[red]오류:[/red] 유효하지 않은 포맷: {format}")
            raise typer.Exit(1)
        config.export.default_format = format
        changed = True

    if lang:
        if lang not in {"ko", "en", "both"}:
            console.print(f"[red]오류:[/red] 유효하지 않은 언어: {lang}")
            raise typer.Exit(1)
        config.default_language = lang
        changed = True

    if provider:
        if not config.get_provider(provider):
            console.print(f"[red]오류:[/red] 등록되지 않은 Provider: {provider}")
            raise typer.Exit(1)
        config.default_ai_provider = provider
        changed = True

    if changed:
        save_config(config)
        console.print("[bold green]✓ 기본값이 업데이트되었습니다.[/bold green]")
    else:
        console.print("[yellow]변경할 항목을 --format, --lang, --provider 옵션으로 지정하세요.[/yellow]")
