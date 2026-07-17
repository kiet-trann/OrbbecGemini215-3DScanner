"""Read-only RTAB-Map activity observations and a fail-safe auto-pause monitor."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sqlite3
import time

from scanner_app.rtabmap.windows_bridge import BridgeResult


@dataclass(frozen=True)
class ActivityObservation:
    sequence: int | None
    observed_at: float
    reason: str | None


class AutoPauseState(str, Enum):
    DISABLED = "disabled"
    WARMING_UP = "warming_up"
    ACTIVE = "active"
    COUNTDOWN = "countdown"
    PAUSED = "paused"
    UNCERTAIN = "uncertain"


class SqliteNodeCountProbe:
    """Read the current RTAB-Map Node row count without writing the database."""

    def __init__(self, database: Path, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._database = database
        self._clock = clock
        self._last_sequence: int | None = None

    def observe(self) -> ActivityObservation:
        observed_at = self._clock()
        if not self._database.is_file():
            return ActivityObservation(None, observed_at, "temporary database does not exist")
        try:
            connection = sqlite3.connect(
                f"{self._database.resolve().as_uri()}?mode=ro",
                uri=True,
                timeout=0,
            )
            try:
                sequence = int(connection.execute("select count(*) from Node").fetchone()[0])
            finally:
                connection.close()
        except sqlite3.Error as error:
            return ActivityObservation(None, observed_at, f"database read failed: {error}")

        if self._last_sequence is not None and sequence < self._last_sequence:
            return ActivityObservation(None, observed_at, "node count decreased")
        self._last_sequence = sequence
        return ActivityObservation(sequence, observed_at, None)


class ActivityMonitor:
    """Pause once after verified RTAB-Map activity becomes inactive."""

    def __init__(
        self,
        *,
        pause: Callable[[], BridgeResult],
        inactivity_seconds: float = 3.0,
        countdown_seconds: float = 1.0,
    ) -> None:
        self._pause = pause
        self._inactivity_seconds = inactivity_seconds
        self._countdown_seconds = countdown_seconds
        self._state = AutoPauseState.DISABLED
        self._last_sequence: int | None = None
        self._last_activity_at: float | None = None
        self._countdown_started_at: float | None = None

    @property
    def state(self) -> AutoPauseState:
        return self._state

    def observe(self, observation: ActivityObservation) -> AutoPauseState:
        if observation.sequence is None:
            self._state = AutoPauseState.UNCERTAIN
            self._countdown_started_at = None
            return self._state

        if self._last_sequence is None:
            self._last_sequence = observation.sequence
            self._last_activity_at = observation.observed_at
            self._state = AutoPauseState.WARMING_UP
            return self._state

        if observation.sequence < self._last_sequence:
            self._state = AutoPauseState.UNCERTAIN
            self._countdown_started_at = None
            return self._state

        if observation.sequence > self._last_sequence:
            self._last_sequence = observation.sequence
            self._last_activity_at = observation.observed_at
            self._countdown_started_at = None
            self._state = AutoPauseState.ACTIVE
            return self._state

        if self._state is AutoPauseState.PAUSED:
            return self._state
        if self._state is AutoPauseState.WARMING_UP:
            return self._state

        assert self._last_activity_at is not None
        if self._state is AutoPauseState.COUNTDOWN:
            assert self._countdown_started_at is not None
            if observation.observed_at - self._countdown_started_at >= self._countdown_seconds:
                result = self._pause()
                self._state = AutoPauseState.PAUSED if result.sent else AutoPauseState.UNCERTAIN
            return self._state

        if observation.observed_at - self._last_activity_at >= self._inactivity_seconds:
            self._countdown_started_at = observation.observed_at
            self._state = AutoPauseState.COUNTDOWN
        return self._state

    def resume(self, observed_at: float) -> AutoPauseState:
        if self._last_sequence is None:
            self._state = AutoPauseState.UNCERTAIN
            return self._state
        self._last_activity_at = observed_at
        self._countdown_started_at = None
        self._state = AutoPauseState.ACTIVE
        return self._state
