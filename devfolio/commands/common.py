"""커맨드 모듈 공통 유틸리티."""

from devfolio.core.storage import is_initialized
from devfolio.exceptions import DevfolioNotInitializedError


def check_init() -> None:
    """DevFolio 초기화 여부 확인. 미초기화 시 DevfolioNotInitializedError 발생."""
    if not is_initialized():
        raise DevfolioNotInitializedError()
