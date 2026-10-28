"""Regenerate the committed API specs from the code.

Run from the repo root:  python scripts/export_openapi.py   (or: make spec)

Writes:
  docs/openapi.json     REST API (FastAPI)
  docs/schema.graphql   GraphQL API (Strawberry, todo_graphql.py)

The files are committed so Mintlify can build the API references without
running the app. docs/asyncapi.yaml (WebSocket events) is written by hand.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from main import app  # noqa: E402
from todo_graphql import schema  # noqa: E402

out = ROOT / "docs" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n")
print(f"Wrote {out.relative_to(ROOT)}")

sdl = ROOT / "docs" / "schema.graphql"
sdl.write_text(schema.as_str() + "\n")
print(f"Wrote {sdl.relative_to(ROOT)}")
