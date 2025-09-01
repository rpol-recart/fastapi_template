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