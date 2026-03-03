# Root-level conftest.py — ensures odoo.init is imported before pytest-odoo
# plugin hooks try to access odoo.tools. Odoo 19 is a namespace package
# without __init__.py, so 'import odoo' alone does not load sub-packages.
import odoo.init  # noqa: F401 — side-effect: populates odoo.tools, odoo.api, etc.
