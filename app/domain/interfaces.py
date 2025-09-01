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