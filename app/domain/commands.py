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