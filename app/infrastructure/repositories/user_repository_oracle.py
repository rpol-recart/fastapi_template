from typing import Optional
from app.domain.interfaces import UserRepository
from app.infrastructure.db.oracle import OraclePool, is_connection_error
from app.domain.models import User
from app.infrastructure.db.errors import DatabaseUnavailableError


class OracleUserRepository(UserRepository):
    def __init__(self, pool: OraclePool):
        self._pool = pool

    def create_user(self, username: str, email: str) -> User:
        conn = self._pool.acquire()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO USERS (username, email) VALUES (:username, :email) RETURNING id INTO :rid",
                    {"username": username, "email": email, "rid": cur.var(int)},
                )
                rid = cur.getimplicitresults()
                conn.commit()
            if not rid:
                with conn.cursor() as cur:
                    cur.execute("SELECT MAX(id) FROM USERS")
                    row = cur.fetchone()
                    rid = row[0]
            return User(id=int(rid), username=username, email=email)
        except Exception as e:
            # Если это проблема с соединением — сбросить пул и отдать 503
            if is_connection_error(e):
                self._pool.close()
                raise DatabaseUnavailableError("Oracle database is unavailable") from e
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def get_user(self, user_id: int) -> Optional[User]:
        conn = self._pool.acquire()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, username, email FROM USERS WHERE id = :id", {"id": user_id})
                row = cur.fetchone()
                if not row:
                    return None
                return User(id=int(row[0]), username=row[1], email=row[2])
        except Exception as e:
            if is_connection_error(e):
                self._pool.close()
                raise DatabaseUnavailableError("Oracle database is unavailable") from e
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass
            