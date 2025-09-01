
### ✅ Цель
Добавить эндпоинт `/advanced_users`, который:
1. Создаёт пользователя в БД,
2. Выполняет расчёт (`Calculate`),
3. Проверяет схожесть (`Similarity`),
4. Формирует `AdvancedUserOut`.

---

## 🧱 Шаг 1: Расширь структуру

Добавим новые модули:

```
app/
  domain/
    commands.py
    interfaces.py
    models.py
  application/
    services.py
    calculators/
      calculator.py
    similarity/
      similarity_checker.py
  schemas/
    advanced_user.py
```

---

## 🧩 Шаг 2: Добавь новые модели и команды

### `app/domain/models.py`
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class User:
    id: int
    username: str
    email: str

@dataclass(frozen=True)
class AdvancedUser:
    id: int
    username: str
    email: str
    value: float  # например, результат расчёта
    similarity_score: float
```

---

### `app/domain/commands.py`
```python
from dataclasses import dataclass

class Command:
    pass

@dataclass
class CreateUserCommand(Command):
    username: str
    email: str

@dataclass
class GetSimilarityCommand(Command):
    user_id: int

@dataclass
class CalculateValueCommand(Command):
    user_id: int

@dataclass
class CreateAdvancedUserCommand(Command):
    username: str
    email: str
```

---

## 📦 Шаг 3: Интерфейсы для новых сервисов

### `app/domain/interfaces.py`
```python
from abc import ABC, abstractmethod
from app.domain.models import User, AdvancedUser


class UserRepository(ABC):
    @abstractmethod
    def create_user(self, username: str, email: str) -> User:
        ...

    @abstractmethod
    def get_user(self, user_id: int) -> User | None:
        ...


class CalculatorService(ABC):
    @abstractmethod
    def calculate(self, user_id: int) -> float:
        ...


class SimilarityChecker(ABC):
    @abstractmethod
    def check_similarity(self, user_id: int) -> float:
        ...
```

---

## 🔧 Шаг 4: Реализуй сервисы

### `app/application/calculators/calculator.py`
```python
from app.domain.interfaces import CalculatorService
import logging


class DefaultCalculator(CalculatorService):
    def __init__(self, logger: logging.Logger):
        self._log = logger.getChild("Calculator")

    def calculate(self, user_id: int) -> float:
        self._log.info("Calculating value for user", extra={"user_id": user_id})
        # Здесь может быть вызов ML-модели, внешнего API, сложная формула и т.д.
        return float(user_id * 1.5)  # пример
```

---

### `app/application/similarity/similarity_checker.py`
```python
from app.domain.interfaces import SimilarityChecker
import logging


class DefaultSimilarityChecker(SimilarityChecker):
    def __init__(self, logger: logging.Logger):
        self._log = logger.getChild("SimilarityChecker")

    def check_similarity(self, user_id: int) -> float:
        self._log.info("Checking similarity for user", extra={"user_id": user_id})
        # Пример: сравнение с другими пользователями
        return 0.75 + (user_id % 10) * 0.01  # имитация
```

---

## 🧠 Шаг 5: Новый сервис — `AdvancedUserService`

### `app/application/services.py` (дополни)
```python
from typing import Optional
import logging
from app.domain.interfaces import UserRepository, CalculatorService, SimilarityChecker
from app.domain.models import User, AdvancedUser
from app.domain.commands import CreateAdvancedUserCommand, CalculateValueCommand, GetSimilarityCommand
from app.application.unit_of_work import SimpleUnitOfWork


class AdvancedUserService:
    def __init__(
        self,
        user_repo: UserRepository,
        calculator: CalculatorService,
        similarity_checker: SimilarityChecker,
        uow: SimpleUnitOfWork,
        logger: logging.Logger,
    ):
        self._user_repo = user_repo
        self._calculator = calculator
        self._similarity_checker = similarity_checker
        self._uow = uow
        self._log = logger.getChild("AdvancedUserService")

    def handle_create_advanced_user(self, cmd: CreateAdvancedUserCommand) -> AdvancedUser:
        self._log.info("Handling CreateAdvancedUserCommand")
        with self._uow.transaction() as conn:
            try:
                # Шаг 1: создать пользователя
                user = self._user_repo.create_user(username=cmd.username, email=cmd.email)
                self._log.info("User created", extra={"user_id": user.id})

                # Шаг 2: расчёт
                value = self._calculator.calculate(user.id)
                self._log.info("Value calculated", extra={"value": value})

                # Шаг 3: проверка схожести
                similarity_score = self._similarity_checker.check_similarity(user.id)
                self._log.info("Similarity checked", extra={"score": similarity_score})

                # Шаг 4: собрать итоговый объект
                result = AdvancedUser(
                    id=user.id,
                    username=user.username,
                    email=user.email,
                    value=value,
                    similarity_score=similarity_score,
                )
                return result
            except Exception as e:
                self._log.error("Failed to create advanced user", exc_info=True)
                raise
