.PHONY: install run test sdk-docs

install:  ## create a venv and install dependencies
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

run:  ## start the API on http://localhost:8000
	.venv/bin/uvicorn main:app --reload

test:  ## run the test suite
	.venv/bin/python -m pytest -q

DOCS_REPO ?= ../docs
sdk-docs:  ## rebuild the SDK reference artifact in the docs repo (DOCS_REPO=../docs)
	rm -rf $(DOCS_REPO)/todo-api/sdk-artifacts/python
	.venv/bin/python -m sphinx -q -b json -d /tmp/todo-sdk-doctrees sdk/docs $(DOCS_REPO)/todo-api/sdk-artifacts/python
	rm -rf $(DOCS_REPO)/todo-api/sdk-artifacts/python/_static $(DOCS_REPO)/todo-api/sdk-artifacts/python/environment.pickle
