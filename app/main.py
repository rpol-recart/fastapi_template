from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.config import AppSettings
from app.core.logging import setup_logging
from app.core.di import AppContainer
from app.api.routes import router as api_router
from app.infrastructure.db.errors import DatabaseUnavailableError
import logging
import uuid


def create_app() -> FastAPI:
    settings = AppSettings()
    setup_logging(level=settings.log_level, json_format=settings.log_json)

    app = FastAPI(title=settings.app_name)

    container = AppContainer(settings=settings)
    app.state.container = container  # type: ignore[attr-defined]

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        logger = logging.getLogger("app")
        extra = {"request_id": request_id}
        request.state.request_id = request_id  # type: ignore[attr-defined]
        try:
            response = await call_next(request)
        finally:
            # Можно добавить access log
            logger.debug("Request processed", extra=extra)
        response.headers["x-request-id"] = request_id
        return response

    # Глобальный обработчик: БД временно недоступна -> 503
    @app.exception_handler(DatabaseUnavailableError)
    async def db_unavailable_handler(request: Request, exc: DatabaseUnavailableError):
        return JSONResponse(
            status_code=503,
            content={"detail": "Database is temporarily unavailable. Please retry later."},
            headers={"x-request-id": getattr(getattr(request, "state", object()), "request_id", "-")},
        )

    app.include_router(api_router)

    @app.on_event("startup")
    def on_startup():
        container.init_pool()

    @app.on_event("shutdown")
    def on_shutdown():
        container.shutdown_pool()

    return app


app = create_app()