```

---

## 🔌 Шаг 6: Обнови DI-контейнер (`app/core/di.py`)

Добавь новые зависимости:

```python
# Внутри AppContainer
def __init__(self, settings: AppSettings):
    # ... существующие поля
    self._calculator = None
    self._similarity_checker = None
    self._advanced_service = None

# Свойства
@property
def calculator(self) -> CalculatorService:
    if self._calculator is None:
        self._calculator = DefaultCalculator(logger=self._logger)
    return self._calculator

@property
def similarity_checker(self) -> SimilarityChecker:
    if self._similarity_checker is None:
        self._similarity_checker = DefaultSimilarityChecker(logger=self._logger)
    return self._similarity_checker

@property
def advanced_service(self) -> AdvancedUserService:
    if self._advanced_service is None:
        self._advanced_service = AdvancedUserService(
            user_repo=self.user_repository,
            calculator=self.calculator,
            similarity_checker=self.similarity_checker,
            uow=self.unit_of_work,
            logger=self._logger,
        )
    return self._advanced_service

@property
def command_bus(self) -> CommandBus:
    if self._bus is None:
        self._bus = CommandBus(logger=self._logger)
        # ... существующие регистрации
        self._bus.register(CreateUserCommand, self.user_service.handle_create_user)
        self._bus.register(GetUserCommand, self.user_service.handle_get_user)

        # ➕ Новая регистрация:
        self._bus.register(CreateAdvancedUserCommand, self.advanced_service.handle_create_advanced_user)
    return self._bus
```

---

## 📐 Шаг 7: Схема ответа

### `app/schemas/advanced_user.py`
```python
from pydantic import BaseModel, EmailStr


class AdvancedUserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    value: float
    similarity_score: float
```

---

## 🌐 Шаг 8: Новый роут

### `app/api/routes.py` (дополни)
```python
from fastapi import APIRouter, Depends, Header
from typing import Optional
from app.schemas.user import CreateUserIn
from app.schemas.advanced_user import AdvancedUserOut
from app.application.orchestrator import CommandBus
from app.domain.commands import CreateAdvancedUserCommand
from app.api.dependencies import get_command_bus

router = APIRouter(prefix="/api", tags=["api"])

# ... существующие роуты

@router.post("/advanced_users", response_model=AdvancedUserOut)
def create_advanced_user(
    payload: CreateUserIn,
    bus: CommandBus = Depends(get_command_bus),
    x_request_id: Optional[str] = Header(default=None),
):
    cmd = CreateAdvancedUserCommand(username=payload.username, email=payload.email)
    result = bus.execute(cmd, request_id=x_request_id)
    return AdvancedUserOut(
        id=result.id,
        username=result.username,
        email=result.email,
        value=result.value,
        similarity_score=result.similarity_score,
    )
```

---

## ✅ Что получилось?

Теперь при вызове `POST /api/advanced_users` происходит:

1. Команда `CreateAdvancedUserCommand` → попадает в `CommandBus`.
2. `CommandBus` вызывает `AdvancedUserService.handle_create_advanced_user`.
3. Внутри метода:
   - Создаётся пользователь (через `UserRepository`),
   - Выполняется расчёт (`CalculatorService`),
   - Проверяется схожесть (`SimilarityChecker`),
   - Все операции в одной транзакции (благодаря `UoW`),
   - Формируется `AdvancedUser`.

---

## 🔮 Дальнейшее развитие

- Можно сделать `CalculatorService` и `SimilarityChecker` асинхронными, если используют API.
- Добавить кэширование через `Redis` (новый репозиторий/сервис).
- Вынести `CommandBus` в отдельный слой с middleware (например, логирование, метрики, таймауты).
- Добавить `QueryBus` для read-операций (CQRS).
- Использовать `pydantic` для валидации входных данных в сервисах.

---

## 🚀 Запуск

Убедись, что:
- БД запущена, таблица `USERS` создана,
- `.env` заполнен,
- Зависимости установлены.

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Тест:
```bash
curl -X POST http://localhost:8000/api/advanced_users \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com"}'
```
