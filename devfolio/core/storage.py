"""로컬 파일 기반 저장소 (platformdirs + ruamel.yaml).

[Spring 비교]
  Spring 의 JpaRepository / FileSystemResource 를 합쳐 놓은 것.
  DB 대신 YAML 파일을 영속 계층으로 사용하며, 각 Project 가 별도의 .yaml 파일로 저장된다.

  storage.py 함수     ↔  Spring 대응
  ─────────────────────────────────────────────
  load_config()       ↔  @ConfigurationProperties 자동 바인딩
  save_config()       ↔  application.yml 수동 저장
  load_project()      ↔  ProjectRepository.findById()
  save_project()      ↔  ProjectRepository.save()
  delete_project_file() ↔  ProjectRepository.deleteById()
  list_projects()     ↔  ProjectRepository.findAll()
"""

import json
import os
import re
import tempfile
import zipfile
from io import StringIO

# pathlib.Path : OS 독립 파일/디렉터리 경로 클래스.
# [Spring] java.nio.file.Path 와 동일.
from pathlib import Path, PurePosixPath

# Any : 어떤 타입이든 허용. [Spring] Object 와 동일.
# Optional[X] : X or None. [Spring] @Nullable X.
from typing import Any, Optional

# platformdirs : OS 별 설정/데이터 디렉터리를 자동으로 결정해주는 라이브러리.
#   macOS  → ~/Library/Preferences/devfolio/  (config)
#            ~/Library/Application Support/devfolio/  (data)
#   Linux  → ~/.config/devfolio/  (config)
#            ~/.local/share/devfolio/  (data)
#   Windows→ %APPDATA%/devfolio/  (config)
#            %LOCALAPPDATA%/devfolio/  (data)
# [Spring] 환경별 application-{profile}.yml 을 사용하는 것과 유사한 개념.
from platformdirs import user_config_dir, user_data_dir

# ValidationError : Pydantic 이 모델 검증에 실패할 때 던지는 예외.
# [Spring] MethodArgumentNotValidException / BindException 과 동일.
from pydantic import ValidationError

# ruamel.yaml : YAML 주석을 보존하면서 읽고 쓸 수 있는 라이브러리.
#   yaml.safe_load / yaml.dump 는 주석을 날려버리므로 이 라이브러리를 사용한다.
# [Spring] Jackson ObjectMapper 와 동일한 역할 (직렬화 / 역직렬화).
from ruamel.yaml import YAML

from devfolio.exceptions import (
    DevfolioStorageError,
    DevfolioValidationError,
    DevfolioYAMLError,
)
from devfolio.log import get_logger
from devfolio.models.config import Config
from devfolio.models.project import Project

# get_logger(__name__) : 현재 모듈 이름(__name__)으로 Logger 를 가져온다.
# [Spring] private static final Logger log = LoggerFactory.getLogger(Storage.class); 와 동일.
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 경로 설정 (platformdirs 기반 크로스플랫폼)
# ---------------------------------------------------------------------------

_APP_NAME = "devfolio"
_APP_AUTHOR = "devfolio"

# user_config_dir / user_data_dir : OS 에 맞는 설정/데이터 경로를 문자열로 반환.
# Path(...) 로 감싸서 pathlib.Path 객체로 변환.
DEVFOLIO_CONFIG_DIR = Path(user_config_dir(_APP_NAME, _APP_AUTHOR))
DEVFOLIO_DATA_DIR = Path(user_data_dir(_APP_NAME, _APP_AUTHOR))

# Path / "파일명" : 경로를 / 연산자로 이어붙인다.
# [Spring] Paths.get(base, "config.yaml") 와 동일.
CONFIG_FILE = DEVFOLIO_CONFIG_DIR / "config.yaml"
PROJECTS_DIR = DEVFOLIO_DATA_DIR / "projects"
EXPORTS_DIR = DEVFOLIO_DATA_DIR / "exports"
TEMPLATES_DIR = DEVFOLIO_DATA_DIR / "templates"
SYNC_REPO_DIR = DEVFOLIO_DATA_DIR / "sync_repo"
SYNC_STATE_FILE = DEVFOLIO_DATA_DIR / "sync_state.json"
AI_LOG_FILE = DEVFOLIO_DATA_DIR / "ai_logs.jsonl"

