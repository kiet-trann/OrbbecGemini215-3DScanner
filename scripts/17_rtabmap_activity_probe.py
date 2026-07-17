"""Check whether RTAB-Map's temporary database is safe to use for auto-pause."""

import _bootstrap  # noqa: F401

import argparse
from collections.abc import Callable
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time

from scanner_app.rtabmap.activity import ActivityObservation, SqliteNodeCountProbe


@dataclass(frozen=True)
class ProbeReport:
    reliable: bool
    mapping_observed: bool
    stable_seconds: float
    failures: tuple[str, ...]


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate RTAB-Map activity monitoring without writing its database.")
    parser.add_argument("--database", type=Path, required=True, help="Active rtabmap.tmp.db path.")
    parser.add_argument("--seconds", type=float, default=10.0, help="Total sample duration in seconds.")
    parser.add_argument("--interval", type=float, default=0.25, help="Seconds between read-only observations.")
    return parser


def build_report(
    observations: list[ActivityObservation],
    *,
    inactivity_seconds: float,
) -> ProbeReport:
    if not observations:
        return ProbeReport(False, False, 0.0, ("no observations were collected",))

    uncertain = next((item.reason for item in observations if item.sequence is None), None)
    if uncertain is not None:
        return ProbeReport(False, False, 0.0, (uncertain,))

    first = observations[0]
    assert first.sequence is not None
    last_sequence = first.sequence
    last_change_at = first.observed_at
    mapping_observed = False
    for observation in observations[1:]:
        assert observation.sequence is not None
        if observation.sequence < last_sequence:
            return ProbeReport(False, False, 0.0, ("Node count decreased",))
        if observation.sequence > last_sequence:
            mapping_observed = True
            last_sequence = observation.sequence
            last_change_at = observation.observed_at

    stable_seconds = observations[-1].observed_at - last_change_at
    failures: list[str] = []
    if not mapping_observed:
        failures.append("no Node growth was observed")
    if mapping_observed and stable_seconds < inactivity_seconds:
        failures.append(f"Node activity was not stable for {inactivity_seconds:.1f} seconds")
    return ProbeReport(
        reliable=not failures,
        mapping_observed=mapping_observed,
        stable_seconds=stable_seconds,
        failures=tuple(failures),
    )


def sample(
    probe: SqliteNodeCountProbe,
    *,
    seconds: float,
    interval: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> list[ActivityObservation]:
    if seconds <= 0 or interval <= 0:
        raise ValueError("seconds and interval must be positive")
    deadline = clock() + seconds
    observations: list[ActivityObservation] = []
    while True:
        observations.append(probe.observe())
        if clock() >= deadline:
            return observations
        sleep(interval)


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    report = build_report(
        sample(SqliteNodeCountProbe(args.database), seconds=args.seconds, interval=args.interval),
        inactivity_seconds=3.0,
    )
    print(json.dumps(asdict(report), ensure_ascii=False))
    return 0 if report.reliable else 2


if __name__ == "__main__":
    raise SystemExit(main())
