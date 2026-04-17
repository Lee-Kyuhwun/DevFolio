"""로컬 파일 기반 저장소 (platformdirs + ruamel.yaml)."""

import json
import re
import zipfile
from pathlib import Path
from typing import Any, Optional

from platformdirs import user_config_dir, user_data_dir
from pydantic import ValidationError
from ruamel.yaml import YAML

from devfolio.exceptions import DevfolioYAMLError
from devfolio.log import get_logger
from devfolio.models.config import Config
from devfolio.models.project import Project

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 경로 설정 (platformdirs 기반 크로스플랫폼)
# ---------------------------------------------------------------------------

_APP_NAME = "devfolio"
_APP_AUTHOR = "devfolio"

DEVFOLIO_CONFIG_DIR = Path(user_config_dir(_APP_NAME, _APP_AUTHOR))
DEVFOLIO_DATA_DIR = Path(user_data_dir(_APP_NAME, _APP_AUTHOR))

CONFIG_FILE = DEVFOLIO_CONFIG_DIR / "config.yaml"
PROJECTS_DIR = DEVFOLIO_DATA_DIR / "projects"
EXPORTS_DIR = DEVFOLIO_DATA_DIR / "exports"
TEMPLATES_DIR = DEVFOLIO_DATA_DIR / "templates"
SYNC_REPO_DIR = DEVFOLIO_DATA_DIR / "sync_repo"
SYNC_STATE_FILE = DEVFOLIO_DATA_DIR / "sync_state.json"

# 레거시 경로 호환 (기존 ~/.devfolio/ 사용 시)
_LEGACY_HOME = Path.home() / ".devfolio"
_LEGACY_CONFIG = _LEGACY_HOME / "config.yaml"

_yaml = YAML()
_yaml.default_flow_style = False
_yaml.preserve_quotes = True
_yaml.width = 4096


# ---------------------------------------------------------------------------
# 디렉터리 초기화
# ---------------------------------------------------------------------------

def ensure_dirs() -> None:
    DEVFOLIO_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DEVFOLIO_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def is_initialized() -> bool:
    return CONFIG_FILE.exists() or _LEGACY_CONFIG.exists()


def _resolve_config_path() -> Path:
    """레거시 경로 자동 감지."""
    if _LEGACY_CONFIG.exists() and not CONFIG_FILE.exists():
        return _LEGACY_CONFIG
    return CONFIG_FILE


def get_config_path() -> Optional[Path]:
    """현재 사용 중인 설정 파일 경로."""
    path = _resolve_config_path()
    return path if path.exists() else None


# ---------------------------------------------------------------------------
# 설정 저장/로드
# ---------------------------------------------------------------------------

def load_config() -> Config:
    path = _resolve_config_path()
    if not path.exists():
        return Config()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _yaml.load(f) or {}
        return Config.model_validate(data)
    except ValidationError as e:
        raise DevfolioYAMLError(str(path), str(e)) from e
    except Exception as e:
        raise DevfolioYAMLError(str(path), str(e)) from e


def save_config(config: Config) -> None:
    ensure_dirs()
    path = _resolve_config_path()
    with open(path, "w", encoding="utf-8") as f:
        _yaml.dump(config.model_dump(exclude_none=False), f)
    # 설정 파일 권한을 소유자만 읽도록 제한 (API 키 보호)
    path.chmod(0o600)


# ---------------------------------------------------------------------------
# 프로젝트 ID 변환
# ---------------------------------------------------------------------------

def project_id_from_name(name: str) -> str:
    """프로젝트명 → 파일 안전한 ID."""
    safe = re.sub(r"[^\w\s-]", "", name.lower())
    safe = re.sub(r"[\s-]+", "_", safe)
    return safe.strip("_") or "project"


# ---------------------------------------------------------------------------
# 프로젝트 CRUD
# ---------------------------------------------------------------------------

def load_project(project_id: str) -> Optional[Project]:
    path = PROJECTS_DIR / f"{project_id}.yaml"
    # 레거시 경로 폴백
    if not path.exists():
        legacy = _LEGACY_HOME / "projects" / f"{project_id}.yaml"
        if legacy.exists():
            path = legacy
        else:
            return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _yaml.load(f) or {}
        return Project.model_validate(data)
    except ValidationError as e:
        raise DevfolioYAMLError(str(path), str(e)) from e
    except Exception as e:
        raise DevfolioYAMLError(str(path), str(e)) from e


