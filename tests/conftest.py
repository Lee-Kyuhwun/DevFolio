"""모든 테스트에 공통으로 적용되는 설정."""

import os
from unittest.mock import patch

import keyring
import pytest
from keyring.backend import KeyringBackend

from devfolio.core import storage


class InMemoryKeyring(KeyringBackend):
    """테스트용 키체인. 사용자의 실제 macOS 키체인 대신 메모리에만 저장한다 (INC-10)."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def get_password(self, service, username):
        return self._store.get((service, username))

    def delete_password(self, service, username):
        self._store.pop((service, username), None)


@pytest.fixture(autouse=True)
def _isolate_credentials():
    """API 키 저장(store_api_key)과 환경 변수 설정이 실제 키체인·셸 환경에 남지 않게 한다."""
    original = keyring.get_keyring()
    keyring.set_keyring(InMemoryKeyring())
    try:
        with patch.dict(os.environ):
            yield
    finally:
        keyring.set_keyring(original)


@pytest.fixture(autouse=True)
def _isolate_ai_log(tmp_path, monkeypatch):
    """AI 호출 로그(ai_logs.jsonl)가 사용자 데이터 폴더에 쓰이지 않게 테스트마다 임시 파일로 바꾼다.

    `_write_ai_log`와 `log._JsonlLogHandler`는 기록할 때마다 `storage.AI_LOG_FILE`을 다시 읽는다.
    """
    monkeypatch.setattr(storage, "AI_LOG_FILE", tmp_path / "ai_logs.jsonl")
