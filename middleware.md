Ниже — вынос CommandBus в отдельный слой mediator с поддержкой цепочки middleware (логирование, метрики, таймауты) и интеграция в DI/приложение.

Что получаем
- Новый слой app/mediator с:
  - гибким CommandBus и add_middleware(...)
  - middleware: LoggingMiddleware, MetricsMiddleware, TimeoutMiddleware
  - ошибки: CommandTimeoutError (отдаём 504)
- Контейнер регистрирует хендлеры и включает middleware.
- Совместимо с текущим синхронным кодом.

Структура (новые/обновлённые файлы)
- app/
  - mediator/
    - __init__.py
    - bus.py
    - middleware.py
    - errors.py
- app/core/config.py (новые параметры таймаута)
- app/core/di.py (используем новый CommandBus и включаем middleware)
- app/api/dependencies.py (импорт из mediator)
- app/main.py (handler на 504)

1) Новый файл: app/mediator/errors.py
```python
class CommandTimeoutError(TimeoutError):
    """Команда превысила допустимое время выполнения."""
    pass
```

2) Новый файл: app/mediator/middleware.py
```python
from __future__ import annotations
import time
import logging
from typing import Any, Callable, Protocol
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from app.domain.commands import Command
from app.mediator.errors import CommandTimeoutError


class Middleware(Protocol):
    def __call__(self, command: Command, next_: Callable[[Command], Any]) -> Any: ...


class LoggingMiddleware:
    def __init__(self, logger: logging.Logger):
        self._log = logger.getChild("CommandBus")

    def __call__(self, command: Command, next_: Callable[[Command], Any]) -> Any:
        name = type(command).__name__
        req_id = getattr(command, "request_id", "-")
        start = time.perf_counter()
        try:
            self._log.info("Command start: %s", name, extra={"request_id": req_id})
            result = next_(command)
            dur_ms = (time.perf_counter() - start) * 1000
            self._log.info("Command ok: %s (%.2f ms)", name, dur_ms, extra={"request_id": req_id})
            return result
        except Exception as e:
            dur_ms = (time.perf_counter() - start) * 1000
            self._log.exception("Command failed: %s (%.2f ms): %s", name, dur_ms, e, extra={"request_id": req_id})
            raise


class Metrics:
    """Минимальный интерфейс метрик. Подключите адаптер под вашу систему метрик."""
    def inc_requests(self, command_name: str) -> None: ...
    def inc_errors(self, command_name: str) -> None: ...
    def observe_duration(self, command_name: str, seconds: float) -> None: ...


class NoopMetrics(Metrics):
    def inc_requests(self, command_name: str) -> None: ...
    def inc_errors(self, command_name: str) -> None: ...
    def observe_duration(self, command_name: str, seconds: float) -> None: ...


class MetricsMiddleware:
    def __init__(self, metrics: Metrics):
        self._m = metrics

    def __call__(self, command: Command, next_: Callable[[Command], Any]) -> Any:
        name = type(command).__name__
        self._m.inc_requests(name)
        start = time.perf_counter()
        try:
            result = next_(command)
            return result
        except Exception:
            self._m.inc_errors(name)
            raise
        finally:
            self._m.observe_duration(name, time.perf_counter() - start)


class TimeoutMiddleware:
    """Ограничивает время выполнения хендлера команды (кроссплатформенно через поток)."""
    def __init__(self, timeout_seconds: float):
        self._timeout = timeout_seconds

    def __call__(self, command: Command, next_: Callable[[Command], Any]) -> Any:
        # Выполняем хендлер в отдельном потоке, ждём результат с таймаутом
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(next_, command)
            try:
                return fut.result(timeout=self._timeout)
            except FuturesTimeoutError as e:
                # Поток-хендлер может продолжать выполнение в фоне, но результат уже не ждём.
                raise CommandTimeoutError(f"Command timed out after {self._timeout:.3f}s") from e
```

(Опционально можно добавить адаптер для prometheus_client — при необходимости.)

