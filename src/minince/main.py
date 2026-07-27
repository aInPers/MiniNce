from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from minince.config import settings
from minince.infrastructure.database.connection import Base, engine
from minince.logging import setup_logging
from minince.web.routers.api import router as api_router
from minince.web.routers.backups import router as backups_router
from minince.web.routers.canvas import router as canvas_router
from minince.web.routers.devices import router as devices_router
from minince.web.routers.manual_config import router as manual_config_router
from minince.web.routers.ospf import router as ospf_router
from minince.web.routers.pages import router as pages_router


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="MiniNCE - 轻量级网络自动化配置平台",
        debug=settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(pages_router)
    app.include_router(api_router)
    app.include_router(devices_router)
    app.include_router(canvas_router)
    app.include_router(manual_config_router)
    app.include_router(backups_router)
    app.include_router(ospf_router)

    return app


app = create_app()


@app.on_event("startup")
async def startup_event() -> None:
    Base.metadata.create_all(bind=engine)


def main() -> None:
    uvicorn.run(
        "minince.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
