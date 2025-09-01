Ниже — минималистичный, но расширяемый шаблон FastAPI-приложения, построенный по SOLID с использованием DI. Выделены отдельные модули для конфигурации, логирования, работы с Oracle (oracledb), слой оркестровки (централизованная логика/CommandBus), интерфейсы домена и реализации репозиториев. На базе шаблона можно быстро развернуть приложения с другой бизнес-логикой, добавляя свои команды, хендлеры, сервисы и репозитории.

Структура проекта
- app/
  - main.py
  - api/
    - __init__.py
    - routes.py
    - dependencies.py
  - core/
    - __init__.py
    - config.py
    - logging.py
    - di.py
  - domain/
    - __init__.py
    - commands.py
    - interfaces.py
    - models.py
  - application/
    - __init__.py
    - orchestrator.py
    - services.py
    - unit_of_work.py
  - infrastructure/
    - __init__.py
    - db/
      - __init__.py
      - oracle.py
    - repositories/
      - __init__.py
      - user_repository_oracle.py
  - schemas/
    - __init__.py
    - user.py
- .env.example
- pyproject.toml (или requirements.txt)

Пример кода

pyproject.toml (вариант с poetry; можно заменить на requirements.txt)
```toml
[tool.poetry]
name = "fastapi-oracle-template"
version = "0.1.0"
description = "Шаблон FastAPI с SOLID, DI, oracledb, централизованной оркестрацией"
authors = ["You <you@example.com>"]
readme = "README.md"

[tool.poetry.dependencies]
python = "^3.10"
fastapi = "^0.115.0"
uvicorn = { extras = ["standard"], version = "^0.30.0" }
pydantic-settings = "^2.4.0"
oracledb = "^2.0.0"
python-dotenv = "^1.0.1"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0.0"
```

.env.example
```env
APP_NAME=fastapi-oracle-template
APP_ENV=dev
APP_HOST=0.0.0.0
APP_PORT=8000

LOG_LEVEL=INFO
LOG_JSON=true

ORACLE_USER=app_user
ORACLE_PASSWORD=secret
ORACLE_DSN=localhost:1521/ORCLPDB1
ORACLE_POOL_MIN=1
ORACLE_POOL_MAX=5
ORACLE_POOL_INC=1
```

app/core/config.py
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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
```

app/core/logging.py
```python
import logging
import logging.config
import os


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    is_json = str(json_format).lower() == "true"

    if is_json:
        fmt = (
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s",'
            '"message":"%(message)s","module":"%(module)s","func":"%(funcName)s","line":"%(lineno)d","request_id":"%(request_id)s"}'
        )
    else:
        fmt = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s (request_id=%(request_id)s)"

    class RequestIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if not hasattr(record, "request_id"):
                record.request_id = "-"
            return True

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {"default": {"format": fmt}},
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["request_id"],
                }
            },
            "root": {
                "handlers": ["default"],
                "level": level.upper(),
            },
        }
    )
```

app/core/di.py
```python
from __future__ import annotations
from typing import Optional
import logging

from app.core.config import AppSettings
from app.infrastructure.db.oracle import OraclePool
from app.infrastructure.repositories.user_repository_oracle import OracleUserRepository
from app.application.services import UserService
from app.application.orchestrator import CommandBus
from app.domain.commands import CreateUserCommand, GetUserCommand
from app.application.unit_of_work import SimpleUnitOfWork


class AppContainer:
    """
    Простейший контейнер зависимостей (DI). Можно заменить на external DI-фреймворк при желании.
    """
    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._logger = logging.getLogger("app")
        self._pool: Optional[OraclePool] = None

        # Будут лениво инициализироваться:
        self._user_repo = None
        self._user_service = None
        self._uow = None
        self._bus = None

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
            )
            self._pool.connect()
            self._logger.info("Oracle connection pool established")

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
            self._bus = CommandBus(logger=self._logger)
            # Регистрация хендлеров команд:
            self._bus.register(CreateUserCommand, self.user_service.handle_create_user)
            self._bus.register(GetUserCommand, self.user_service.handle_get_user)
        return self._bus
