# Todo API

An in-memory todo list built with [FastAPI](https://fastapi.tiangolo.com/): CRUD, API-key auth, pagination, and one deprecated endpoint. Part of the [Mintlify demo org](https://github.com/mintlify-demo): `docs/` holds this API's Mintlify docs.

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/todos` | Paginated (`page`, `page_size`), filter with `completed` |
| `POST` | `/todos` | Create |
| `GET` / `PATCH` / `DELETE` | `/todos/{todo_id}` | Read, update, delete |
| `GET` | `/todos/list-all` | **Deprecated**, unpaginated |

All requests need `X-API-Key: demo-key` (set `TODO_API_KEY` to change it).

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload        # http://localhost:8000  (Swagger UI at /docs)
```

```bash
curl -X POST localhost:8000/todos -H 'X-API-Key: demo-key' \
  -H 'Content-Type: application/json' -d '{"title": "Write the docs"}'
```

## Test it

```bash
python -m pytest -q
```

## Regenerate the OpenAPI spec

`docs/openapi.json` is committed so Mintlify can build the API reference without running the app. After changing `main.py`:

```bash
python scripts/export_openapi.py    # or: make spec
```

A test fails if the committed spec is out of date.

## Docs

`docs/` is a complete Mintlify project. The central [`docs`](https://github.com/mintlify-demo/docs) repo publishes it at `/todo-api`. Preview just this folder with `cd docs && mint dev`.
