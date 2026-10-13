"""Configuration for rate limiting."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitConfig:
    """Configuration for a rate limiter.

    Attributes:
        max_requests: Maximum number of requests allowed in the window.
        window_seconds: Duration of the rate limit window in seconds.
        burst: Maximum burst size (tokens that can be consumed at once).
            Defaults to max_requests when not set.
    """

    max_requests: int = 60
    window_seconds: float = 60.0
    burst: int | None = None

    def __post_init__(self) -> None:
        if self.max_requests <= 0:
            raise ValueError("max_requests must be positive")
        # Written so NaN fails it: every comparison with NaN is false, and a
        # NaN window used to pass `<= 0` and switch the limit off entirely.
        if not (0 < self.window_seconds < math.inf):
            raise ValueError("window_seconds must be positive and finite")
        if self.burst is not None and self.burst <= 0:
            raise ValueError("burst must be positive when provided")
