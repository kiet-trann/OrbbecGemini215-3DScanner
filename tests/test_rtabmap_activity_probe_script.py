import importlib.util
from pathlib import Path
import sys

try:
    from test_support import add_src_to_path
except ImportError:
    from tests.test_support import add_src_to_path

add_src_to_path()

from scanner_app.rtabmap.activity import ActivityObservation


def load_probe_script():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(
        "rtabmap_activity_probe",
        scripts_dir / "17_rtabmap_activity_probe.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_report_requires_mapping_growth_and_three_seconds_of_stability() -> None:
    script = load_probe_script()

    reliable = script.build_report(
        [
            ActivityObservation(10, 0.0, None),
            ActivityObservation(11, 1.0, None),
            ActivityObservation(11, 4.0, None),
        ],
        inactivity_seconds=3.0,
    )
    no_growth = script.build_report(
        [
            ActivityObservation(10, 0.0, None),
            ActivityObservation(10, 4.0, None),
        ],
        inactivity_seconds=3.0,
    )

    assert reliable.reliable
    assert reliable.failures == ()
    assert not no_growth.reliable
    assert no_growth.failures == ("no Node growth was observed",)


def test_report_is_unreliable_when_any_observation_is_uncertain() -> None:
    script = load_probe_script()

    report = script.build_report(
        [
            ActivityObservation(10, 0.0, None),
            ActivityObservation(None, 1.0, "database is locked"),
            ActivityObservation(11, 5.0, None),
        ],
        inactivity_seconds=3.0,
    )

    assert not report.reliable
    assert report.failures == ("database is locked",)


def test_parser_defaults_and_sample_interval_are_deterministic() -> None:
    script = load_probe_script()
    args = script.build_argument_parser().parse_args(["--database", "rtabmap.tmp.db"])
    now = [0.0]
    observations = [
        ActivityObservation(1, 0.0, None),
        ActivityObservation(2, 0.25, None),
        ActivityObservation(2, 0.5, None),
    ]

    class FakeProbe:
        def observe(self) -> ActivityObservation:
            return observations.pop(0)

    sampled = script.sample(
        FakeProbe(),
        seconds=0.5,
        interval=0.25,
        clock=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    assert args.database == Path("rtabmap.tmp.db")
    assert args.seconds == 10.0
    assert args.interval == 0.25
    assert [item.sequence for item in sampled] == [1, 2, 2]
