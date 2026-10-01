from contextlib import contextmanager
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

_pool: ConnectionPool | None = None


def abrir_pool() -> None:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=10, open=False,
                               kwargs={"row_factory": dict_row})
        _pool.open(wait=True, timeout=30)


def fechar_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def sessao(user_id: UUID | str | None = None):
    """Uma transação; se houver usuário, app.user_id é fixado (local à transação) e o RLS passa a valer para ele."""
    abrir_pool()
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            if user_id is not None:
                cur.execute("SELECT set_config('app.user_id', %s, true)", (str(user_id),))
            yield cur
