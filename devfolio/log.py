"""DevFolio 로깅 설정.

[Spring 비교]
  SLF4J + Logback 설정을 코드로 구성한 형태.
  모듈별 Logger를 만들고(StreamHandler), 특정 모듈은 JSONL 파일로도 로깅한다.

[Python 문법 메모 — Java 개발자용]
  - `if not logger.handlers:`는 “중복 핸들러 추가 방지”를 위한 가드(재호출 시 로그 중복 출력 방지).
  - `logger.propagate = False`는 루트 로거로 전파를 끊어 “중복 출력”을 막는다.
"""

import json
import logging
import os
from datetime import datetime, timezone

_AI_LOG_MODULES = frozenset(
    {
        "devfolio.core.ai_service",
        "devfolio.core.git_scanner",
        "devfolio.web.routes.api",
    }
)


class _JsonlLogHandler(logging.Handler):
    """INFO+ 로그 레코드를 ai_logs.jsonl 에 append-only 기록."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            from devfolio.core.storage import AI_LOG_FILE, DEVFOLIO_DATA_DIR

            DEVFOLIO_DATA_DIR.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "op": "log",
                "message": self.format(record),
            }
            with AI_LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


def get_logger(name: str) -> logging.Logger:
    """모듈별 로거 생성. DEVFOLIO_LOG_LEVEL 환경변수로 레벨 제어."""
    logger = logging.getLogger(name)
    logger.propagate = False

    if not logger.handlers:
        # 환경변수(DEVFOLIO_LOG_LEVEL)로 로깅 레벨을 동적으로 조절한다.
        level_name = os.environ.get("DEVFOLIO_LOG_LEVEL", "WARNING").upper()
        level = getattr(logging, level_name, logging.WARNING)
        logger.setLevel(level)

        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        if name in _AI_LOG_MODULES:
            # AI 관련 모듈은 디버깅/감사를 위해 jsonl 파일에도 로그를 남긴다.
            jsonl_handler = _JsonlLogHandler()
            jsonl_handler.setLevel(logging.INFO)
            jsonl_handler.setFormatter(formatter)
            logger.addHandler(jsonl_handler)
            logger.setLevel(min(level, logging.INFO))

    return logger
