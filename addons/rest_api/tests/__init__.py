# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Test package initializer for the ``rest_api`` addon. Odoo discovers a module's
# tests by importing its ``tests`` sub-package and collecting the ``test_*``
# modules that have been imported into it (see
# ``odoo/tests/loader.py::_get_tests_modules``). Each REST test module must
# therefore be imported here for it to run under ``--test-enable``; without this
# file none of the suites below are collected.
from . import test_rest_auth
from . import test_rest_validation
from . import test_rest_authz_parity
from . import test_rest_openapi
from . import test_rest_crud
