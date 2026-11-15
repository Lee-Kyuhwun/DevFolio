"""로컬 우선 JSON 저장소.

기존 DevFolio 는 프로젝트당 YAML 파일을 썼다. 성과노트는 "빠른 기록"이 핵심이라
컬렉션 단위 JSON 파일을 원자적으로 교체하는 방식을 쓴다(파일 수가 늘지 않고 백업이 단순).

- 데이터 위치: `IMPACTNOTE_DATA_DIR` 또는 platformdirs("impactnote")
- 권한: 0o600 (업무 내용·근거에는 내부 정보가 들어갈 수 있다)
- 동시성: 인스턴스 단위 RLock. 로컬 단일 사용자 도구이므로 파일 잠금은 두지 않는다.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional, Type, TypeVar

from platformdirs import user_config_dir, user_data_dir
from pydantic import BaseModel

from impactnote.core.models import Settings

T = TypeVar("T", bound=BaseModel)

COLLECTIONS = (
    "activities",
    "achievements",
    "evidence",
    "metrics",
    "goals",
    "reports",
    "analyses",
    "project_analyses",
)


def data_dir() -> Path:
    """데이터 디렉터리. 환경변수 우선(테스트·Docker 격리)."""
    override = os.environ.get("IMPACTNOTE_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(user_data_dir("impactnote", "impactnote"))


def config_dir() -> Path:
    override = os.environ.get("IMPACTNOTE_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(user_config_dir("impactnote", "impactnote"))


def legacy_data_dir() -> Path:
    """DevFolio 시절 데이터 위치(마이그레이션 원본, 읽기 전용)."""
    override = os.environ.get("IMPACTNOTE_LEGACY_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(user_data_dir("devfolio", "devfolio"))


def legacy_config_dir() -> Path:
    override = os.environ.get("IMPACTNOTE_LEGACY_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(user_config_dir("devfolio", "devfolio"))


class JsonStore:
    """컬렉션 하나를 JSON 파일로 보관한다."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = Path(directory) if directory else data_dir()
        self._lock = threading.RLock()

    def ensure_dirs(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        if name not in COLLECTIONS and name != "settings":
            raise ValueError(f"알 수 없는 컬렉션입니다: {name}")
        return self.directory / f"{name}.json"

    # -- 원시 읽기/쓰기 ---------------------------------------------------
    def _read(self, name: str) -> Any:
        path = self._path(name)
        if not path.exists():
            return [] if name != "settings" else {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return [] if name != "settings" else {}

    def _write(self, name: str, payload: Any) -> None:
        self.ensure_dirs()
        path = self._path(name)
        temporary: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, delete=False, mode="w", encoding="utf-8"
            ) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o600)
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    # -- 모델 단위 API ----------------------------------------------------
    def list(self, name: str) -> list[dict[str, Any]]:
        with self._lock:
            raw = self._read(name)
        return [item for item in raw if isinstance(item, dict)]

    def all(self, name: str, model: Type[T]) -> list[T]:
        return [model.model_validate(item) for item in self.list(name)]

    def get(self, name: str, item_id: str, model: Type[T]) -> Optional[T]:
        for item in self.list(name):
            if item.get("id") == item_id:
                return model.model_validate(item)
        return None

    def put(self, name: str, item: BaseModel) -> None:
        payload = item.model_dump(mode="json")
        with self._lock:
            items = self.list(name)
            for index, existing in enumerate(items):
                if existing.get("id") == payload["id"]:
                    items[index] = payload
                    break
            else:
                items.append(payload)
            self._write(name, items)

    def delete(self, name: str, item_id: str) -> bool:
        with self._lock:
            items = self.list(name)
            remaining = [item for item in items if item.get("id") != item_id]
            if len(remaining) == len(items):
                return False
            self._write(name, remaining)
            return True

    def replace_all(self, name: str, items: list[BaseModel]) -> None:
        with self._lock:
            self._write(name, [item.model_dump(mode="json") for item in items])

    # -- 설정 ------------------------------------------------------------
    def settings(self) -> Settings:
        with self._lock:
            raw = self._read("settings")
        try:
            return Settings.model_validate(raw or {})
        except Exception:
            return Settings()

    def save_settings(self, settings: Settings) -> None:
        with self._lock:
            self._write("settings", settings.model_dump(mode="json"))


_DEFAULT_STORE: Optional[JsonStore] = None


def get_store() -> JsonStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = JsonStore()
    return _DEFAULT_STORE


def reset_store_for_tests() -> None:
    """테스트에서 환경변수 변경 후 새 경로를 다시 읽게 한다."""
    global _DEFAULT_STORE
    _DEFAULT_STORE = None
