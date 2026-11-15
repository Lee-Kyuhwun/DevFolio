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
def _isolate_model_health(tmp_path, monkeypatch):
    """모델 Circuit Breaker 상태가 테스트 사이에 전염되지 않게 매번 새로 만든다 (INC-10, INC-22).

    상태는 프로세스 전역 싱글턴이고 파일에도 저장되므로, 격리하지 않으면 앞선 테스트가
    차단한 모델이 다음 테스트에서 "후보 없음"으로 이어진다.
    """
    from devfolio.core import ai_reliability

    store = ai_reliability.ModelHealthStore(path=tmp_path / "ai_model_health.json")
    monkeypatch.setattr(ai_reliability, "_DEFAULT_STORE", store)
    yield store


@pytest.fixture(autouse=True)
def _isolate_analysis_runs(tmp_path, monkeypatch):
    """AI 분석 실행 기록이 사용자 데이터 폴더에 쓰이지 않게 테스트마다 임시 파일로 바꾼다."""
    from devfolio.core import ai_observability

    registry = ai_observability.AnalysisRunRegistry(
        path=tmp_path / "ai_analysis_runs.json"
    )
    monkeypatch.setattr(ai_observability, "_DEFAULT_REGISTRY", registry)
    yield registry


@pytest.fixture(autouse=True)
def _isolate_ai_log(tmp_path, monkeypatch):
    """AI 호출 로그(ai_logs.jsonl)가 사용자 데이터 폴더에 쓰이지 않게 테스트마다 임시 파일로 바꾼다.

    `_write_ai_log`와 `log._JsonlLogHandler`는 기록할 때마다 `storage.AI_LOG_FILE`을 다시 읽는다.
    """
    monkeypatch.setattr(storage, "AI_LOG_FILE", tmp_path / "ai_logs.jsonl")