3) Новый файл: app/mediator/bus.py
```python
from __future__ import annotations
from typing import Any, Callable, Dict, List, Type, TypeVar
import logging

from app.domain.commands import Command
from app.mediator.middleware import Middleware

C = TypeVar("C", bound=Command)


class CommandBus:
    """
    Командный шина с поддержкой middleware (pipeline).
    Middleware вызываются в порядке добавления (add_middleware).
    """

    def __init__(self, logger: logging.Logger):
        self._handlers: Dict[Type[Command], Callable[[Any], Any]] = {}
        self._middlewares: List[Middleware] = []
        self._log = logger.getChild("CommandBus")

    def register(self, command_type: Type[C], handler: Callable[[C], Any]) -> None:
        if command_type in self._handlers:
            raise ValueError(f"Handler for {command_type.__name__} already registered")
        self._handlers[command_type] = handler

    def add_middleware(self, middleware: Middleware) -> None:
        self._middlewares.append(middleware)

    def execute(self, command: C, *, request_id: str | None = None) -> Any:
        handler = self._handlers.get(type(command))
        if handler is None:
            raise ValueError(f"No handler registered for command {type(command).__name__}")
        # Прокидываем request_id внутрь команды
        setattr(command, "request_id", request_id or "-")

        # Собираем pipeline: handler завернутый цепочкой middleware
        def call_handler(cmd: Command) -> Any:
            return handler(cmd)  # type: ignore[arg-type]

        wrapped = call_handler
        for mw in reversed(self._middlewares):
            next_ = wrapped
            def wrapper(cmd: Command, _mw=mw, _n=next_):
                return _mw(cmd, _n)
            wrapped = wrapper

        return wrapped(command)
```

4) Обновление: app/core/config.py (добавим таймаут команд)
```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class AppSettings(BaseSettings):
    app_name: str = Field(default="fastapi-oracle-template", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_json: bool = Field(default=True, alias="LOG_JSON")

    oracle_user: str = Field(alias="ORACLE_USER")
    oracle_password: str = Field(alias="ORACLE_PASSWORD")
    oracle_dsn: str = Field(alias="ORACLE_DSN")
    oracle_pool_min: int = Field(default=1, alias="ORACLE_POOL_MIN")
    oracle_pool_max: int = Field(default=5, alias="ORACLE_POOL_MAX")
    oracle_pool_inc: int = Field(default=1, alias="ORACLE_POOL_INC")

    # Отказоустойчивость БД (если уже добавляли ранее)
    oracle_retry_attempts: int = Field(default=2, alias="ORACLE_RETRY_ATTEMPTS")
    oracle_retry_delay_ms: int = Field(default=200, alias="ORACLE_RETRY_DELAY_MS")

    # Таймауты команд (для TimeoutMiddleware)
    command_timeout_ms: int = Field(default=3000, alias="COMMAND_TIMEOUT_MS")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
```

5) Обновление: .env.example
```env
# Таймаут команд, мс
COMMAND_TIMEOUT_MS=3000
```

