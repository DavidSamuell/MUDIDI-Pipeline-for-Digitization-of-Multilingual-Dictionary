"""Put the annotation code packages on ``sys.path`` for the test modules.

The annotation scripts use flat sibling imports (``from script_labeler import ...``)
and are grouped into ``labelers/`` and ``label_studio/`` subfolders. pytest loads
this conftest before collecting ``annotation/tests/``, so the flat imports in the
test modules resolve regardless of which subfolder a module lives in. (``mudidi``
itself is importable via ``pythonpath = ["src"]`` in ``pyproject.toml``.)
"""

import sys
from pathlib import Path

_ANNOTATION_ROOT = Path(__file__).resolve().parents[1]
for _package in ("labelers", "label_studio"):
    sys.path.insert(0, str(_ANNOTATION_ROOT / _package))
