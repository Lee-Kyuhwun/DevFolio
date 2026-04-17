"""FastAPI Portfolio Studio 앱 팩토리.

[Spring 비교]
  @Configuration + @Bean 으로 ApplicationContext 를 구성하는 것과 동일.
  create_app() 이 FastAPI 인스턴스를 만들어 반환하는 팩토리 함수.

  FastAPI  ↔  Spring MVC DispatcherServlet
  router   ↔  @RestController / @Controller
  /static  ↔  addResourceHandlers (정적 파일 서빙)
  prefix   ↔  @RequestMapping("/api")
"""

from __future__ import annotations

# pathlib.Path : OS 에 상관없이 파일/디렉터리 경로를 다루는 클래스.
# [Spring] java.nio.file.Path 와 동일한 역할.
from pathlib import Path


def create_app():  # type: ignore[return]
    """FastAPI 앱 인스턴스를 생성하고 반환한다.

    [Spring 비교]
      @Configuration 클래스의 @Bean 메서드 — 호출될 때마다 새 인스턴스를 만든다.
      `devfolio serve` 커맨드에서 uvicorn.run(create_app(), ...) 형태로 사용.

    gui extra(FastAPI, uvicorn 등)가 설치되지 않은 환경에서는 ImportError 를 발생시킨다.
    lazy import 를 쓰는 이유: gui 없이 CLI 만 쓰는 환경에서 모듈 로드 시 에러가 나지 않도록.
    """
    # 함수 안에서 import 하는 패턴(lazy import).
    # [Spring] @Lazy 빈 — 실제로 필요할 때까지 의존성을 로드하지 않는 것과 유사.
    try:
        # FastAPI : ASGI 웹 프레임워크. [Spring] DispatcherServlet + Spring MVC 전체.
        from fastapi import FastAPI
        # StaticFiles : /static 경로로 정적 파일(CSS, JS, 이미지)을 서빙하는 미들웨어.
        # [Spring] WebMvcConfigurer.addResourceHandlers("classpath:/static/**") 와 동일.
        from fastapi.staticfiles import StaticFiles
    except ImportError as e:
        raise ImportError(
            "웹 UI를 실행하려면 gui extra가 필요합니다: pip install 'devfolio[gui]'"
        ) from e

    from devfolio.web.routes.api import router as api_router
    from devfolio.web.routes.ui import router as ui_router

    # FastAPI(...) : 앱 인스턴스 생성.
    # docs_url=None, redoc_url=None : /docs(Swagger UI), /redoc 엔드포인트 비활성화.
    # 로컬 개인 도구이므로 외부에 Swagger UI 를 노출하지 않는다.
    app = FastAPI(
        title="DevFolio Portfolio Studio",
        description="DevFolio 프로젝트 입력, AI draft, preview, export용 로컬 웹 UI",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )

    # Path(__file__) : 현재 파일(app.py)의 절대 경로.
    # .parent : app.py 가 있는 디렉터리 (devfolio/web/).
    # / "static" : Path 는 / 연산자로 경로를 합칠 수 있다. [Spring] Paths.get(...).resolve("static").
    static_dir = Path(__file__).parent / "static"

    # app.mount("/static", StaticFiles(...), name="static")
    #   "/static" URL 이하의 요청을 static_dir 디렉터리에서 파일로 처리.
    #   [Spring] registry.addResourceHandler("/static/**").addResourceLocations("classpath:/static/").
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # app.include_router(router) : 라우터(컨트롤러)를 앱에 등록.
    # [Spring] @Import(UIController.class) 또는 @ComponentScan 으로 Bean 등록.
    app.include_router(ui_router)

    # prefix="/api" : api_router 의 모든 경로 앞에 /api 를 붙인다.
    # [Spring] @RequestMapping("/api") 를 클래스에 붙인 것과 동일.
    app.include_router(api_router, prefix="/api")

    return app
