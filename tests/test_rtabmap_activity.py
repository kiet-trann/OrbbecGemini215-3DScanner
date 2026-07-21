from pathlib import Path
import os
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
    SessionDatabaseProbe,
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


def create_database(path: Path, *, nodes: int) -> Path:
    connection = sqlite3.connect(path)
    connection.execute("create table Node(id integer primary key)")
    connection.executemany("insert into Node(id) values (?)", [(index,) for index in range(nodes)])
    connection.commit()
    connection.close()
    return path


def test_session_probe_selects_newest_readable_database_after_start(tmp_path: Path) -> None:
    old = create_database(tmp_path / "old.db", nodes=99)
    os.utime(old, (90.0, 90.0))
    current = create_database(tmp_path / "scan.db", nodes=2)
    os.utime(current, (101.0, 101.0))
    probe = SessionDatabaseProbe(tmp_path, clock=lambda: 12.5, wall_clock=lambda: 100.0)

    probe.start()

    assert probe.observe() == ActivityObservation(2, 12.5, None)
    assert probe.active_database == current


def test_session_probe_uses_the_timestamp_captured_before_launch(tmp_path: Path) -> None:
    current = create_database(tmp_path / "scan.db", nodes=2)
    os.utime(current, (101.0, 101.0))
    probe = SessionDatabaseProbe(tmp_path, clock=lambda: 12.5, wall_clock=lambda: 200.0)

    probe.start(100.0)

    assert probe.observe() == ActivityObservation(2, 12.5, None)


def test_session_probe_keeps_initial_database_binding(tmp_path: Path) -> None:
    selected = create_database(tmp_path / "first.db", nodes=2)
    os.utime(selected, (101.0, 101.0))
    later = create_database(tmp_path / "later.db", nodes=20)
    os.utime(later, (99.0, 99.0))
    probe = SessionDatabaseProbe(tmp_path, clock=lambda: 12.5, wall_clock=lambda: 100.0)
    probe.start()
    probe.observe()
    os.utime(later, (102.0, 102.0))

    assert probe.observe().sequence == 2
    assert probe.active_database == selected


def test_session_probe_is_uncertain_until_a_database_is_created_for_the_session(tmp_path: Path) -> None:
    probe = SessionDatabaseProbe(tmp_path, clock=lambda: 12.5, wall_clock=lambda: 100.0)

    probe.start()

    assert probe.observe() == ActivityObservation(
        None, 12.5, "active RTAB-Map database was not found"
    )
