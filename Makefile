.PHONY: install run test spec docs-dev

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
