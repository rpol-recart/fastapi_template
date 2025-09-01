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