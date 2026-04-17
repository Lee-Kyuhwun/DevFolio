"""HTML 페이지 라우터."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

router = APIRouter()
_templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Portfolio Studio 메인 페이지."""
    from devfolio.core.storage import is_initialized, load_config

    initialized = is_initialized()
    cfg = load_config()

    return _templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "initialized": initialized,
            "config": cfg,
        },
    )
