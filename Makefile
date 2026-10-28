.PHONY: install run test spec docs-dev sdk-docs

install:  ## create a venv and install dependencies
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

run:  ## start the API on http://localhost:8000
	.venv/bin/uvicorn main:app --reload

test:  ## run the test suite
	.venv/bin/python -m pytest -q

spec:  ## regenerate docs/openapi.json from the app
	.venv/bin/python scripts/export_openapi.py

docs-dev:  ## preview just this repo's docs (needs: npm i -g mint)
	cd docs && mint dev

sdk-docs:  ## regenerate the Sphinx JSON artifact Mintlify builds the Python SDK reference from
	rm -rf docs/sdk-artifacts/python
	.venv/bin/python -m sphinx -q -b json -d /tmp/todo-sdk-doctrees sdk/docs docs/sdk-artifacts/python
	rm -rf docs/sdk-artifacts/python/_static docs/sdk-artifacts/python/environment.pickle
