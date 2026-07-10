import importlib.util
import json
from dataclasses import asdict
from pathlib import Path
import sys
import unittest


def load_hardware_qualification_script():
    project_root = Path(__file__).resolve().parents[1]
    scripts_dir = project_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    script_path = scripts_dir / "12_hardware_qualification.py"
    spec = importlib.util.spec_from_file_location(
        "scripts_12_hardware_qualification",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HardwareQualificationScriptTests(unittest.TestCase):
    def test_qualification_requires_all_hardware_thresholds(self) -> None:
        script = load_hardware_qualification_script()

        report = script.evaluate_metrics(
            rgbd_fps=25.5,
            imu_hz=199.0,
            object_valid_ratio=0.75,
            median_noise_mm=0.8,
            p90_noise_mm=1.7,
        )

        self.assertTrue(report.passed)
        self.assertEqual(report.failures, ())
        self.assertEqual(
            report.metrics,
            {
                "rgbd_fps": 25.5,
                "imu_hz": 199.0,
                "object_valid_ratio": 0.75,
                "median_noise_mm": 0.8,
                "p90_noise_mm": 1.7,
            },
        )

        failing_cases = [
            ("rgbd_fps", (23.99, 199.0, 0.75, 0.8, 1.7)),
            ("imu_hz", (25.5, 189.99, 0.75, 0.8, 1.7)),
            ("imu_hz", (25.5, 210.01, 0.75, 0.8, 1.7)),
            ("object_valid_ratio", (25.5, 199.0, 0.69, 0.8, 1.7)),
            ("median_noise_mm", (25.5, 199.0, 0.75, 1.01, 1.7)),
            ("p90_noise_mm", (25.5, 199.0, 0.75, 0.8, 2.01)),
        ]
        for expected_failure, args in failing_cases:
            with self.subTest(expected_failure=expected_failure, args=args):
                failed = script.evaluate_metrics(*args)
                self.assertFalse(failed.passed)
                self.assertIn(expected_failure, failed.failures)

    def test_qualification_report_is_json_serializable(self) -> None:
        script = load_hardware_qualification_script()
        report = script.evaluate_metrics(
            rgbd_fps=24.0,
            imu_hz=190.0,
            object_valid_ratio=0.70,
            median_noise_mm=1.0,
            p90_noise_mm=2.0,
        )

        payload = json.loads(json.dumps(asdict(report)))

        self.assertEqual(payload["passed"], True)
        self.assertEqual(payload["failures"], [])
        self.assertEqual(payload["metrics"]["rgbd_fps"], 24.0)
        self.assertEqual(payload["metrics"]["imu_hz"], 190.0)
        self.assertEqual(payload["metrics"]["object_valid_ratio"], 0.70)
        self.assertEqual(payload["metrics"]["median_noise_mm"], 1.0)
        self.assertEqual(payload["metrics"]["p90_noise_mm"], 2.0)


if __name__ == "__main__":
    unittest.main()
