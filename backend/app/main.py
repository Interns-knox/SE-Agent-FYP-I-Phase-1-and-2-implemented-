import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.domains.artifacts.router import router as artifacts_router
from app.domains.context.router import router as context_router
from app.domains.features.router import router as features_router
from app.domains.workflow.router import router as workflow_router
from app.domains.workspace.router import health_router
from app.domains.workspace.router import router as workspace_router

logger = logging.getLogger("se_agent")


def create_app() -> FastAPI:
    app = FastAPI(title="SE Agent Platform", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(workspace_router)
    app.include_router(features_router)
    app.include_router(context_router)
    app.include_router(artifacts_router)
    app.include_router(workflow_router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
