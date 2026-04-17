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
import re
import zipfile

# pathlib.Path : OS 독립 파일/디렉터리 경로 클래스.
# [Spring] java.nio.file.Path 와 동일.
from pathlib import Path

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

from devfolio.exceptions import DevfolioYAMLError
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

# 레거시 경로 호환 — 이전 버전에서 ~/.devfolio/ 를 사용하던 사용자 지원.
# Path.home() : 사용자 홈 디렉터리. [Spring] System.getProperty("user.home").
_LEGACY_HOME = Path.home() / ".devfolio"
_LEGACY_CONFIG = _LEGACY_HOME / "config.yaml"

# YAML() : ruamel.yaml 인스턴스. 파일마다 새로 만들지 않고 모듈 레벨에서 하나만 유지.
# [Spring] ObjectMapper 싱글톤과 동일한 패턴.
_yaml = YAML()
# default_flow_style=False : 블록 스타일(들여쓰기)로 YAML 출력. 가독성 우선.
_yaml.default_flow_style = False
# preserve_quotes=True : 원본의 따옴표 스타일을 유지.
_yaml.preserve_quotes = True
# width=4096 : 한 줄이 4096자 이상일 때만 줄바꿈. 긴 URL 이 잘리지 않도록.
_yaml.width = 4096


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
            data = _yaml.load(f) or {}
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
    ensure_dirs()
    path = _resolve_config_path()
    with open(path, "w", encoding="utf-8") as f:
        # config.model_dump(exclude_none=False) : Config → dict 변환.
        #   exclude_none=False → None 값도 포함해서 직렬화.
        #   [Spring] @JsonInclude(Include.ALWAYS) 와 동일.
        _yaml.dump(config.model_dump(exclude_none=False), f)
    # path.chmod(0o600) : Unix 파일 권한을 octal 로 설정.
    #   0o600 = 소유자 읽기+쓰기, 그룹/기타 접근 불가.
    # [Spring] Files.setPosixFilePermissions(path, Set.of(OWNER_READ, OWNER_WRITE)) 와 동일.
    path.chmod(0o600)


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
            data = _yaml.load(f) or {}
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
    ensure_dirs()
    path = PROJECTS_DIR / f"{project.id}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        # project.model_dump(exclude_none=False) : Project → dict.
        _yaml.dump(project.model_dump(exclude_none=False), f)


def delete_project_file(project_id: str) -> bool:
    """프로젝트 YAML 파일을 삭제한다. 삭제 성공이면 True.

    [Spring 비교]
      ProjectRepository.deleteById(id).
    """
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
                    data = _yaml.load(f) or {}
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
    candidate_id = project_id_from_name(name_or_id)
    project = load_project(candidate_id)
    if project:
        return project

    all_projects = list_projects()

    # 2. 정확한 이름 매칭
    for p in all_projects:
        if p.name == name_or_id:
            return p

    # 3. 대소문자 무시 부분 일치 — 결과가 정확히 1개일 때만 반환.
    name_lower = name_or_id.lower()
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
    dirs_to_backup = [DEVFOLIO_CONFIG_DIR, DEVFOLIO_DATA_DIR]
    if _LEGACY_CONFIG.exists():
        dirs_to_backup.append(_LEGACY_HOME)

    # zipfile.ZipFile(path, "w", ZIP_DEFLATED) : 압축 ZIP 파일을 쓰기 모드로 열기.
    # [Spring] new ZipOutputStream(new FileOutputStream(path)) 와 동일.
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for base_dir in dirs_to_backup:
            if not base_dir.exists():
                continue
            # Path.rglob("*") : 하위 디렉터리까지 재귀 탐색.
            # [Spring] Files.walk(base_dir) 와 동일.
            for file_path in base_dir.rglob("*"):
                if file_path.is_file():
                    # arcname : ZIP 안에서의 경로 이름.
                    # file_path.relative_to(base_dir) : 상대 경로로 변환.
                    arcname = f"{base_dir.name}/{file_path.relative_to(base_dir)}"
                    zf.write(file_path, arcname)


def restore(backup_path: Path) -> None:
    """ZIP 백업 파일에서 데이터를 복원한다.

    [Spring 비교]
      ZipInputStream 으로 파일을 순서대로 읽어 저장하는 것과 동일.
    """
    ensure_dirs()
    # zipfile.ZipFile(path, "r") : ZIP 파일을 읽기 모드로 열기.
    with zipfile.ZipFile(backup_path, "r") as zf:
        # zf.namelist() : ZIP 내 모든 파일 이름 목록.
        for member in zf.namelist():
            if "config.yaml" in member:
                zf.extract(member, DEVFOLIO_CONFIG_DIR.parent)
            elif "projects/" in member or "exports/" in member or "templates/" in member:
                zf.extract(member, DEVFOLIO_DATA_DIR.parent)


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