```

app/infrastructure/db/oracle.py
```python
import oracledb
from typing import Optional


class OraclePool:
    """
    Обертка над oracledb pool. Синхронный API (простой и надежный).
    Для асинхронного — см. документацию oracledb asyncio.
    """
    def __init__(self, user: str, password: str, dsn: str, min: int = 1, max: int = 5, increment: int = 1, encoding: str = "UTF-8"):
        self._user = user
        self._password = password
        self._dsn = dsn
        self._min = min
        self._max = max
        self._increment = increment
        self._encoding = encoding
        self._pool: Optional[oracledb.ConnectionPool] = None

    def connect(self) -> None:
        # THIN режим по умолчанию — установка клиента не требуется.
        self._pool = oracledb.create_pool(
            user=self._user,
            password=self._password,
            dsn=self._dsn,
            min=self._min,
            max=self._max,
            increment=self._increment,
            encoding=self._encoding,
        )

    def acquire(self) -> oracledb.Connection:
        if self._pool is None:
            raise RuntimeError("Pool is not initialized")
        return self._pool.acquire()

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None
```

app/domain/interfaces.py
```python
from abc import ABC, abstractmethod
from typing import Optional
from app.domain.models import User


class UserRepository(ABC):
    @abstractmethod
    def create_user(self, username: str, email: str) -> User:
        ...

    @abstractmethod
    def get_user(self, user_id: int) -> Optional[User]:
        ...
```

app/domain/models.py
```python
from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    id: int
    username: str
    email: str
```

app/domain/commands.py
```python
from dataclasses import dataclass


class Command:
    """Базовый класс для команд (маркер)."""
    pass


@dataclass
class CreateUserCommand(Command):
    username: str
    email: str


@dataclass
class GetUserCommand(Command):
    user_id: int
```

app/infrastructure/repositories/user_repository_oracle.py
```python
from typing import Optional
from app.domain.interfaces import UserRepository
from app.infrastructure.db.oracle import OraclePool
from app.domain.models import User


class OracleUserRepository(UserRepository):
    """
    Пример реализации репозитория для Oracle.
    Таблица для примера: USERS(id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, username VARCHAR2(100), email VARCHAR2(200))
    """
    def __init__(self, pool: OraclePool):
        self._pool = pool

    def create_user(self, username: str, email: str) -> User:
        conn = self._pool.acquire()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO USERS (username, email) VALUES (:username, :email) RETURNING id INTO :id",
                    {"username": username, "email": email, "id": cur.var(int)},
                )
                new_id = cur.getimplicitresults()
                # В зависимости от версии драйвера/БД может отличаться способ получения id.
                # Универсальный подход:
                # rid = cur.var(oracledb.NUMBER)
                # cur.execute("INSERT ... RETURNING id INTO :rid", {"rid": rid, ...})
                # new_id = int(rid.getvalue())
                conn.commit()
            # Заглушка для демонстрации: если RETURNING сложен, можно получить seq/identity и сделать SELECT currval аналогом.
            if not new_id:
                # fallback: достать последний вставленный id — только как пример, лучше RETURNING.
                with conn.cursor() as cur:
                    cur.execute("SELECT MAX(id) FROM USERS")
                    row = cur.fetchone()
                    new_id = row[0]
            return User(id=int(new_id), username=username, email=email)
        finally:
            conn.close()

    def get_user(self, user_id: int) -> Optional[User]:
        conn = self._pool.acquire()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, username, email FROM USERS WHERE id = :id", {"id": user_id})
                row = cur.fetchone()
                if not row:
                    return None
                return User(id=int(row[0]), username=row[1], email=row[2])
        finally:
            conn.close()
```

Примечание: извлечение id через RETURNING может отличаться по синтаксису в зависимости от версии драйвера oracledb. При необходимости настройте участок с RETURNING и cur.var(...) согласно вашей версии.

app/application/unit_of_work.py
```python
from typing import Optional
from app.infrastructure.db.oracle import OraclePool


class SimpleUnitOfWork:
    """
    Простой UoW для управления транзакциями вручную, если нужно выполнить несколько операций атомарно.
    Пример: with uow.transaction() as conn: ...
    """
    def __init__(self, pool: OraclePool):
        self._pool = pool

    def transaction(self):
        return _Transaction(self._pool)