6) Обновление: app/core/di.py (используем новый слой mediator и включаем middleware)
```python
from __future__ import annotations
from typing import Optional
import logging

from app.core.config import AppSettings
from app.infrastructure.db.oracle import OraclePool
from app.infrastructure.repositories.user_repository_oracle import OracleUserRepository
from app.application.services import UserService
from app.domain.commands import CreateUserCommand, GetUserCommand
from app.application.unit_of_work import SimpleUnitOfWork

from app.mediator.bus import CommandBus
from app.mediator.middleware import LoggingMiddleware, MetricsMiddleware, TimeoutMiddleware, NoopMetrics


class AppContainer:
    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._logger = logging.getLogger("app")
        self._pool: Optional[OraclePool] = None

        self._user_repo = None
        self._user_service = None
        self._uow = None
        self._bus: Optional[CommandBus] = None

    @property
    def settings(self) -> AppSettings:
        return self._settings

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    def init_pool(self) -> None:
        if self._pool is None:
            self._pool = OraclePool(
                user=self._settings.oracle_user,
                password=self._settings.oracle_password,
                dsn=self._settings.oracle_dsn,
                min=self._settings.oracle_pool_min,
                max=self._settings.oracle_pool_max,
                increment=self._settings.oracle_pool_inc,
                retry_attempts=self._settings.oracle_retry_attempts,
                retry_delay=self._settings.oracle_retry_delay_ms / 1000.0,
            )
            try:
                self._pool.connect()
                self._logger.info("Oracle connection pool established")
            except Exception as e:
                self._logger.error("Oracle pool init failed at startup (will retry on demand): %s", e)

    def shutdown_pool(self) -> None:
        if self._pool:
            self._pool.close()
            self._logger.info("Oracle connection pool closed")
            self._pool = None

    @property
    def user_repository(self) -> OracleUserRepository:
        if self._user_repo is None:
            if self._pool is None:
                raise RuntimeError("DB pool is not initialized")
            self._user_repo = OracleUserRepository(self._pool)
        return self._user_repo

    @property
    def unit_of_work(self) -> SimpleUnitOfWork:
        if self._uow is None:
            if self._pool is None:
                raise RuntimeError("DB pool is not initialized")
            self._uow = SimpleUnitOfWork(self._pool)
        return self._uow

    @property
    def user_service(self) -> UserService:
        if self._user_service is None:
            self._user_service = UserService(user_repo=self.user_repository, uow=self.unit_of_work, logger=self._logger)
        return self._user_service

    @property
    def command_bus(self) -> CommandBus:
        if self._bus is None:
            bus = CommandBus(logger=self._logger)
            # Middleware: порядок имеет значение (Logging -> Metrics -> Timeout -> Handler)
            bus.add_middleware(LoggingMiddleware(self._logger))
            bus.add_middleware(MetricsMiddleware(NoopMetrics()))
            bus.add_middleware(TimeoutMiddleware(timeout_seconds=self._settings.command_timeout_ms / 1000.0))

            # Регистрация хендлеров команд
            bus.register(CreateUserCommand, self.user_service.handle_create_user)
            bus.register(GetUserCommand, self.user_service.handle_get_user)
            self._bus = bus
        return self._bus
```

7) Обновление: app/api/dependencies.py (импорт из mediator)
```python
from fastapi import Request
from app.core.di import AppContainer
from app.mediator.bus import CommandBus


def get_container(request: Request) -> AppContainer:
    return request.app.state.container  # type: ignore[attr-defined]


def get_command_bus(request: Request) -> CommandBus:
    return get_container(request).command_bus
```

8) Обновление: app/main.py (обработчик 504)
```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.config import AppSettings
from app.core.logging import setup_logging
from app.core.di import AppContainer
from app.api.routes import router as api_router
from app.infrastructure.db.errors import DatabaseUnavailableError
from app.mediator.errors import CommandTimeoutError
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
            logger.debug("Request processed", extra=extra)
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(DatabaseUnavailableError)
    async def db_unavailable_handler(request: Request, exc: DatabaseUnavailableError):
        return JSONResponse(
            status_code=503,
            content={"detail": "Database is temporarily unavailable. Please retry later."},
            headers={"x-request-id": getattr(getattr(request, "state", object()), "request_id", "-")},
        )

    @app.exception_handler(CommandTimeoutError)
    async def command_timeout_handler(request: Request, exc: CommandTimeoutError):
        return JSONResponse(
            status_code=504,
            content={"detail": "Command execution timed out."},
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
```

Примечания и рекомендации
- Порядок middleware важен. Предлагаемый порядок:
  - LoggingMiddleware — наружный слой: фиксирует старт/результат, длительность и ошибки.
  - MetricsMiddleware — считает количество запросов/ошибок и длительность.
  - TimeoutMiddleware — ограничивает время выполнения хендлера.
- При необходимости подключите реальную систему метрик. Для Prometheus можно написать адаптер на базе prometheus_client (Counter/Histogram) и передать в MetricsMiddleware вместо NoopMetrics.
- Старый файл app/application/orchestrator.py можно удалить (или оставить как thin-обёртку, перенаправляющую в новый mediator).
- Таймауты и отказоустойчивость БД дополняют друг друга: при зависаниях в хендлере вернётся 504, при недоступности БД — 503, пул сбросится и инициализируется заново на следующем запросе.