# 레거시 경로 호환 — 이전 버전에서 ~/.devfolio/ 를 사용하던 사용자 지원.
# Path.home() : 사용자 홈 디렉터리. [Spring] System.getProperty("user.home").
_LEGACY_HOME = Path.home() / ".devfolio"
_LEGACY_CONFIG = _LEGACY_HOME / "config.yaml"


def _new_yaml() -> YAML:
    """요청마다 파서 상태를 분리해 동시 웹 요청이 서로 간섭하지 않게 한다."""
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    yaml.width = 4096
    return yaml


def _atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    """같은 디렉터리의 임시 파일을 완성한 뒤 원본을 원자적으로 교체한다."""
    temporary: Optional[Path] = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _save_yaml(path: Path, payload: dict[str, Any]) -> None:
    try:
        ensure_dirs()
        buffer = StringIO()
        _new_yaml().dump(payload, buffer)
        _atomic_write(path, buffer.getvalue().encode("utf-8"))
    except Exception as exc:
        raise DevfolioStorageError(f"YAML 저장 실패: {path}") from exc


def _validate_project_id(project_id: str) -> None:
    if not re.fullmatch(r"[\w.-]+", project_id) or project_id in {".", ".."}:
        raise DevfolioValidationError(
            "프로젝트 ID에 경로 구분자나 특수문자를 사용할 수 없습니다."
        )


# ---------------------------------------------------------------------------
# 디렉터리 초기화
# ---------------------------------------------------------------------------


def ensure_dirs() -> None:
    """필요한 디렉터리를 모두 생성한다.

    [Spring] @PostConstruct 에서 디렉터리 존재 여부를 확인/생성하는 init() 메서드와 유사.
    """
    # mkdir(parents=True, exist_ok=True) :
    #   parents=True  → 중간 디렉터리가 없으면 함께 생성. [Spring] Files.createDirectories(path).
    #   exist_ok=True → 이미 있어도 예외 없음. [Spring] Files.createDirectories 와 동일.
    DEVFOLIO_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DEVFOLIO_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def is_initialized() -> bool:
    """config.yaml 이 존재하면 초기화된 것으로 간주."""
    # Path.exists() : 파일/디렉터리가 존재하면 True. [Spring] Files.exists(path).
    return CONFIG_FILE.exists() or _LEGACY_CONFIG.exists()


def _resolve_config_path() -> Path:
    """레거시 경로(~/.devfolio/config.yaml)를 자동 감지해 반환한다."""
    if _LEGACY_CONFIG.exists() and not CONFIG_FILE.exists():
        return _LEGACY_CONFIG
    return CONFIG_FILE


def get_config_path() -> Optional[Path]:
    """현재 사용 중인 설정 파일 경로를 반환한다. 없으면 None."""
    path = _resolve_config_path()
    # 존재하면 Path 반환, 없으면 None.
    return path if path.exists() else None


# ---------------------------------------------------------------------------
# 설정 저장/로드
# ---------------------------------------------------------------------------


def load_config() -> Config:
    """YAML 설정 파일을 읽어 Config Pydantic 모델로 반환한다.

    [Spring 비교]
      @ConfigurationProperties 바인딩과 동일.
      파일이 없으면 기본값(Config())을 반환한다.
    """
    path = _resolve_config_path()
    if not path.exists():
        # 설정 파일 없음 → 빈 기본 Config 반환. [Spring] 기본값으로 초기화된 @ConfigurationProperties.
        return Config()
    try:
        # open(path, "r", encoding="utf-8") : 파일을 읽기 모드로 열기.
        # [Spring] new FileInputStream(path) 와 유사. with 블록이 닫히면 자동 close.
        with open(path, "r", encoding="utf-8") as f:
            # _yaml.load(f) : YAML → Python dict 로 역직렬화.
            # or {} : 빈 파일이면 None 을 반환하므로 빈 dict 로 대체.
            data = _new_yaml().load(f) or {}
        # Config.model_validate(data) : dict → Config 모델 변환 + 검증.
        # [Spring] ObjectMapper.convertValue(data, Config.class) 와 동일.
        return Config.model_validate(data)
    except ValidationError as e:
        raise DevfolioYAMLError(str(path), str(e)) from e
    except Exception as e:
        raise DevfolioYAMLError(str(path), str(e)) from e


