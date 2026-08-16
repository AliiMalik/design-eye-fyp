"""Host-side entry point for the demo seeder.

The implementation lives in ``backend/app/seed.py`` so it ships inside the API
image; inside the container run ``python -m app.seed`` instead.

    python scripts/seed_demo.py --reset
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.seed import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
