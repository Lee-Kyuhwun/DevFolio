"""devfolio init — 최초 설정 흐름."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from devfolio.core.storage import get_config_path, is_initialized, save_config
from devfolio.core.sync_service import SyncService
from devfolio.models.config import AIProviderConfig, Config, SyncConfig, UserConfig
from devfolio.utils.security import store_api_key

console = Console()

_BANNER = """
  ██████╗ ███████╗██╗   ██╗███████╗ ██████╗ ██╗     ██╗ ██████╗
  ██╔══██╗██╔════╝██║   ██║██╔════╝██╔═══██╗██║     ██║██╔═══██╗
  ██║  ██║█████╗  ██║   ██║█████╗  ██║   ██║██║     ██║██║   ██║
  ██║  ██║██╔══╝  ╚██╗ ██╔╝██╔══╝  ██║   ██║██║     ██║██║   ██║
  ██████╔╝███████╗ ╚████╔╝ ██║     ╚██████╔╝███████╗██║╚██████╔╝
  ╚═════╝ ╚══════╝  ╚═══╝  ╚═╝      ╚═════╝ ╚══════╝╚═╝ ╚═════╝
"""

_PROVIDER_MODELS: dict[str, list[str]] = {
    "anthropic": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-haiku-4-5-20251001"],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    "gemini": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"],
    "ollama": ["llama3.2", "llama3.1", "mistral", "deepseek-coder"],
}


def run_init(force: bool = False) -> None:
    """대화형 초기 설정."""
    console.print(Panel(_BANNER, style="bold blue", border_style="blue"))
    console.print("  [bold cyan]개발자 포트폴리오 & 경력기술서 자동화 도구[/bold cyan]\n")

    if is_initialized() and not force:
        if not Confirm.ask("이미 초기화되어 있습니다. 다시 설정하시겠습니까?"):
            console.print("[yellow]취소되었습니다.[/yellow]")
            raise typer.Exit()

    config = Config()

    # 사용자 정보
    console.print("\n[bold]── 사용자 정보 ──[/bold]")
    config.user = UserConfig(
        name=Prompt.ask("이름을 입력하세요"),
        email=Prompt.ask("이메일을 입력하세요", default=""),
        github=Prompt.ask("GitHub URL [dim](선택)[/dim]", default=""),
        blog=Prompt.ask("블로그 URL [dim](선택)[/dim]", default=""),
    )

    # AI 설정
    console.print("\n[bold]── AI 설정 ──[/bold]")
    use_ai = Confirm.ask("AI 기능을 사용하시겠습니까?", default=False)

    if use_ai:
        provider_name = _select_provider()
        if provider_name and provider_name != "skip":
            _configure_provider(config, provider_name)

    # GitHub sync 설정
    console.print("\n[bold]── GitHub 백업 설정 ──[/bold]")
    if Confirm.ask("GitHub 저장소로 원본 데이터와 산출물을 백업하시겠습니까?", default=False):
        _configure_sync(config)

    save_config(config)
    config_path = get_config_path()
    console.print(
        f"\n[bold green]✓ 설정이 완료되었습니다![/bold green] "
        f"[dim]{config_path or '(경로 확인 불가)'} 에 저장되었습니다.[/dim]\n"
    )
    console.print("  추천 시작 경로: [bold]devfolio serve[/bold]")
    console.print("  CLI로 바로 입력하려면: [bold]devfolio project add[/bold]")
    if config.sync.enabled:
        console.print("  백업하려면: [bold]devfolio sync run[/bold]")


def _select_provider() -> str:
    choices = {
        "1": "anthropic",
        "2": "openai",
        "3": "gemini",
        "4": "ollama",
        "5": "skip",
    }
    console.print("\nAI Provider를 선택하세요:")
    console.print("  [bold]1[/bold]  Anthropic (Claude)")
    console.print("  [bold]2[/bold]  OpenAI (GPT)")
    console.print("  [bold]3[/bold]  Google (Gemini)")
    console.print("  [bold]4[/bold]  Ollama (로컬 실행)")
    console.print("  [bold]5[/bold]  나중에 설정")

    choice = Prompt.ask("번호 선택", choices=list(choices.keys()), default="5")
    return choices[choice]


def _configure_provider(config: Config, provider_name: str) -> None:
    models = _PROVIDER_MODELS.get(provider_name, [])

    if models:
        console.print(f"\n모델을 선택하세요 [{provider_name}]:")
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

    provider = AIProviderConfig(name=provider_name, model=model, key_stored=False)

    if provider_name == "ollama":
        base_url = Prompt.ask("Ollama 서버 URL", default="http://localhost:11434")
        provider.base_url = base_url
    else:
        api_key = Prompt.ask(f"{provider_name} API 키를 입력하세요", password=True)
        if api_key:
            ok = store_api_key(provider_name, api_key)
            provider.key_stored = ok
            if not ok:
                console.print(
                    "[yellow]⚠ 키체인 저장에 실패했습니다. "
                    "환경 변수로 API 키를 관리해주세요.[/yellow]"
                )

    config.upsert_provider(provider)
    config.default_ai_provider = provider_name


def _configure_sync(config: Config) -> None:
    repo_input = Prompt.ask("GitHub 저장소 URL 또는 owner/repo")
    branch = Prompt.ask("동기화 브랜치", default=config.sync.branch or "main")

    config.sync = SyncConfig(
        enabled=True,
        repo_url=SyncService.normalize_repo_url(repo_input),
        branch=branch.strip() or "main",
    )