def save_config(config: Config) -> None:
    """Config 모델을 YAML 파일로 저장한다.

    [Spring 비교]
      application.yml 을 런타임에 덮어쓰는 것과 유사.
      저장 후 0o600 권한으로 설정 (소유자만 읽기/쓰기) — API 키 보호용.
    """
    path = _resolve_config_path()
    _save_yaml(path, config.model_dump(exclude_none=False))


# ---------------------------------------------------------------------------
# 프로젝트 ID 변환
# ---------------------------------------------------------------------------


def project_id_from_name(name: str) -> str:
    """프로젝트명 → 파일명에 안전한 ID 문자열로 변환한다.

    예: "My Project!" → "my_project"
    [Spring] 슬러그 생성 유틸리티 함수와 동일한 역할.
    """
    # re.sub(pattern, replacement, string) : 정규식 치환.
    # [Spring] string.replaceAll(regex, replacement) 와 동일.
    # r"[^\w\s-]" : 단어 문자(\w), 공백(\s), 하이픈(-) 이외의 문자 제거.
    safe = re.sub(r"[^\w\s-]", "", name.lower())
    # 공백/하이픈 연속을 언더스코어 하나로 치환.
    safe = re.sub(r"[\s-]+", "_", safe)
    # strip("_") : 앞뒤 언더스코어 제거. [Spring] StringUtils.strip(safe, "_").
    # or "project" : 결과가 빈 문자열이면 "project" 사용.
    return safe.strip("_") or "project"


# ---------------------------------------------------------------------------
# 프로젝트 CRUD
# ---------------------------------------------------------------------------


def load_project(project_id: str) -> Optional[Project]:
    """ID 로 프로젝트 YAML 파일을 읽어 Project 모델로 반환한다.

    [Spring 비교]
      ProjectRepository.findById(id) — 없으면 None(Optional.empty()).
    """
    _validate_project_id(project_id)
    path = PROJECTS_DIR / f"{project_id}.yaml"
    # 레거시 경로 폴백 — 신규 경로에 없으면 레거시에서 찾는다.
    if not path.exists():
        legacy = _LEGACY_HOME / "projects" / f"{project_id}.yaml"
        if legacy.exists():
            path = legacy
        else:
            return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _new_yaml().load(f) or {}
        # Project.model_validate(data) : dict → Project 모델로 검증/변환.
        return Project.model_validate(data)
    except ValidationError as e:
        raise DevfolioYAMLError(str(path), str(e)) from e
    except Exception as e:
        raise DevfolioYAMLError(str(path), str(e)) from e


def save_project(project: Project) -> None:
    """Project 모델을 YAML 파일로 저장한다.

    [Spring 비교]
      ProjectRepository.save(project) — ID 를 기반으로 파일명 결정.
    """
    _validate_project_id(project.id)
    try:
        project = Project.model_validate(project.model_dump(exclude_none=False))
    except ValidationError as exc:
        raise DevfolioValidationError(str(exc)) from exc
    path = PROJECTS_DIR / f"{project.id}.yaml"
    _save_yaml(path, project.model_dump(exclude_none=False))


def delete_project_file(project_id: str) -> bool:
    """프로젝트 YAML 파일을 삭제한다. 삭제 성공이면 True.

    [Spring 비교]
      ProjectRepository.deleteById(id).
    """
    _validate_project_id(project_id)
    path = PROJECTS_DIR / f"{project_id}.yaml"
    if not path.exists():
        # 레거시 경로 확인
        legacy = _LEGACY_HOME / "projects" / f"{project_id}.yaml"
        if legacy.exists():
            # Path.unlink() : 파일 삭제. [Spring] Files.delete(path).
            legacy.unlink()
            return True
        return False
    path.unlink()
    return True


