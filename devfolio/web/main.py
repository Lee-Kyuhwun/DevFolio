"""python -m devfolio.web.main 진입점.

멀티프로세싱 spawn 환경(Docker, Windows)에서 freeze_support() 가드가 없으면
자식 프로세스가 __main__ 을 재실행하다 오류를 낸다.
이 파일이 그 가드 역할을 하면서 uvicorn 서버를 직접 띄운다.
"""

from __future__ import annotations

import multiprocessing


def main() -> None:
    import os

    import uvicorn

    from devfolio.web.app import create_app

    host = os.environ.get("DEVFOLIO_HOST", "127.0.0.1")
    port = int(os.environ.get("DEVFOLIO_PORT", "8000"))
    reload = os.environ.get("DEVFOLIO_RELOAD", "").lower() in ("1", "true", "yes")

    if reload:
        uvicorn.run(
            "devfolio.web.app:create_app",
            host=host,
            port=port,
            log_level="warning",
            reload=True,
            reload_dirs=[str(__file__.replace("web/main.py", ""))],
            factory=True,
        )
    else:
        uvicorn.run(create_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
