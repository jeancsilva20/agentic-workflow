"""Make `agent-console/` importable as a flat module directory (`store`, `app`)
for its own standalone test suite — it is not part of the `agent` package.

The repository root goes on the path too: the console's config layer reads the
model catalog and the shared config-file location from the sibling `agent`
package, so the tests need the same import to resolve as at runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CONSOLE_DIR = Path(__file__).resolve().parents[1]
if str(_CONSOLE_DIR) not in sys.path:
    sys.path.insert(0, str(_CONSOLE_DIR))

_REPO_ROOT = _CONSOLE_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
