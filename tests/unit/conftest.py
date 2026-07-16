"""Path setup so tests can import both `canonical_intent` and the platform-api
`app` package without either being an installed package — mirrors how the
Docker image lays them out as siblings under one root, without needing Docker.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

for _path in (
    _REPO_ROOT / "platform",  # for `import canonical_intent`
    _REPO_ROOT / "platform" / "python",  # for `import generator` (Milestone 6A, terraform_executor.py)
    _REPO_ROOT / "lab" / "docker" / "platform-api",  # for `from app... import`
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
