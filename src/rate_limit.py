"""进程内滑动窗口限流（登录/注册）。

限制：
- 单进程内存实现，重启清零；当前 systemd 单 uvicorn 进程够用。
- 多 worker / 多机部署前必须换成 Redis 或数据库集中式限流；这一点写在设计文档中。
- 登录只记录失败次数，成功后清空；注册每次尝试都计数。
"""

from __future__ import annotations

import threading
import time

from . import settings

_lock = threading.Lock()
_events: dict[str, list[float]] = {}


def _prune(key: str, window: int, now: float) -> list[float]:
    cutoff = now - window
    items = _events.get(key, [])
    items = [t for t in items if t > cutoff]
    if items:
        _events[key] = items
    else:
        _events.pop(key, None)
    return items


def _check(key: str, limit: int, window: int) -> tuple[bool, int]:
    if not settings.rate_limit_enabled():
        return True, 0
    now = time.monotonic()
    with _lock:
        items = _prune(key, window, now)
        if len(items) >= limit:
            retry_after = int(window - (now - items[0])) + 1
            return False, max(1, retry_after)
        return True, 0


def _record(key: str, window: int) -> None:
    if not settings.rate_limit_enabled():
        return
    now = time.monotonic()
    with _lock:
        items = _prune(key, window, now)
        items.append(now)
        _events[key] = items


def check_register(ip: str) -> tuple[bool, int]:
    limit, window = settings.register_rate_limit()
    return _check(f"register:{ip}", limit, window)


def record_register(ip: str) -> None:
    _, window = settings.register_rate_limit()
    _record(f"register:{ip}", window)


def check_login(ip: str, username: str) -> tuple[bool, int]:
    limit, window = settings.login_rate_limit()
    return _check(f"login:{ip}:{username.lower()}", limit, window)


def record_login_failure(ip: str, username: str) -> None:
    _, window = settings.login_rate_limit()
    _record(f"login:{ip}:{username.lower()}", window)


def clear_login(ip: str, username: str) -> None:
    with _lock:
        _events.pop(f"login:{ip}:{username.lower()}", None)


def reset() -> None:
    """测试用：清空所有计数。"""
    with _lock:
        _events.clear()
