import hashlib
from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from app.core.config import settings

_attempts: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _key(ip: str, identifier: str) -> str:
    return hashlib.sha256(f"{ip}|{identifier.strip().casefold()}".encode()).hexdigest()


def check_login_rate_limit(ip: str, identifier: str) -> bool:
    cutoff = monotonic() - settings.auth_rate_limit_window_seconds
    key = _key(ip, identifier)
    with _lock:
        events = _attempts[key]
        while events and events[0] < cutoff:
            events.popleft()
        return len(events) < settings.auth_rate_limit_attempts


def record_login_failure(ip: str, identifier: str) -> None:
    with _lock:
        _attempts[_key(ip, identifier)].append(monotonic())


def clear_login_failures(ip: str, identifier: str) -> None:
    with _lock:
        _attempts.pop(_key(ip, identifier), None)