class _Transaction:
    def __init__(self, pool: OraclePool):
        self._pool = pool
        self._conn = None

    def __enter__(self):
        self._conn = self._pool.acquire()
        self._conn.autocommit = False
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
```

app/application/services.py
```python
from typing import Optional
import logging
from app.domain.interfaces import UserRepository
from app.domain.models import User
from app.domain.commands import CreateUserCommand, GetUserCommand
from app.application.unit_of_work import SimpleUnitOfWork


class UserService:
    """
    Сервис уровня приложения. Не знает о веб/HTTP, orchestrator дергает его хендлеры.
    Зависит от абстракций (интерфейсов), конкретика подставляется DI-контейнером.
    """

    def __init__(self, user_repo: UserRepository, uow: SimpleUnitOfWork, logger: logging.Logger):
        self._user_repo = user_repo
        self._uow = uow
        self._log = logger.getChild("UserService")

    # Хендлеры команд:
    def handle_create_user(self, cmd: CreateUserCommand) -> User:
        self._log.info("Handling CreateUserCommand", extra={"request_id": getattr(cmd, "request_id", "-")})
        # Если нужна транзакция на несколько операций — используйте uow.transaction()
        user = self._user_repo.create_user(username=cmd.username, email=cmd.email)
        return user

    def handle_get_user(self, cmd: GetUserCommand) -> Optional[User]:
        self._log.info("Handling GetUserCommand", extra={"request_id": getattr(cmd, "request_id", "-")})
        return self._user_repo.get_user(user_id=cmd.user_id)
```

app/application/orchestrator.py
```python
from typing import Any, Callable, Dict, Type, TypeVar
import logging
from app.domain.commands import Command

C = TypeVar("C", bound=Command)


class CommandBus:
    """
    Централизованный оркестратор. Регистрирует хендлеры для команд и исполняет их.
    Позволяет наращивать логику, не меняя слой API.
    """

    def __init__(self, logger: logging.Logger):
        self._handlers: Dict[Type[Command], Callable[[Any], Any]] = {}
        self._log = logger.getChild("CommandBus")

    def register(self, command_type: Type[C], handler: Callable[[C], Any]) -> None:
        if command_type in self._handlers:
            raise ValueError(f"Handler for {command_type.__name__} already registered")
        self._handlers[command_type] = handler

    def execute(self, command: C, *, request_id: str | None = None) -> Any:
        handler = self._handlers.get(type(command))
        if handler is None:
            raise ValueError(f"No handler registered for command {type(command).__name__}")
        self._log.info("Executing command", extra={"request_id": request_id or "-"})
        # Дополнительно можно прокинуть request_id внутрь команды
        setattr(command, "request_id", request_id or "-")
        return handler(command)
```

app/schemas/user.py
```python
from pydantic import BaseModel, EmailStr


class CreateUserIn(BaseModel):
    username: str
    email: EmailStr


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
```

app/api/dependencies.py
```python
from fastapi import Request
from app.core.di import AppContainer
from app.application.orchestrator import CommandBus


def get_container(request: Request) -> AppContainer:
    return request.app.state.container  # type: ignore[attr-defined]


def get_command_bus(request: Request) -> CommandBus:
    return get_container(request).command_bus
```

app/api/routes.py
```python
from fastapi import APIRouter, Depends, Header
from typing import Optional
from app.schemas.user import CreateUserIn, UserOut
from app.application.orchestrator import CommandBus
from app.domain.commands import CreateUserCommand, GetUserCommand
from app.api.dependencies import get_command_bus

router = APIRouter(prefix="/api", tags=["api"])


@router.post("/users", response_model=UserOut)
def create_user(payload: CreateUserIn, bus: CommandBus = Depends(get_command_bus), x_request_id: Optional[str] = Header(default=None)):
    cmd = CreateUserCommand(username=payload.username, email=payload.email)
    result = bus.execute(cmd, request_id=x_request_id)
    return UserOut(id=result.id, username=result.username, email=result.email)