def list_projects() -> list[Project]:
    """저장된 모든 프로젝트를 읽어 리스트로 반환한다.

    [Spring 비교]
      ProjectRepository.findAll() — 신규/레거시 디렉터리 모두 검색하며 중복 제거.
    """
    projects: list[Project] = []

    # 검색 대상 디렉터리 목록. 신규 + 레거시(중복 방지).
    search_dirs = [PROJECTS_DIR]
    legacy_projects = _LEGACY_HOME / "projects"
    # 레거시 경로가 다르면 추가 (PROJECTS_DIR 와 같은 경로면 중복이므로 건너뜀).
    if legacy_projects.exists() and legacy_projects != PROJECTS_DIR:
        search_dirs.append(legacy_projects)

    # set[str] : 중복 없는 ID 집합. [Spring] Set<String> 과 동일.
    seen_ids: set[str] = set()
    for directory in search_dirs:
        # Path.glob("*.yaml") : 디렉터리 내 *.yaml 파일을 모두 열거.
        # [Spring] Files.walk(directory).filter(p -> p.toString().endsWith(".yaml")).
        for yaml_file in sorted(directory.glob("*.yaml")):
            # Path.stem : 확장자 없는 파일명. "project_a.yaml" → "project_a".
            # [Spring] FilenameUtils.getBaseName(filename) 과 동일.
            project_id = yaml_file.stem
            # 이미 처리한 ID 는 건너뜀 (레거시+신규 중복 방지).
            if project_id in seen_ids:
                continue
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = _new_yaml().load(f) or {}
                projects.append(Project.model_validate(data))
                # set.add() : ID 를 seen 에 추가. [Spring] Set.add(id).
                seen_ids.add(project_id)
            except Exception as e:
                # 손상된 파일은 건너뛰고 경고 로그만 남긴다.
                logger.warning("손상된 프로젝트 파일 건너뜀: %s (%s)", yaml_file, e)
                continue
    return projects


def get_project_file_paths() -> list[Path]:
    """저장된 프로젝트 YAML 파일 경로 목록을 반환한다."""
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
    """이름 또는 ID 로 프로젝트를 검색한다.

    탐색 순서:
      1. 정확한 ID 매칭
      2. 정확한 이름 매칭
      3. 대소문자 무시 부분 일치 (단 하나일 때만 반환)

    [Spring 비교]
      ProjectRepository.findByNameContainingIgnoreCase() 와 유사하나
      우선순위를 명시적으로 구현.
    """
    # 1. 정확한 ID 매칭
    if re.fullmatch(r"[\w.-]+", name_or_id) and name_or_id not in {".", ".."}:
        project = load_project(name_or_id)
        if project:
            return project

    all_projects = list_projects()

    # 2. 정확한 이름 매칭
    for p in all_projects:
        if p.name == name_or_id:
            return p

    # 3. 대소문자 무시 부분 일치 — 결과가 정확히 1개일 때만 반환.
    name_lower = name_or_id.strip().lower()
    if not name_lower:
        return None
    # [Spring] stream().filter(p -> p.getName().toLowerCase().contains(name_lower)).collect(toList()).
    matches = [p for p in all_projects if name_lower in p.name.lower()]
    if len(matches) == 1:
        return matches[0]

    return None


# ---------------------------------------------------------------------------
# 백업 / 복원
# ---------------------------------------------------------------------------


