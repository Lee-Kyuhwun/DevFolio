"""devfolio data * — 데이터 백업/복원 커맨드."""

import json
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.prompt import Confirm
from ruamel.yaml import YAML

from devfolio.commands.common import check_init
from devfolio.core.project_manager import ProjectManager
from devfolio.core.storage import backup, restore, save_project
from devfolio.core.storage import project_id_from_name
from devfolio.exceptions import DevfolioError
from devfolio.models.project import Project

app = typer.Typer(help="데이터 백업 및 복원", rich_markup_mode="rich")
console = Console()
pm = ProjectManager()
yaml = YAML(typ="safe")


def _load_import_payload(file_path: Path) -> Any:
    suffix = file_path.suffix.lower()
    raw = file_path.read_text(encoding="utf-8")

    if suffix == ".json":
        return json.loads(raw)
    if suffix in {".yaml", ".yml"}:
        return yaml.load(raw)

    try:
        return yaml.load(raw)
    except Exception:
        return json.loads(raw)


def _normalize_project_payload(item: dict, existing_name: Optional[str] = None) -> dict:
    normalized = dict(item)
    if "id" not in normalized and "name" in normalized:
        normalized["id"] = project_id_from_name(existing_name or normalized["name"])
    return normalized


@app.command("backup")
def backup_cmd(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="백업 파일 경로 (기본: ~/devfolio_backup_YYYYMMDD.zip)"
    ),
):
    """DevFolio 데이터 전체를 ZIP으로 백업."""
    check_init()

    if not output:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = Path.home() / f"devfolio_backup_{date_str}.zip"

    with console.status("[cyan]백업 중...[/cyan]"):
        backup(output)

    console.print(f"[bold green]✓ 백업 완료:[/bold green] {output}")


@app.command("restore")
def restore_cmd(
    backup_path: Path = typer.Argument(..., help="복원할 백업 ZIP 파일 경로"),
    yes: bool = typer.Option(False, "--yes", "-y", help="확인 프롬프트 건너뜀"),
):
    """백업 ZIP에서 데이터 복원."""
    if not backup_path.exists():
        raise DevfolioError(
            f"복원할 백업 파일을 찾을 수 없습니다: {backup_path}",
            hint="`devfolio data backup`으로 생성한 ZIP 경로를 다시 확인하세요.",
        )

    if not yes:
        if not Confirm.ask(
            "[yellow]⚠ 기존 데이터가 덮어씌워집니다.[/yellow] 계속하시겠습니까?"
        ):
            console.print("[yellow]취소되었습니다.[/yellow]")
            return

    with console.status("[cyan]복원 중...[/cyan]"):
        restore(backup_path)

    console.print(f"[bold green]✓ 복원 완료[/bold green] (출처: {backup_path})")


@app.command("import")
def import_data(
    file: Path = typer.Argument(..., help="가져올 YAML/JSON 파일 경로"),
    yes: bool = typer.Option(False, "--yes", "-y", help="중복 확인 건너뜀"),
):
    """YAML 또는 JSON 형식으로 프로젝트 일괄 가져오기.

    예시 형식:
    [{"name": "...", "type": "company", "period": {"start": "2024-01"}, ...}]
    """
    check_init()

    if not file.exists():
        raise DevfolioError(
            f"가져올 파일을 찾을 수 없습니다: {file}",
            hint="경로를 다시 확인하거나 `examples/connected_car_gateway.yaml` 예시를 참고하세요.",
        )

    try:
        data = _load_import_payload(file)
    except Exception as e:
        raise DevfolioError(
            f"가져올 파일을 파싱할 수 없습니다: {file}",
            hint="YAML 또는 JSON 형식이 올바른지 확인하세요.",
        ) from e

    if not isinstance(data, list):
        data = [data]

    imported = 0
    skipped = 0

    for item in data:
        if not isinstance(item, dict) or "name" not in item:
            console.print(f"[yellow]⚠ 건너뜀 (형식 오류):[/yellow] {item}")
            skipped += 1
            continue

        existing = pm.get_project(item["name"])
        if existing and not yes:
            if not Confirm.ask(
                f"  [yellow]'{item['name']}'[/yellow] 이미 존재합니다. 덮어쓰시겠습니까?",
                default=False,
            ):
                skipped += 1
                continue

        try:
            payload = _normalize_project_payload(item, existing.name if existing else None)
            if existing and yes:
                payload["id"] = existing.id
            project = Project.model_validate(payload)
            save_project(project)
            imported += 1
            console.print(f"  [green]✓[/green] {project.name}")
        except Exception as e:
            console.print(f"  [red]✗[/red] {item.get('name', '?')}: {e}")
            skipped += 1

    console.print(
        f"\n[bold green]✓ 가져오기 완료[/bold green] "
        f"(성공: {imported}, 건너뜀: {skipped})"
    )


@app.command("export-json")
def export_json(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="출력 파일 경로"),
):
    """모든 프로젝트를 JSON으로 내보내기."""
    check_init()

    from devfolio.core.storage import list_projects as _list_projects
    projects = _list_projects()

    if not projects:
        console.print("[yellow]등록된 프로젝트가 없습니다.[/yellow]")
        return

    data = [p.model_dump() for p in projects]
    content = json.dumps(data, ensure_ascii=False, indent=2)

    if output:
        output.write_text(content, encoding="utf-8")
        result_path = output
    else:
        from devfolio.core.storage import EXPORTS_DIR
        result_path = EXPORTS_DIR / "projects.json"
        result_path.write_text(content, encoding="utf-8")

    console.print(
        f"[bold green]✓ JSON 내보내기 완료:[/bold green] {result_path} "
        f"[dim]({len(projects)}개 프로젝트)[/dim]"
    )
