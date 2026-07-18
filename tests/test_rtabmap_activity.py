from pathlib import Path
import sqlite3

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.activity import (
    ActivityMonitor,
    ActivityObservation,
    AutoPauseState,
    SqliteNodeCountProbe,
)
from scanner_app.rtabmap.windows_bridge import BridgeResult


def test_monitor_pauses_once_after_three_inactive_seconds() -> None:
    pause_calls: list[None] = []
    monitor = ActivityMonitor(
        pause=lambda: pause_calls.append(None) or BridgeResult(True, "Pause sent"),
        inactivity_seconds=3.0,
        countdown_seconds=1.0,
    )

    assert monitor.observe(ActivityObservation(1, 0.0, None)) is AutoPauseState.WARMING_UP
    assert monitor.observe(ActivityObservation(2, 1.0, None)) is AutoPauseState.ACTIVE
    assert monitor.observe(ActivityObservation(2, 4.0, None)) is AutoPauseState.COUNTDOWN
    assert monitor.observe(ActivityObservation(2, 5.0, None)) is AutoPauseState.PAUSED
    assert monitor.observe(ActivityObservation(2, 8.0, None)) is AutoPauseState.PAUSED
    assert pause_calls == [None]


def test_monitor_becomes_uncertain_without_sending_pause_when_probe_is_invalid() -> None:
    monitor = ActivityMonitor(
        pause=lambda: (_ for _ in ()).throw(AssertionError("must not pause")),
        inactivity_seconds=3.0,
        countdown_seconds=1.0,
    )

    monitor.observe(ActivityObservation(1, 0.0, None))
    assert monitor.observe(ActivityObservation(None, 1.0, "database is locked")) is AutoPauseState.UNCERTAIN


def test_monitor_becomes_uncertain_when_pause_command_is_not_sent() -> None:
    monitor = ActivityMonitor(
        pause=lambda: BridgeResult(False, "Pause failed: access denied"),
        inactivity_seconds=3.0,
        countdown_seconds=1.0,
    )

    monitor.observe(ActivityObservation(1, 0.0, None))
    monitor.observe(ActivityObservation(2, 1.0, None))
    assert monitor.observe(ActivityObservation(2, 4.0, None)) is AutoPauseState.COUNTDOWN
    assert monitor.observe(ActivityObservation(2, 5.0, None)) is AutoPauseState.UNCERTAIN


def test_sqlite_probe_reads_rtabmap_node_count_read_only(tmp_path: Path) -> None:
    database = tmp_path / "rtabmap.tmp.db"
    connection = sqlite3.connect(database)
    connection.execute("create table Node(id integer primary key)")
    connection.executemany("insert into Node(id) values (?)", [(1,), (2,), (3,)])
    connection.commit()
    connection.close()

    observation = SqliteNodeCountProbe(database, clock=lambda: 12.5).observe()

    assert observation == ActivityObservation(sequence=3, observed_at=12.5, reason=None)


def test_sqlite_probe_reports_missing_database_as_uncertain(tmp_path: Path) -> None:
    observation = SqliteNodeCountProbe(tmp_path / "rtabmap.tmp.db", clock=lambda: 9.0).observe()

    assert observation.sequence is None
    assert observation.observed_at == 9.0
    assert observation.reason == "temporary database does not exist"