def backup(output_path: Path) -> None:
    """DevFolio 데이터 전체를 ZIP 파일로 백업한다.

    [Spring 비교]
      파일 시스템 전체를 ZipOutputStream 으로 묶는 것과 동일.
    """
    directories = [("config", DEVFOLIO_CONFIG_DIR), ("data", DEVFOLIO_DATA_DIR)]
    if _LEGACY_HOME.exists():
        directories.append(("legacy", _LEGACY_HOME))
    temporary: Optional[Path] = None
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
        excluded = {output_path.resolve(), temporary.resolve()}
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as zf:
            for label, base_dir in directories:
                for file_path in sorted(base_dir.rglob("*")):
                    if file_path.is_symlink() or not file_path.is_file():
                        continue
                    if file_path.resolve() in excluded:
                        continue
                    relative = file_path.relative_to(base_dir).as_posix()
                    zf.write(file_path, f"{label}/{relative}")
        temporary.replace(output_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise DevfolioStorageError(f"백업 실패: {output_path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def restore(backup_path: Path) -> None:
    """ZIP 백업 파일에서 데이터를 복원한다.

    [Spring 비교]
      ZipInputStream 으로 파일을 순서대로 읽어 저장하는 것과 동일.
    """
    # 파일 전체를 읽고 검증한 뒤에만 현재 저장소에 반영한다.
    pending: dict[Path, tuple[int, bytes]] = {}
    originals: dict[Path, tuple[bytes, int] | None] = {}
    written: list[Path] = []
    try:
        with zipfile.ZipFile(backup_path, "r") as zf:
            for member in zf.infolist():
                parts = PurePosixPath(member.filename).parts
                if (
                    not parts
                    or PurePosixPath(member.filename).is_absolute()
                    or ".." in parts
                    or "\\" in member.filename
                    or ":" in parts[0]
                    or (member.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise ValueError("백업에 안전하지 않은 경로가 있습니다.")
                if member.is_dir() or len(parts) < 2:
                    continue
                root, *relative = parts
                priority = 2 if root in {"legacy", ".devfolio"} else 1
                if relative == ["config.yaml"] and root in {
                    "config",
                    "devfolio",
                    ".devfolio",
                    "legacy",
                    DEVFOLIO_CONFIG_DIR.name,
                }:
                    base = DEVFOLIO_CONFIG_DIR
                    target = CONFIG_FILE
                elif root == "data":
                    base = DEVFOLIO_DATA_DIR
                    target = base.joinpath(*relative)
                elif root in {
                    "devfolio",
                    ".devfolio",
                    "legacy",
                    DEVFOLIO_DATA_DIR.name,
                } and relative[0] in {"projects", "exports", "templates"}:
                    base = DEVFOLIO_DATA_DIR
                    target = base.joinpath(*relative)
                else:
                    continue
                if root in {"config", "data"}:
                    priority = 0
                if not target.resolve().is_relative_to(base.resolve()):
                    raise ValueError("복원 경로가 데이터 디렉터리를 벗어납니다.")
                content = zf.read(member)
                if target == CONFIG_FILE:
                    Config.model_validate(
                        _new_yaml().load(content.decode("utf-8")) or {}
                    )
                elif target.parent == PROJECTS_DIR and target.suffix == ".yaml":
                    project = Project.model_validate(
                        _new_yaml().load(content.decode("utf-8")) or {}
                    )
                    _validate_project_id(project.id)
                    if project.id != target.stem:
                        raise ValueError("프로젝트 ID와 백업 파일명이 다릅니다.")
                if target in pending:
                    previous_priority, _ = pending[target]
                    if previous_priority == priority:
                        raise ValueError("백업에 중복된 복원 경로가 있습니다.")
                    if previous_priority < priority:
                        continue
                pending[target] = (priority, content)
        if not pending:
            raise ValueError("복원할 DevFolio 데이터가 없습니다.")
        ensure_dirs()
        for target in pending:
            originals[target] = (
                (target.read_bytes(), target.stat().st_mode & 0o777)
                if target.exists()
                else None
            )
        for target, (_, content) in pending.items():
            _atomic_write(target, content)
            written.append(target)
    except Exception as exc:
        rollback_failures: list[str] = []
        for target in reversed(written):
            try:
                original = originals[target]
                if original is None:
                    target.unlink(missing_ok=True)
                else:
                    _atomic_write(target, *original)
            except OSError:
                rollback_failures.append(str(target))
        detail = f"백업 복원 실패: {backup_path}"
        if rollback_failures:
            detail += " (원본 복구 실패: " + ", ".join(rollback_failures) + ")"
        raise DevfolioStorageError(detail) from exc


def load_sync_state() -> dict[str, Any]:
    """마지막 GitHub 동기화 상태를 JSON 파일에서 읽어 반환한다.

    [Spring 비교]
      Redis 또는 별도 파일에 저장된 캐시/상태를 읽는 것과 유사.
    """
    if not SYNC_STATE_FILE.exists():
        return {}
    try:
        # Path.read_text() : 파일 내용을 문자열로 한번에 읽기.
        # json.loads() : JSON 문자열 → Python dict. [Spring] ObjectMapper.readValue(json, Map.class).
        return json.loads(SYNC_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_sync_state(state: dict[str, Any]) -> None:
    """GitHub 동기화 런타임 상태를 JSON 파일로 저장한다."""
    ensure_dirs()
    # json.dumps(obj, ensure_ascii=False, indent=2) :
    #   ensure_ascii=False → 한글 등 비ASCII 문자를 이스케이프하지 않음.
    #   indent=2 → 2칸 들여쓰기로 pretty-print.
    # [Spring] ObjectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(state).
    SYNC_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