@router.get("/users/{user_id}", response_model=UserOut | None)
def get_user(user_id: int, bus: CommandBus = Depends(get_command_bus), x_request_id: Optional[str] = Header(default=None)):
    cmd = GetUserCommand(user_id=user_id)
    result = bus.execute(cmd, request_id=x_request_id)
    if result is None:
        return None
    return UserOut(id=result.id, username=result.username, email=result.email)
```

app/main.py
```python
from fastapi import FastAPI, Request
from app.core.config import AppSettings
from app.core.logging import setup_logging
from app.core.di import AppContainer
from app.api.routes import router as api_router
import logging
import uuid


def create_app() -> FastAPI:
    settings = AppSettings()
    setup_logging(level=settings.log_level, json_format=settings.log_json)

    app = FastAPI(title=settings.app_name)

    # DI контейнер
    container = AppContainer(settings=settings)
    app.state.container = container  # type: ignore[attr-defined]

    # Middleware для request_id
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        # Прокинем request_id в логгер через адаптер
        logger = logging.getLogger("app")
        extra = {"request_id": request_id}
        request.state.request_id = request_id  # type: ignore[attr-defined]
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        # можно добавить access log здесь при желании
        logger.debug("Request processed", extra=extra)
        return response

    # Роуты
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

Как расширять шаблон
- Новая бизнес-логика:
  - Добавьте новый Command в app/domain/commands.py.
  - В application/services.py создайте метод-хендлер для команды. Сервис обращается к интерфейсам домена и/или UoW.
  - Зарегистрируйте хендлер в контейнере (core/di.py) на CommandBus.
  - Привяжите маршрут в app/api/routes.py, который создает команду и отправляет в CommandBus.

- Работа с БД:
  - Описывайте интерфейсы репозиториев в app/domain/interfaces.py.
  - Делайте конкретные реализации в app/infrastructure/repositories/*.py на основе app/infrastructure/db/oracle.py.
  - При необходимости используйте UnitOfWork для транзакций между несколькими репозиториями.

- Конфигурация:
  - Все настройки — через AppSettings (pydantic-settings) и .env.
  - Параметры логирования и пула БД настраиваются через переменные окружения.

- Логирование:
  - Централизованная настройка через core/logging.setup_logging.
  - Пример добавления request_id через middleware.
  - Логгеры сервисов и оркестратора получают child-логгер.

Запуск
- Установите зависимости:
  - poetry install
  - либо pip install fastapi uvicorn pydantic-settings oracledb python-dotenv
- Подготовьте БД и таблицу USERS:
  - Пример:
    - CREATE TABLE USERS (id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, username VARCHAR2(100), email VARCHAR2(200));
- Скопируйте .env.example в .env и заполните.
- Запуск:
  - uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Пояснения по SOLID и DI в шаблоне
- Single Responsibility: каждый модуль выполняет свою роль (config, logging, db, repositories, services, orchestrator, api).
- Open/Closed: добавление новой логики через новые команды и хендлеры без изменения существующих классов.
- Liskov: интерфейсы домена (репозитории) и их реализации взаимозаменяемы.
- Interface Segregation: репозитории объявлены минимально необходимыми методами.
- Dependency Inversion: верхние уровни (сервисы/оркестратор) зависят от абстракций (интерфейсов), конкретные реализации поставляет DI-контейнер (core/di.py).

Заметки
- oracledb: пример с RETURNING может потребовать корректировки под вашу версию драйвера/БД. Если нужно — используйте cur.var(...) и извлекайте значение явно.
- Асинхронность: показан синхронный доступ к БД через пул. Для высокой нагрузки можно:
  - выполнить синхронный репозиторий в threadpool (FastAPI делает это автоматически, если endpoint — def, а не async def), либо
  - перейти на asyncio API oracledb и реализовать async-репозитории/пул.

Готово: вы получили каркас, в котором API слой отправляет команды в централизованный оркестратор, тот вызывает сервисы, а сервисы — абстракции доменного уровня с конкретными реализациями, подставляемыми DI-контейнером. Это позволяет быстро менять бизнес-логику, не затрагивая инфраструктурную часть.