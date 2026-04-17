"""DevFolio CLI 진입점 — 전역 오류 핸들러 포함.

[Spring 비교]
  Spring Shell @ShellApplication 또는 Picocli @Command 의 진입점 역할.
  typer.Typer() 로 CLI 앱을 만들고, 서브 커맨드를 add_typer() 로 등록하는 구조는
  Spring MVC 의 DispatcherServlet + @RequestMapping 등록과 유사하다.
"""

# sys : Python 표준 라이브러리. sys.exit() 로 프로세스 종료.
# [Spring] System.exit(code) 와 동일.
import sys

# typer : Click 기반 CLI 프레임워크. 타입 힌트로 CLI 옵션/인수를 선언한다.
# [Spring] Spring Shell @ShellComponent + @ShellMethod, 또는 Picocli @Command.
import typer

# rich.console.Console : ANSI 컬러 출력 라이브러리. 터미널에 색상/스타일 텍스트 출력.
# rich.panel.Panel   : 박스 테두리를 그려주는 컴포넌트.
from rich.console import Console
from rich.panel import Panel

# 각 서브 커맨드 모듈을 임포트. [Spring] @ComponentScan 으로 Controller 를 찾는 것과 유사.
from devfolio.commands import ai, config, data, export, project, scan, sync, task
from devfolio.commands.init_cmd import run_init
from devfolio.commands import serve as serve_cmd
from devfolio.exceptions import DevfolioError

# i18n : 다국어(ko/en) 문자열 카탈로그. DEVFOLIO_LANG 환경변수로 제어.
from devfolio.i18n import init_from_config

# typer.Typer() : CLI 앱 객체 생성. [Spring] @SpringBootApplication + SpringApplication.run().
# add_completion=False : 자동완성 기능 비활성화 (간결한 --help 출력을 위해).
# rich_markup_mode="rich" : help 텍스트에서 [bold cyan] 같은 Rich 마크업 허용.
# pretty_exceptions_enable=False : Typer 기본 예외 포맷터를 비활성화하고
#   아래 cli() 의 전역 핸들러로 처리하기 위해 꺼둔다.
app = typer.Typer(
    name="devfolio",
    help="[bold cyan]DevFolio[/bold cyan] — 개발자 포트폴리오 & 경력기술서 자동화 시스템",
    add_completion=False,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
)

# Console(stderr=True) : 표준 에러(stderr)로 출력하는 콘솔 인스턴스.
# 오류 메시지를 stderr 에 보내면 파이프라인에서 stdout 과 섞이지 않는다.
# [Spring] log.error() 가 STDERR 에 쓰는 것과 같은 목적.
console = Console(stderr=True)

# ---------------------------------------------------------------------------
# 서브 커맨드 등록
# ---------------------------------------------------------------------------
# app.add_typer(sub_app, name="명령어") : 서브 커맨드를 등록.
# [Spring] @CommandLine.Command(subcommands={SubCmd.class}) 또는
#   @ShellComponent 로 별도 파일에서 커맨드를 분리하는 패턴과 동일.
app.add_typer(project.app, name="project", help="프로젝트 CRUD")
app.add_typer(task.app, name="task", help="작업 내역 CRUD")
app.add_typer(config.app, name="config", help="설정 관리 (AI Provider 등)")
app.add_typer(ai.app, name="ai", help="AI 문서 생성 / JD 매칭 / 문구 개선")
app.add_typer(export.app, name="export", help="Markdown / PDF / DOCX / HTML 내보내기")
app.add_typer(data.app, name="data", help="백업 / 복원 / 고급 YAML·JSON 가져오기")
app.add_typer(sync.app, name="sync", help="GitHub 백업 동기화")
app.add_typer(scan.app, name="scan", help="Git 저장소 스캔 → 포트폴리오 자동 생성")
app.add_typer(serve_cmd.app, name="serve", help="웹 기반 Portfolio Studio 시작")


