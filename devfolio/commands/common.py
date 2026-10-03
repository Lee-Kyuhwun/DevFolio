"""커맨드 모듈 공통 유틸리티.

[Spring 비교]
  Controller/Command 진입 시 공통으로 수행하는 precondition 체크(필터/인터셉터) 역할.
  예: "초기화(devfolio init) 되었는가?" 같은 검증을 한 곳에 모아둔다.
"""

from devfolio.core.storage import is_initialized
from devfolio.exceptions import DevfolioNotInitializedError


def check_init() -> None:
    """DevFolio 초기화 여부 확인. 미초기화 시 DevfolioNotInitializedError 발생."""
    if not is_initialized():
        raise DevfolioNotInitializedError()
