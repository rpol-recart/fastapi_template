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