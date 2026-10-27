"""Regenerate docs/openapi.json from the FastAPI app.

Run from the repo root:  python scripts/export_openapi.py   (or: make spec)
The file is committed so Mintlify can build the API reference without
running the app.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from main import app  # noqa: E402

out = ROOT / "docs" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n")
print(f"Wrote {out.relative_to(ROOT)}")
