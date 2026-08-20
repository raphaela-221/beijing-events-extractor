"""编辑锁：P0 内存单例。单用户单任务，服务重启即清（重启也杀了运行任务）。"""
from __future__ import annotations

from datetime import datetime
from threading import Lock


class LockManager:
    def __init__(self) -> None:
        self._holder: dict | None = None
        self._mux = Lock()

    def status(self) -> dict | None:
        with self._mux:
            return dict(self._holder) if self._holder else None

    def acquire(self, user: str) -> bool:
        with self._mux:
            if self._holder and self._holder["user"] != user:
                return False
            if not self._holder:
                self._holder = {
                    "user": user,
                    "since": datetime.now().isoformat(timespec="seconds"),
                }
            return True

    def release(self, user: str) -> bool:
        with self._mux:
            if self._holder and self._holder["user"] == user:
                self._holder = None
                return True
            return False

    def force_release(self) -> dict | None:
        """管理员强制释放（附录 B：release 仅持有者或管理员）。返回原持有者。"""
        with self._mux:
            prev = dict(self._holder) if self._holder else None
            self._holder = None
            return prev


lock = LockManager()
