import os
import sqlite3
from threading import RLock
from typing import Any


_raw_connect = sqlite3.connect
_connections: dict[str, "LockedConnection"] = {}
_locks: dict[str, RLock] = {}


class LockedCursor:
    def __init__(self, cursor: sqlite3.Cursor, lock: RLock):
        self._cursor = cursor
        self._lock = lock

    def execute(self, *args, **kwargs):
        with self._lock:
            return self._cursor.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        with self._lock:
            return self._cursor.executemany(*args, **kwargs)

    def fetchone(self):
        with self._lock:
            return self._cursor.fetchone()

    def fetchall(self):
        with self._lock:
            return self._cursor.fetchall()

    def fetchmany(self, *args, **kwargs):
        with self._lock:
            return self._cursor.fetchmany(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class LockedConnection:
    def __init__(self, conn: sqlite3.Connection, lock: RLock):
        self._conn = conn
        self._lock = lock

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"_conn", "_lock"}:
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)

    def cursor(self):
        return LockedCursor(self._conn.cursor(), self._lock)

    def execute(self, *args, **kwargs):
        with self._lock:
            return self._conn.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        with self._lock:
            return self._conn.executemany(*args, **kwargs)

    def commit(self):
        with self._lock:
            return self._conn.commit()

    def close(self):
        # Shared connections stay alive; no-op to avoid cross-cog breakage.
        return None

    def __enter__(self):
        self._lock.acquire()
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            return self._conn.__exit__(exc_type, exc, tb)
        finally:
            self._lock.release()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def connect(path: str, *args, **kwargs) -> sqlite3.Connection:
    path_str = str(path)
    if path_str == ":memory:":
        return _raw_connect(path_str, *args, **kwargs)

    key = os.path.abspath(path_str)
    if key in _connections:
        return _connections[key]

    kwargs.setdefault("timeout", 30.0)
    kwargs.setdefault("check_same_thread", False)
    conn = _raw_connect(path_str, *args, **kwargs)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.commit()

    lock = _locks.setdefault(key, RLock())
    locked = LockedConnection(conn, lock)
    _connections[key] = locked
    return locked


def patch_sqlite3() -> None:
    sqlite3.connect = connect


def close_all() -> None:
    for conn in _connections.values():
        try:
            conn._conn.close()
        except Exception:
            pass
    _connections.clear()
    _locks.clear()
