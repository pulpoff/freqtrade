import threading
from typing import Any


class SingletonMeta(type):
    """
    A thread-safe implementation of Singleton.
    Use as metaclass to create singleton classes.
    """

    _instances: dict = {}
    _lock: threading.Lock = threading.Lock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            with cls._lock:
                # Double-checked locking pattern
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]
