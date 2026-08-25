import logging
import random
import time
from collections.abc import Callable


logger = logging.getLogger("uvicorn.error")

PERIODIC_RANDOM_PROBABILITY = 0.50
PERIODIC_MAX_SILENCE_SECONDS = 300


class PeriodicGate:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        random_source: Callable[[], float] = random.random,
    ) -> None:
        self._clock = clock
        self._random_source = random_source
        self._started_at = clock()
        self._last_agent_message_at: float | None = None

    @property
    def last_agent_message_at(self) -> float | None:
        return self._last_agent_message_at

    def record_agent_message(self) -> None:
        self._last_agent_message_at = self._clock()

    def should_allow(
        self,
        *,
        hp_drop: bool = False,
    ) -> tuple[bool, str]:
        if hp_drop:
            return self._result(True, "hp_drop")

        now = self._clock()
        silence_started_at = (
            self._last_agent_message_at
            if self._last_agent_message_at is not None
            else self._started_at
        )
        if now - silence_started_at >= PERIODIC_MAX_SILENCE_SECONDS:
            return self._result(True, "silence_timeout")

        if self._random_source() < PERIODIC_RANDOM_PROBABILITY:
            return self._result(True, "random_hit")

        return self._result(False, "random_miss")

    @staticmethod
    def _result(allowed: bool, reason: str) -> tuple[bool, str]:
        logger.info(
            "[PeriodicGate] allowed=%s reason=%s",
            str(allowed).lower(),
            reason,
        )
        return allowed, reason
