"""FastAPI Portfolio Studio 앱 팩토리."""

from __future__ import annotations

from pathlib import Path


def create_app():  # type: ignore[return]
    """FastAPI 앱 인스턴스를 생성하고 반환합니다."""
    try:
        from fastapi import FastAPI
        from fastapi.staticfiles import StaticFiles
    except ImportError as e:
        raise ImportError(
            "웹 UI를 실행하려면 gui extra가 필요합니다: pip install 'devfolio[gui]'"
        ) from e

    from devfolio.web.routes.api import router as api_router
    from devfolio.web.routes.ui import router as ui_router

    app = FastAPI(
        title="DevFolio Portfolio Studio",
        description="DevFolio 프로젝트 입력, AI draft, preview, export용 로컬 웹 UI",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(ui_router)
    app.include_router(api_router, prefix="/api")

    return app
