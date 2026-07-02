# Part of Odoo. See LICENSE file for full copyright and licensing details.

# Top-level package initializer for the ``rest_api`` addon. Odoo loads the
# addon via ``load_openerp_module('rest_api')`` (i.e.
# ``__import__('odoo.addons.rest_api')``), so this module is the single entry
# point that wires the addon's sub-packages into a normal module load. Without
# it, neither ``models`` nor ``controllers`` is imported: no REST route is
# registered and ``_auth_method_rest_bearer`` is never added to ``ir.http``.
#
# ``models`` is imported BEFORE ``controllers`` so the ``ir.http`` inheritance
# in ``models/ir_http.py`` registers the ``_auth_method_rest_bearer``
# classmethod before the controllers that declare ``auth='rest_bearer'``
# routes are imported (AAP sections 0.3.1 and 0.4.2; standard Odoo
# models-before-controllers order).
from . import models
from . import controllers
