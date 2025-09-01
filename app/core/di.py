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
    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._logger = logging.getLogger("app")
        self._pool: Optional[OraclePool] = None

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
                retry_attempts=self._settings.oracle_retry_attempts,
                retry_delay=self._settings.oracle_retry_delay_ms / 1000.0,
            )
            # Пытаемся подключиться, но не падаем, если БД недоступна: подключимся лениво при первом запросе
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
            self._bus = CommandBus(logger=self._logger)
            self._bus.register(CreateUserCommand, self.user_service.handle_create_user)
            self._bus.register(GetUserCommand, self.user_service.handle_get_user)
        return self._bus
    