# @app.command("init") : "devfolio init" 커맨드를 이 함수에 연결.
# [Spring] @ShellMethod(key="init") 또는 @Command(name="init") 과 동일.
@app.command("init")
def init(
    # typer.Option(...) : CLI 옵션 선언. "--force" 또는 "-f" 플래그.
    # [Spring] @Option(names={"--force", "-f"}) 와 동일.
    force: bool = typer.Option(False, "--force", "-f", help="이미 초기화된 경우에도 재설정"),
):
    """DevFolio 최초 설정 (대화형)."""
    run_init(force=force)


# @app.callback(invoke_without_command=True)
#   서브 커맨드 없이 `devfolio` 만 입력했을 때 이 함수가 실행됨.
#   [Spring] 기본 핸들러 — 매핑 없는 요청 시 도움말 출력.
# ctx: typer.Context : 현재 CLI 실행 컨텍스트. 어떤 서브 커맨드가 호출됐는지 알 수 있다.
@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """DevFolio — 개발자 포트폴리오 & 경력기술서 자동화 시스템"""
    # ctx.invoked_subcommand : 서브 커맨드가 있으면 그 이름, 없으면 None.
    if ctx.invoked_subcommand is None:
        console_out = Console()
        # ctx.get_help() : --help 와 동일한 도움말 문자열 반환.
        console_out.print(ctx.get_help())


def cli():
    """CLI 진입점 — 전역 DevfolioError 처리.

    [Spring 비교]
      SpringApplication.run() + @ControllerAdvice(전역 예외 핸들러)를 합친 역할.
      pyproject.toml 의 [project.scripts] devfolio = "devfolio.main:cli" 로 연결되어
      설치 후 `devfolio` 명령으로 호출된다.
    """
    # config가 있으면 언어 설정을 i18n에 반영.
    # 함수 안에서 import 하는 이유(lazy import):
    #   최초 실행 시 config 파일이 없을 수 있고, 이때 모듈 레벨 import 면 예외가 터질 수 있다.
    #   함수 안으로 넣으면 실제로 필요할 때만 로드되어 안전하다.
    try:
        from devfolio.core.storage import is_initialized, load_config
        if is_initialized():
            cfg = load_config()
            init_from_config(cfg.default_language)
    except Exception:
        # config 없어도 기본 로케일(ko)로 계속 진행. 예외를 무시.
        pass

    try:
        # app() : Typer 앱 실행. sys.argv 를 파싱해 해당 커맨드 함수를 호출.
        app()
    except DevfolioError as e:
        # DevfolioError 를 잡아 사용자 친화적인 메시지로 출력.
        # [Spring] @ExceptionHandler(DevfolioError.class) 와 동일한 역할.
        # [bold red] : Rich 마크업으로 빨간색 굵은 텍스트 출력.
        console.print(f"\n[bold red]오류:[/bold red] {e.message}")
        if e.hint:
            # [dim] : 흐린(회색) 텍스트.
            console.print(f"  [dim]→ {e.hint}[/dim]\n")
        # sys.exit(1) : 비정상 종료 코드 1 로 프로세스 종료.
        # [Spring] System.exit(1) 과 동일. CI/CD 에서 실패로 감지됨.
        sys.exit(1)
    except KeyboardInterrupt:
        # Ctrl+C 를 눌렀을 때 발생하는 예외. [Spring] Thread.interrupt() 대응.
        console.print("\n[yellow]취소되었습니다.[/yellow]")
        sys.exit(0)


# if __name__ == "__main__": : 이 파일을 직접 실행할 때만 cli() 호출.
# `python -m devfolio.main` 으로 실행하면 이 블록이 동작한다.
# 패키지로 설치된 경우 pyproject.toml 의 scripts 에서 cli() 를 직접 호출하므로 이 블록은 실행되지 않음.
# [Spring] public static void main(String[] args) 와 동일한 역할.
if __name__ == "__main__":
    cli()
