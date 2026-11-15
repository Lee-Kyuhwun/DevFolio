"""DevFolio → 성과노트 데이터 마이그레이션.

- 원본은 읽기만 한다(삭제·수정 없음).
- 실행 전 기존 데이터를 ZIP 으로 백업한다.
- 같은 원본을 다시 가져오지 않도록 `source_ref` 로 중복을 막는다(재실행 가능).
- 변환 근거가 부족한 항목은 `검토 필요(needs_review)` 로 남긴다.
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from impactnote.core.service import ImpactService
from impactnote.core.store import (
    JsonStore,
    legacy_config_dir,
    legacy_data_dir,
)

STATE_FILE = "migration.json"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _legacy_projects() -> list[dict]:
    """레거시 프로젝트 YAML 을 dict 로 읽는다.

    `IMPACTNOTE_LEGACY_DATA_DIR`(Docker 의 읽기 전용 마운트 등)을 우선 사용하고,
    그 경로에 파일이 없을 때만 devfolio 기본 저장소(platformdirs/`~/.devfolio`)로 폴백한다.
    """
    projects: list[dict] = []
    seen: set[str] = set()
    root = legacy_data_dir() / "projects"
    if root.exists():
        try:
            from ruamel.yaml import YAML

            from devfolio.models.project import Project
        except Exception:
            YAML = None  # type: ignore[assignment,misc]
        if YAML is not None:
            parser = YAML(typ="safe")
            for path in sorted(root.glob("*.y*ml")):
                try:
                    data = parser.load(path.read_text(encoding="utf-8")) or {}
                    project = Project.model_validate(data).model_dump(mode="json")
                except Exception:  # noqa: BLE001 — 읽을 수 없는 파일은 건너뛴다
                    continue
                project_id = str(project.get("id", ""))
                if not project_id or project_id in seen:
                    continue
                seen.add(project_id)
                projects.append(project)
    if projects:
        return projects

    try:
        from devfolio.core.storage import list_projects
    except Exception:
        return []
    return [project.model_dump(mode="json") for project in list_projects()]


def legacy_available() -> bool:
    return bool(_legacy_projects())


def _backup(store: JsonStore) -> Optional[Path]:
    sources = [legacy_data_dir(), legacy_config_dir()]
    existing = [path for path in sources if path.exists()]
    if not existing:
        return None
    backup_dir = store.directory / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"devfolio-backup-{stamp}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for base in existing:
            label = "config" if base == legacy_config_dir() else "data"
            for path in sorted(base.rglob("*")):
                if path.is_file():
                    archive.write(path, f"{label}/{path.relative_to(base).as_posix()}")
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def _fingerprint(projects: list[dict]) -> str:
    ids = sorted(str(project.get("id", "")) for project in projects)
    return f"{len(ids)}:{','.join(ids)}"


def _month_date(value: Optional[str]) -> str:
    if value and len(str(value)) >= 7:
        return f"{str(value)[:7]}-01"
    return datetime.now(timezone.utc).date().isoformat()


def run_migration(
    service: Optional[ImpactService] = None,
    *,
    store: Optional[JsonStore] = None,
    force: bool = False,
) -> dict:
    """레거시 프로젝트/작업을 업무 기록·성과로 변환한다."""
    from impactnote.core.service import ImpactService as _Service

    service = service or _Service(store or JsonStore())
    store_instance = service.store
    projects = _legacy_projects()
    if not projects:
        return {
            "status": "no_source",
            "migrated_activities": 0,
            "migrated_achievements": 0,
            "skipped": 0,
            "backup": None,
            "message": "이전할 DevFolio 데이터가 없습니다.",
        }

    fingerprint = _fingerprint(projects)
    state = _read_json(store_instance.directory / STATE_FILE)
    if not force and state.get("fingerprint") == fingerprint:
        return {
            "status": "already_migrated",
            "migrated_activities": 0,
            "migrated_achievements": 0,
            "skipped": 0,
            "backup": state.get("backup"),
            "message": "이미 같은 데이터를 이전했습니다.",
        }

    backup = _backup(store_instance)
    existing_refs = {
        item.source_ref for item in service.activities() if item.source_ref
    }
    created_activities = 0
    created_achievements = 0
    skipped = 0

    for project in projects:
        project_id = str(project.get("id") or project.get("name") or "project")
        name = str(project.get("name") or project_id)
        period = project.get("period") or {}
        date = _month_date(period.get("start"))
        base_ref = f"devfolio:{project_id}"
        overview = project.get("overview") or {}
        tasks = project.get("tasks") or []

        if tasks:
            for index, task in enumerate(tasks):
                ref = f"{base_ref}:task:{task.get('id') or index}"
                if ref in existing_refs:
                    skipped += 1
                    continue
                task_period = task.get("period") or {}
                activity = service.create_activity(
                    {
                        "title": str(task.get("name") or "업무")[:200],
                        "description": str(task.get("solution") or "")[:4000],
                        "date": _month_date(
                            task_period.get("start") or period.get("start")
                        ),
                        "period_end": None,
                        "project": name,
                        "activity_type": "general",
                        "problem": str(task.get("problem") or "")[:2000],
                        "action": str(task.get("solution") or "")[:2000],
                        "status": "done",
                        "tags": [str(item) for item in (task.get("tech_used") or [])][
                            :10
                        ],
                        "source": "migration",
                        "source_ref": ref,
                    }
                )
                created_activities += 1
                result = str(task.get("result") or "").strip()
                if result:
                    service.create_achievement(
                        {
                            "title": f"{name}: {task.get('name')}"[:200],
                            "activity_ids": [activity.id],
                            "problem": str(task.get("problem") or "")[:3000],
                            "action": str(task.get("solution") or "")[:3000],
                            "result": result[:3000],
                            "status": "user_input",
                            "period_start": activity.date,
                            "period_end": activity.date,
                            "source": "migration",
                        }
                    )
                    created_achievements += 1
                existing_refs.add(ref)
        else:
            ref = f"{base_ref}:project"
            if ref in existing_refs:
                skipped += 1
                continue
            activity = service.create_activity(
                {
                    "title": name[:200],
                    "description": str(
                        project.get("one_line_summary") or project.get("summary") or ""
                    )[:4000],
                    "date": date,
                    "project": name,
                    "activity_type": "general",
                    "problem": str(overview.get("problem") or "")[:2000],
                    "status": "done",
                    "tags": [str(item) for item in (project.get("tech_stack") or [])][
                        :10
                    ],
                    "source": "migration",
                    "source_ref": ref,
                }
            )
            created_activities += 1
            repo_url = str(project.get("repo_url") or "")
            if repo_url:
                evidence = service.create_evidence(
                    {
                        "type": "url",
                        "title": f"{name} 저장소",
                        "reference": repo_url,
                        "description": "DevFolio 프로젝트에서 이전된 링크",
                        "verified": False,
                    }
                )
                activity.evidence_ids = [evidence.id]
                store_instance.put("activities", activity)
            if not project.get("one_line_summary") and not overview.get("problem"):
                service.create_achievement(
                    {
                        "title": f"{name} (검토 필요)"[:200],
                        "activity_ids": [activity.id],
                        "action": activity.description,
                        "status": "needs_review",
                        "needs_review": True,
                        "source": "migration",
                    }
                )
                created_achievements += 1
            existing_refs.add(ref)

    # 작성자 정보는 비어 있을 때만 옮긴다(사용자가 새로 입력한 값을 덮지 않음).
    settings = service.settings()
    if not settings.user_name:
        try:
            from devfolio.core.storage import load_config

            legacy_user = load_config().user
            if legacy_user.name:
                service.save_settings({"user_name": legacy_user.name})
        except Exception:  # noqa: BLE001 — 레거시 설정을 못 읽어도 이전은 계속한다
            pass

    summary = {
        "status": "migrated",
        "migrated_activities": created_activities,
        "migrated_achievements": created_achievements,
        "skipped": skipped,
        "backup": str(backup) if backup else None,
        "fingerprint": fingerprint,
        "message": "DevFolio 데이터를 성과노트로 이전했습니다. 검토 필요 항목을 확인하세요.",
    }
    (store_instance.directory / STATE_FILE).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


__all__ = ["legacy_available", "run_migration"]
