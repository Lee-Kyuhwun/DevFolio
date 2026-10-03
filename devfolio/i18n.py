"""DevFolio 국제화(i18n) 지원.

사용 예시::

    from devfolio.i18n import t, set_locale

    set_locale("ko")
    print(t("project.created", id="my_project"))
    # → "프로젝트 등록 완료! ID: my_project"

환경 변수 ``DEVFOLIO_LANG`` 또는 config 의 ``default_language`` 로도 로케일을 제어한다.

[Spring 비교]
  MessageSource + LocaleResolver 조합을 아주 단순한 dict 카탈로그로 구현한 버전.
  key("project.created") → 텍스트를 가져오고, 필요하면 `{id}` 같은 placeholder를 format 한다.

[Python 문법 메모 — Java 개발자용]
  - `global _current_locale`은 “모듈 전역 변수”를 함수 안에서 수정하겠다는 선언이다.
  - `template.format(**kwargs)`는 Java의 `MessageFormat`/`String.format`과 유사한 placeholder 치환이다.
"""

from __future__ import annotations

import os
from typing import Optional

# 지원 로케일
_SUPPORTED: set[str] = {"ko", "en"}
_DEFAULT_LOCALE = "ko"

_current_locale: str = os.environ.get("DEVFOLIO_LANG", _DEFAULT_LOCALE)

# 로케일별 카탈로그 캐시 (lazy load)
_catalog_cache: dict[str, dict[str, str]] = {}


def _load_catalog(locale: str) -> dict[str, str]:
    """로케일 카탈로그를 로드한다. 지원하지 않는 로케일은 한국어 폴백."""
    if locale not in _catalog_cache:
        # lazy load: 실제로 번역이 필요할 때만 locales 모듈을 import한다(시작 속도/의존성 관리).
        if locale == "en":
            from devfolio.locales.en import STRINGS
        else:
            from devfolio.locales.ko import STRINGS  # type: ignore[assignment]
        _catalog_cache[locale] = STRINGS
    return _catalog_cache[locale]


def set_locale(locale: str) -> None:
    """현재 프로세스의 로케일을 설정한다.

    Args:
        locale: 로케일 코드 ("ko", "en"). 지원하지 않으면 기본값 "ko" 사용.
    """
    global _current_locale
    _current_locale = locale if locale in _SUPPORTED else _DEFAULT_LOCALE


def get_locale() -> str:
    """현재 활성 로케일 코드를 반환한다."""
    return _current_locale


def t(key: str, **kwargs: object) -> str:
    """번역 문자열을 반환한다.

    Args:
        key: 문자열 키 (예: "project.created")
        **kwargs: 문자열 내 ``{변수}`` 치환에 사용할 키워드 인자

    Returns:
        번역된 문자열. 키를 찾을 수 없으면 키 자체를 반환한다.

    Examples:
        >>> set_locale("ko")
        >>> t("project.created", id="abc123")
        '프로젝트 등록 완료! ID: abc123'
    """
    catalog = _load_catalog(_current_locale)
    template = catalog.get(key)
    if template is None:
        # 폴백: 한국어 카탈로그에서 재시도
        if _current_locale != "ko":
            from devfolio.locales.ko import STRINGS as ko_strings

            template = ko_strings.get(key)
        if template is None:
            return key  # 최종 폴백: 키 자체 반환
    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError:
            return template
    return template


def init_from_config(language: Optional[str]) -> None:
    """Config 의 ``default_language`` 값으로 로케일을 초기화한다.

    "both" 값은 한국어로 처리된다.

    Args:
        language: Config.default_language ("ko", "en", "both", 또는 None)
    """
    if not language or language == "both":
        set_locale("ko")
    else:
        set_locale(language)
