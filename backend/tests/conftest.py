"""pytest configuration for the backend test suite.

Ensures that the ``backend/`` directory is on sys.path so that
``import market.*`` works from any working directory.
"""

import sys
from pathlib import Path

# Add backend/ to sys.path so `import market.*` resolves correctly
# regardless of where pytest is invoked from.
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