def save_project(project: Project) -> None:
    ensure_dirs()
    path = PROJECTS_DIR / f"{project.id}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        _yaml.dump(project.model_dump(exclude_none=False), f)


def delete_project_file(project_id: str) -> bool:
    path = PROJECTS_DIR / f"{project_id}.yaml"
    if not path.exists():
        # 레거시 경로 확인
        legacy = _LEGACY_HOME / "projects" / f"{project_id}.yaml"
        if legacy.exists():
            legacy.unlink()
            return True
        return False
    path.unlink()
    return True


def list_projects() -> list[Project]:
    projects: list[Project] = []
    search_dirs = [PROJECTS_DIR]
    # 레거시 경로 추가 (중복 방지)
    legacy_projects = _LEGACY_HOME / "projects"
    if legacy_projects.exists() and legacy_projects != PROJECTS_DIR:
        search_dirs.append(legacy_projects)

    seen_ids: set[str] = set()
    for directory in search_dirs:
        for yaml_file in sorted(directory.glob("*.yaml")):
            project_id = yaml_file.stem
            if project_id in seen_ids:
                continue
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = _yaml.load(f) or {}
                projects.append(Project.model_validate(data))
                seen_ids.add(project_id)
            except Exception as e:
                logger.warning("손상된 프로젝트 파일 건너뜀: %s (%s)", yaml_file, e)
                continue
    return projects


def get_project_file_paths() -> list[Path]:
    """실제 저장된 프로젝트 YAML 파일 목록."""
    search_dirs = [PROJECTS_DIR]
    legacy_projects = _LEGACY_HOME / "projects"
    if legacy_projects.exists() and legacy_projects != PROJECTS_DIR:
        search_dirs.append(legacy_projects)

    file_paths: list[Path] = []
    seen_ids: set[str] = set()
    for directory in search_dirs:
        for yaml_file in sorted(directory.glob("*.yaml")):
            project_id = yaml_file.stem
            if project_id in seen_ids:
                continue
            file_paths.append(yaml_file)
            seen_ids.add(project_id)
    return file_paths


def find_project_by_name(name_or_id: str) -> Optional[Project]:
    """이름 또는 ID로 프로젝트 검색 (부분 일치 포함)."""
    # 1. 정확한 ID 매칭
    candidate_id = project_id_from_name(name_or_id)
    project = load_project(candidate_id)
    if project:
        return project

    all_projects = list_projects()

    # 2. 정확한 이름 매칭
    for p in all_projects:
        if p.name == name_or_id:
            return p

    # 3. 대소문자 무시 부분 일치
    name_lower = name_or_id.lower()
    matches = [p for p in all_projects if name_lower in p.name.lower()]
    if len(matches) == 1:
        return matches[0]

    return None


# ---------------------------------------------------------------------------
# 백업 / 복원
# ---------------------------------------------------------------------------

def backup(output_path: Path) -> None:
    """DevFolio 데이터 전체를 ZIP으로 백업."""
    dirs_to_backup = [DEVFOLIO_CONFIG_DIR, DEVFOLIO_DATA_DIR]
    # 레거시 경로가 다르면 포함
    if _LEGACY_CONFIG.exists():
        dirs_to_backup.append(_LEGACY_HOME)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for base_dir in dirs_to_backup:
            if not base_dir.exists():
                continue
            for file_path in base_dir.rglob("*"):
                if file_path.is_file():
                    arcname = f"{base_dir.name}/{file_path.relative_to(base_dir)}"
                    zf.write(file_path, arcname)


def restore(backup_path: Path) -> None:
    """ZIP 백업에서 복원."""
    ensure_dirs()
    with zipfile.ZipFile(backup_path, "r") as zf:
        # config 파일 복원
        for member in zf.namelist():
            if "config.yaml" in member:
                zf.extract(member, DEVFOLIO_CONFIG_DIR.parent)
            elif "projects/" in member or "exports/" in member or "templates/" in member:
                zf.extract(member, DEVFOLIO_DATA_DIR.parent)


def load_sync_state() -> dict[str, Any]:
    """마지막 GitHub 동기화 상태 로드."""
    if not SYNC_STATE_FILE.exists():
        return {}
    try:
        return json.loads(SYNC_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_sync_state(state: dict[str, Any]) -> None:
    """GitHub 동기화 런타임 상태 저장."""
    ensure_dirs()
    SYNC_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
