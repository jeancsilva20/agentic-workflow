"""Make `agent-console/` importable as a flat module directory (`store`, `app`)
for its own standalone test suite — it is not part of the `agent` package.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CONSOLE_DIR = Path(__file__).resolve().parents[1]
if str(_CONSOLE_DIR) not in sys.path:
    sys.path.insert(0, str(_CONSOLE_DIR))
