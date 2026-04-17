"""HTML 페이지 라우터.

[Spring 비교]
  @Controller (뷰를 반환하는 컨트롤러) + Thymeleaf TemplateEngine 역할.
  JSON 대신 HTML 을 응답으로 반환하며, Jinja2 를 사용해 서버 사이드 렌더링(SSR)을 수행한다.

  APIRouter    ↔  @Controller 클래스
  @router.get  ↔  @GetMapping
  Jinja2Templates ↔  ThymeleafTemplateEngine / TemplateResolver
  TemplateResponse ↔  ModelAndView
"""

from __future__ import annotations

from pathlib import Path

# APIRouter : 라우터(컨트롤러) 객체. [Spring] @Controller 클래스에 해당.
#   여러 라우터를 만들어 app.include_router() 로 앱에 합친다.
from fastapi import APIRouter

# HTMLResponse : HTTP 응답 Content-Type 을 "text/html" 로 설정.
# [Spring] @RequestMapping(produces = MediaType.TEXT_HTML_VALUE) 와 유사.
from fastapi.responses import HTMLResponse

# Jinja2Templates : Jinja2 템플릿 엔진 래퍼.
# [Spring] SpringTemplateEngine (Thymeleaf) 와 동일한 역할.
from fastapi.templating import Jinja2Templates

# Request : HTTP 요청 객체. [Spring] HttpServletRequest 와 동일.
#   TemplateResponse 에 필수 — 템플릿에서 request URL 등에 접근할 수 있게 주입.
from starlette.requests import Request

# APIRouter() : 라우트 그룹 생성. [Spring] @Controller 클래스 선언과 동일.
router = APIRouter()

# Jinja2Templates(directory=...) : 템플릿 파일이 있는 디렉터리를 지정.
# [Spring] ThymeleafProperties.setPrefix("classpath:/templates/") 와 동일.
#
# Path(__file__).parent.parent / "templates" :
#   __file__ = devfolio/web/routes/ui.py
#   .parent   = devfolio/web/routes/
#   .parent   = devfolio/web/
#   .parent   = devfolio/
#   / "templates" → devfolio/web/templates/
_templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# @router.get("/", response_class=HTMLResponse)
#   GET "/" 요청 → 이 함수가 처리.
#   response_class=HTMLResponse : 응답을 HTML 로 선언 (기본은 JSON).
#   [Spring] @GetMapping("/") + @ResponseBody + produces=TEXT_HTML.
@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """Portfolio Studio 메인 페이지."""
    # lazy import : 이 라우터가 실제로 호출될 때만 storage 모듈을 로드.
    from devfolio.core.storage import is_initialized, load_config

    initialized = is_initialized()
    # load_config() : Config 파일을 읽어 Pydantic Config 객체를 반환.
    # 초기화 전이면 빈 Config() 를 반환하므로 예외 없이 안전하다.
    cfg = load_config()

    # _templates.TemplateResponse(request, "index.html", {...})
    #   첫 번째 인수가 반드시 Request 여야 하는 것은 Starlette 신버전 API 규칙.
    #   [Spring] ModelAndView("index", model) 또는
    #     model.addAttribute("initialized", initialized); return "index"; 와 동일.
    return _templates.TemplateResponse(
        request,
        "index.html",
        {
            # 템플릿(index.html) 에서 {{ initialized }}, {{ config }} 로 접근 가능.
            # [Spring] model.addAttribute("initialized", initialized) 와 동일.
            "initialized": initialized,
            "config": cfg,
        },
    )
