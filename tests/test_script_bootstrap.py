import os
import subprocess
import sys
import unittest
from pathlib import Path


class ScriptBootstrapTests(unittest.TestCase):
    def test_bootstrap_makes_src_package_importable_without_editable_install(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import runpy; "
                    "runpy.run_path('scripts/_bootstrap.py'); "
                    "import scanner_app; "
                    "print(scanner_app.__version__)"
                ),
            ],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0.1.0")


if __name__ == "__main__":
    unittest.main()
