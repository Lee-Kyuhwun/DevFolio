"""성과노트 FastAPI 앱 팩토리."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from impactnote import APP_NAME, APP_NAME_EN, __version__


def create_app() -> FastAPI:
    from impactnote.web.api import router as api_router

    try:  # litellm 백그라운드 프로세스가 spawn 환경에서 오류를 내지 않게 한다.
        import litellm

        litellm.telemetry = False
        litellm.suppress_debug_info = True
    except Exception:  # noqa: BLE001 — AI 미설치 환경도 정상 동작해야 한다
        pass

    app = FastAPI(
        title=f"{APP_NAME} ({APP_NAME_EN})",
        description="근거 기반 업무 성과 기록 및 보고서 작성 도구",
        version=__version__,
        docs_url=None,
        redoc_url=None,
    )

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.include_router(api_router, prefix="/api")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html", media_type="text/html")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(static_dir / "favicon.svg", media_type="image/svg+xml")

    return app
