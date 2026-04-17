"""DevFolio 로깅 설정."""

import logging
import os


def get_logger(name: str) -> logging.Logger:
    """모듈별 로거 생성. DEVFOLIO_LOG_LEVEL 환경변수로 레벨 제어."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        level_name = os.environ.get("DEVFOLIO_LOG_LEVEL", "WARNING").upper()
        level = getattr(logging, level_name, logging.WARNING)
        logger.setLevel(level)

        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(
            "[%(levelname)s] %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
