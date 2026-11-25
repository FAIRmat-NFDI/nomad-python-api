"""Public settings for the client's API connections and timeouts."""

from dataclasses import dataclass, fields
from sys import float_info
from threading import TIMEOUT_MAX


@dataclass(frozen=True, kw_only=True)
class ConnectionLimits:
    """Bound the client's connection pool and idle connection reuse."""

    max_connections: int = 10
    max_keepalive_connections: int = 5
    keepalive_expiry: float = 5.0

    def __post_init__(self) -> None:
        if type(self.max_connections) is not int or self.max_connections < 1:
            raise ValueError("max_connections must be a positive integer.")
        if type(self.max_keepalive_connections) is not int or self.max_keepalive_connections < 0:
            raise ValueError("max_keepalive_connections must be a nonnegative integer.")
        _validate_seconds("keepalive_expiry", self.keepalive_expiry, allow_zero=True)


@dataclass(frozen=True, kw_only=True)
class NetworkTimeouts:
    """Set timeouts in seconds for the individual API network phases."""

    connect: float = 5.0
    pool: float = 10.0
    read: float = 10.0
    write: float = 10.0

    def __post_init__(self) -> None:
        for setting in fields(self):
            value = getattr(self, setting.name)
            _validate_seconds(setting.name, value)
            if value > TIMEOUT_MAX:
                raise ValueError(f"{setting.name} must not exceed the runtime timeout limit ({TIMEOUT_MAX:g} s).")


def _validate_seconds(name: str, value: float, *, allow_zero: bool = False) -> None:
    if (
        type(value) not in (int, float)
        or not (0 <= value <= float_info.max)
        or (value == 0 and not allow_zero)
    ):
        bound = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{name} must be a finite {bound} number of seconds.")
