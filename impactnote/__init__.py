"""성과노트(ImpactNote) — 근거 기반 업무 성과 기록·보고 도구.

기존 DevFolio(포트폴리오/이력서) 패키지는 데이터·API 호환 계층으로 남기고,
사용자에게 보이는 제품과 새 도메인은 이 패키지가 담당한다.
"""

from __future__ import annotations

APP_NAME = "성과노트"
APP_NAME_EN = "ImpactNote"
APP_SLUG = "impactnote"
__version__ = "1.0.0"

__all__ = ["APP_NAME", "APP_NAME_EN", "APP_SLUG", "__version__"]
