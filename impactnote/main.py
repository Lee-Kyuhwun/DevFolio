"""성과노트 CLI.

웹 UI 가 주 진입점이고, CLI 는 기록·이전·보고서 생성을 자동화할 때 쓴다.
기존 `devfolio` 명령은 호환을 위해 그대로 남아 있다(레거시 앱).
"""

from __future__ import annotations

import multiprocessing
import os
from typing import Optional

import typer

from impactnote import APP_NAME, APP_NAME_EN, __version__
from impactnote.core.service import ImpactService, NotFound

app = typer.Typer(
    help=f"{APP_NAME}({APP_NAME_EN}) — 근거 기반 업무 성과 기록·보고 도구",
    no_args_is_help=True,
)
activity_app = typer.Typer(help="업무 기록 추가·조회")
achievement_app = typer.Typer(help="성과 조회·생성")
report_app = typer.Typer(help="제출용 보고서 생성")
app.add_typer(activity_app, name="activity")
app.add_typer(achievement_app, name="achievement")
app.add_typer(report_app, name="report")


def _service() -> ImpactService:
    return ImpactService()


@app.command()
def version() -> None:
    """버전을 출력한다."""
    typer.echo(f"{APP_NAME} ({APP_NAME_EN}) {__version__}")


@app.command("init")
def init_cmd() -> None:
    """데이터 디렉터리를 만들고 DevFolio 데이터가 있으면 이전을 안내한다."""
    from impactnote.core.migrate import legacy_available
    from impactnote.core.store import data_dir, get_store

    store = get_store()
    store.ensure_dirs()
    typer.echo(f"데이터 위치: {data_dir()}")
    if legacy_available():
        typer.echo(
            "DevFolio 데이터가 있습니다. `impactnote migrate` 로 이전할 수 있습니다."
        )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="바인딩 주소"),
    port: int = typer.Option(8000, help="포트"),
    reload: bool = typer.Option(False, "--reload", help="코드 변경 자동 반영"),
) -> None:
    """성과노트 웹 UI 를 실행한다."""
    import uvicorn

    from impactnote.web.app import create_app

    if reload:
        uvicorn.run(
            "impactnote.web.app:create_app",
            host=host,
            port=port,
            log_level="warning",
            reload=True,
            reload_dirs=[os.path.dirname(os.path.dirname(__file__))],
            factory=True,
        )
    else:
        uvicorn.run(create_app(), host=host, port=port, log_level="warning")


@app.command()
def migrate(
    force: bool = typer.Option(False, help="이미 이전했어도 다시 실행"),
) -> None:
    """DevFolio 프로젝트·작업을 업무 기록·성과로 이전한다(원본은 그대로)."""
    from impactnote.core.migrate import run_migration

    summary = run_migration(_service(), force=force)
    typer.echo(summary.get("message", ""))
    if summary.get("backup"):
        typer.echo(f"백업: {summary['backup']}")
    typer.echo(
        f"업무 기록 {summary.get('migrated_activities', 0)}건 / "
        f"성과 {summary.get('migrated_achievements', 0)}건 / "
        f"건너뜀 {summary.get('skipped', 0)}건"
    )


@activity_app.command("add")
def activity_add(
    title: str = typer.Argument(..., help="업무 제목"),
    description: str = typer.Option("", "--desc", help="수행 내용"),
    date: str = typer.Option("", "--date", help="수행일 YYYY-MM-DD"),
    project: str = typer.Option("", "--project", help="프로젝트/업무 영역"),
    activity_type: str = typer.Option("general", "--type", help="업무 유형"),
    problem: str = typer.Option("", "--problem", help="문제/요구사항"),
    action: str = typer.Option("", "--action", help="본인이 한 행동"),
    result: str = typer.Option("", "--result", help="정량/정성 결과(기록에 있을 때만)"),
    status: str = typer.Option("done", "--status", help="planned|in_progress|done"),
) -> None:
    """업무 기록을 한 줄로 추가한다."""
    payload: dict = {
        "title": title,
        "description": description,
        "project": project,
        "activity_type": activity_type,
        "problem": problem,
        "action": action,
        "result": result,
        "status": status,
    }
    if date:
        payload["date"] = date
    activity = _service().create_activity(payload)
    typer.echo(f"기록 완료: {activity.title} ({activity.date}) id={activity.id}")


@activity_app.command("list")
def activity_list(limit: int = typer.Option(20, help="최대 개수")) -> None:
    """최근 업무 기록을 출력한다."""
    items = _service().activities()[:limit]
    if not items:
        typer.echo("업무 기록이 없습니다.")
        return
    for item in items:
        typer.echo(f"{item.date}  {item.title}  [{item.status}]  {item.id}")


@achievement_app.command("list")
def achievement_list(
    status: Optional[str] = typer.Option(None, help="상태 필터"),
) -> None:
    """성과 목록을 출력한다."""
    items = _service().achievements()
    if status:
        items = [item for item in items if item.status == status]
    if not items:
        typer.echo("성과가 없습니다.")
        return
    for item in items:
        typer.echo(
            f"[{item.status}] {item.title}  ({len(item.evidence_ids)}개 근거)  {item.id}"
        )


@achievement_app.command("from-activity")
def achievement_from_activity(
    activity_id: str = typer.Argument(..., help="업무 기록 ID"),
    title: str = typer.Option("", "--title", help="성과 제목"),
) -> None:
    """업무 기록 1건을 성과로 만든다."""
    try:
        achievement = _service().create_achievement_from_activities(
            [activity_id], title=title
        )
    except NotFound as exc:
        typer.echo(f"실패: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"성과 생성: {achievement.title} ({achievement.status}) id={achievement.id}"
    )


@report_app.command("generate")
def report_generate(
    template: str = typer.Option(
        "monthly", "--template", help="weekly|monthly|quarterly|annual|custom"
    ),
    period: str = typer.Option(
        "month", "--period", help="week|month|quarter|half|year|custom"
    ),
    reference: str = typer.Option("", "--reference", help="기준일 YYYY-MM-DD"),
    start: str = typer.Option("", "--start", help="사용자 지정 시작일"),
    end: str = typer.Option("", "--end", help="사용자 지정 종료일"),
    title: str = typer.Option("", "--title", help="보고서 제목"),
    form: str = typer.Option("md", "--format", help="md|docx|pdf|txt|csv"),
) -> None:
    """선택한 기간·템플릿으로 제출용 보고서를 만든다."""
    from impactnote.core.report import create_report

    try:
        report = create_report(
            _service(),
            template=template,
            period_kind=period,
            reference=reference or None,
            start=start or None,
            end=end or None,
            title=title,
            fmt=form,
        )
    except Exception as exc:  # noqa: BLE001 — CLI 는 메시지로 안내
        typer.echo(f"보고서 생성 실패: {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"{report.title} (v{report.version})")
    typer.echo(f"파일: {report.file_name or '(본문만 저장됨)'}")
    typer.echo(
        f"포함 성과 {len(report.achievement_ids)}건 / 업무 {len(report.activity_ids)}건"
    )


@report_app.command("list")
def report_list() -> None:
    """생성한 보고서 이력을 출력한다."""
    items = _service().reports()
    if not items:
        typer.echo("보고서 이력이 없습니다.")
        return
    for item in items:
        typer.echo(
            f"{item.created_at[:10]}  {item.title}  v{item.version}  [{item.status}]  {item.file_name}"
        )


def cli() -> None:
    app()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    cli()
