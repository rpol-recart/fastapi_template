**новый модуль `SimilarityChecker`** (и другие сервисы) **использовал централизованный логгер**, включая:
- Поддержку `request_id`,
- JSON-формат (если включен),
- Корректное именование логгера (например, `app.SimilarityChecker`),
- Интеграцию с middleware, который прокидывает `request_id`.

---

### ✅ Цель
Сделать так, чтобы `SimilarityChecker` логировал события **с тем же контекстом**, что и остальные части приложения — особенно `request_id`, который устанавливается в middleware.

---

## ✅ Решение: передавать логгер через DI

Ты уже **передаёшь `logger` в сервисы через DI-контейнер** — это правильный подход. Нужно только убедиться, что:
1. Все сервисы получают **один и тот же корневой логгер** (`app`),
2. Используют `logger.getChild(...)` для структурированного логирования,
3. В `middleware` логгер вызывается с `extra={"request_id": ...}`.

---

### 📂 Шаг 1: Убедись, что логгер инициализирован в `AppContainer`

В `app/core/di.py` уже есть:

```python
class AppContainer:
    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._logger = logging.getLogger("app")  # ← Это корневой логгер
        # ...
```

✅ Отлично — все сервисы будут получать **один и тот же логгер**.

---

### 📂 Шаг 2: Передавай логгер в `SimilarityChecker`

#### `app/application/similarity/similarity_checker.py`
```python
from app.domain.interfaces import SimilarityChecker
import logging


class DefaultSimilarityChecker(SimilarityChecker):
    def __init__(self, logger: logging.Logger):
        self._log = logger.getChild("SimilarityChecker")  # ← Создаём child-логгер

    def check_similarity(self, user_id: int) -> float:
        self._log.info(
            "Starting similarity check",
            extra={"user_id": user_id, "stage": "start"}
        )

        # Пример логики
        try:
            score = 0.75 + (user_id % 10) * 0.01
            self._log.info(
                "Similarity check completed",
                extra={"user_id": user_id, "score": score}
            )
            return score
        except Exception as e:
            self._log.error(
                "Failed to compute similarity",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True
            )
            raise
```

---

### 📂 Шаг 3: Внедри логгер через DI-контейнер

#### `app/core/di.py` — обнови `similarity_checker` property:

```python
@property
def similarity_checker(self) -> SimilarityChecker:
    if self._similarity_checker is None:
        self._similarity_checker = DefaultSimilarityChecker(logger=self._logger)
    return self._similarity_checker
```

Теперь `DefaultSimilarityChecker` получает тот же логгер, что и всё приложение.

---

### ✅ Что ты получаешь:

| Фича | Реализовано? | Как |
|------|--------------|-----|
| JSON-логи | ✅ | Настроено в `core/logging.py` |
| `request_id` в логах | ✅ | Middleware передаёт `extra={"request_id": ...}` |
| Читаемые имена логгеров | ✅ | `app.SimilarityChecker` через `.getChild()` |
| Единый формат | ✅ | Централизованная настройка `logging.config.dictConfig` |

---

### 📂 Шаг 4: Проверь, что middleware прокидывает `request_id`

#### В `app/main.py` — middleware:

```python
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    logger = logging.getLogger("app")
    extra = {"request_id": request_id}
    
    # Логируем начало запроса
    logger.debug("Request started", extra=extra)

    response = await call_next(request)
    response.headers["x-request-id"] = request_id

    # Логируем завершение
    logger.debug("Request completed", extra=extra)
    return response
```

---

### ✅ Пример вывода лога (JSON):

```json
{
  "timestamp": "2025-04-05T12:34:56",
  "level": "INFO",
  "logger": "app.SimilarityChecker",
  "message": "Starting similarity check",
  "module": "similarity_checker",
  "func": "check_similarity",
  "line": 15,
  "request_id": "abc123",
  "user_id": 42,
  "stage": "start"
}
```

---

## 🔁 Дополнительно: если хочешь логировать **внутри CommandBus**

Уже есть:

```python
def execute(self, command: C, *, request_id: str | None = None) -> Any:
    self._log.info("Executing command", extra={"request_id": request_id or "-"})
    setattr(command, "request_id", request_id or "-")
    return handler(command)
```

Так что `request_id` будет доступен **всем хендлерам и сервисам**, если они его читают из команды (опционально).

---

## ✅ Итог

Чтобы использовать **централизованный логгер** в `SimilarityChecker`:

1. **Передавай `logger` из `AppContainer`** в конструктор,
2. Используй `logger.getChild("SimilarityChecker")` для структурирования,
3. Всегда логируй с `extra={...}`, особенно `request_id` (если нужен),
4. Middleware автоматически добавляет `request_id` в логи.

---

### 🧩 Совет: универсальный базовый класс (опционально)

Если у тебя много сервисов, можно создать:

```python
# app/application/base_service.py
import logging
from abc import ABC

class BaseService(ABC):
    def __init__(self, logger: logging.Logger, name: str):
        self._log = logger.getChild(name)
```

И использовать:

```python
class DefaultSimilarityChecker(BaseService):
    def __init__(self, logger: logging.Logger):
        super().__init__(logger, "SimilarityChecker")
```

---

Готово! Теперь **все твои модули логируют единообразно**, с `request_id`, в JSON, и легко отслеживаются в ELK, Grafana Loki и т.д. 🚀
