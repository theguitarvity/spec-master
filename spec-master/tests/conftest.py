"""Path-only pytest bootstrap (no pytest import; stdlib only).

``spec-master/tests`` is a package but ``spec-master/`` is not, so pytest's
default ``prepend`` import mode puts ``spec-master/`` on ``sys.path`` and the
sibling helper ``_pathfix`` becomes unimportable. Inserting this directory
lets ``pytest`` run from the repository root with no ``pythonpath`` option.
unittest ignores this file (it does not match ``test*.py``).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
