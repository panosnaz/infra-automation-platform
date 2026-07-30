"""Path setup so tests can import `generator` (platform/python/) without it
being an installed package.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_path = _REPO_ROOT / "platform" / "python"  # for `import generator`
if str(_path) not in sys.path:
    sys.path.insert(0, str(_path))
