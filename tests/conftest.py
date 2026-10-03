"""모든 테스트에 공통으로 적용되는 설정."""

import pytest

from devfolio.core import storage


@pytest.fixture(autouse=True)
def _isolate_ai_log(tmp_path, monkeypatch):
    """AI 호출 로그(ai_logs.jsonl)가 사용자 데이터 폴더에 쓰이지 않게 테스트마다 임시 파일로 바꾼다.

    `_write_ai_log`와 `log._JsonlLogHandler`는 기록할 때마다 `storage.AI_LOG_FILE`을 다시 읽는다.
    """
    monkeypatch.setattr(storage, "AI_LOG_FILE", tmp_path / "ai_logs.jsonl")
