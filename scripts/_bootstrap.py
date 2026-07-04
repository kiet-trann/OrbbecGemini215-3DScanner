"""Allow milestone scripts to run before the package is installed.

When a file under `scripts/` is executed directly, Python puts `scripts/` on
`sys.path`, but not the project's `src/` directory. This bootstrap keeps the
prototype scripts convenient while preserving the src-layout package structure.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
