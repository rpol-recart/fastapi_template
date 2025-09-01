import logging
import time
import threading
from typing import Optional

import oracledb

from app.infrastructure.db.errors import DatabaseUnavailableError


def _extract_error_info(exc: Exception):
    # Возвращает (code, message) максимально безопасно
    code = None
    message = str(exc)
    if exc.args:
        err = exc.args[0]
        code = getattr(err, "code", None)
        message = getattr(err, "message", message)
    return code, message


def is_connection_error(exc: Exception) -> bool:
    # Набор распространённых кодов/паттернов, указывающих на потерю/отсутствие соединения
    if isinstance(exc, (oracledb.DatabaseError, oracledb.InterfaceError)):
        code, message = _extract_error_info(exc)
        conn_codes = {3113, 3114, 1012, 12514, 12541, 12545, 12537, 12547}
        if code in conn_codes:
            return True
        msg = (message or "").upper()
        # Подстрахуемся по подписи DPI/ORA
        if "DPI-" in msg or "DPY-" in msg or "ORA-125" in msg or "ORA-03113" in msg or "ORA-03114" in msg or "ORA-01012" in msg:
            return True
    return False


class OraclePool:
    """
    Обертка над oracledb pool с ретраями и сбросом при недоступности БД.
    """
    def __init__(
        self,
        user: str,
        password: str,
        dsn: str,
        min: int = 1,
        max: int = 5,
        increment: int = 1,
        encoding: str = "UTF-8",
        retry_attempts: int = 2,        # 2 повторные попытки (помимо первой)
        retry_delay: float = 0.2,       # пауза между попытками (сек)
    ):
        self._user = user
        self._password = password
        self._dsn = dsn
        self._min = min
        self._max = max
        self._increment = increment
        self._encoding = encoding

        self._retry_attempts = retry_attempts
        self._retry_delay = retry_delay

        self._pool: Optional[oracledb.ConnectionPool] = None
        self._lock = threading.Lock()
        self._log = logging.getLogger(__name__).getChild("OraclePool")

    def connect(self) -> None:
        # Потокобезопасное создание пула
        with self._lock:
            try:
                self._pool = oracledb.create_pool(
                    user=self._user,
                    password=self._password,
                    dsn=self._dsn,
                    min=self._min,
                    max=self._max,
                    increment=self._increment,
                    encoding=self._encoding,
                )
                self._log.info("Oracle pool connected")
            except Exception as e:
                self._pool = None
                self._log.error("Failed to create Oracle pool: %s", e)
                raise

    def _safe_close_pool(self) -> None:
        with self._lock:
            if self._pool is not None:
                try:
                    self._pool.close()
                except Exception as e:
                    self._log.warning("Error while closing Oracle pool: %s", e)
                finally:
                    self._pool = None
                    self._log.info("Oracle pool reset to None")

    def acquire(self):
        """
        Получить соединение с ретраями.
        - Если пул None — ленивая попытка connect().
        - При коннект-/сетевых ошибках — до 2 повторных попыток.
        - Если всё плохо — DatabaseUnavailableError (и пул сброшен).
        """
        last_exc: Optional[Exception] = None
        total_tries = 1 + self._retry_attempts  # первая + повторы
        for attempt in range(1, total_tries + 1):
            try:
                if self._pool is None:
                    self._log.debug("Pool is None -> connecting (attempt %d/%d)", attempt, total_tries)
                    self.connect()
                return self._pool.acquire()  # type: ignore[union-attr]
            except Exception as e:
                last_exc = e
                if is_connection_error(e):
                    self._log.warning("Connection error on acquire (attempt %d/%d): %s", attempt, total_tries, e)
                    self._safe_close_pool()  # сбросить пул и попробовать переподключиться
                    if attempt < total_tries:
                        time.sleep(self._retry_delay)
                        continue
                    # все попытки исчерпаны
                    raise DatabaseUnavailableError("Oracle database is unavailable") from e
                else:
                    # не коннект-ошибка: отдать наверх как есть
                    raise
        # Теоретически не дойдём, но на всякий случай:
        if last_exc:
            raise last_exc
        raise DatabaseUnavailableError("Oracle database is unavailable (unknown state)")

    def close(self) -> None:
        self._safe_close_pool()