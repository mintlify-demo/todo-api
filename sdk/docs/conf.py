# Sphinx config for the todo-client reference. Build JSON for Mintlify with `make sdk-docs`.
import os
import sys

sys.path.insert(0, os.path.abspath(".."))

project = "todo-client"
author = "mintlify-demo"
release = "0.1.0"
extensions = ["sphinx.ext.autodoc"]
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {"members": True, "undoc-members": False, "show-inheritance": True}
