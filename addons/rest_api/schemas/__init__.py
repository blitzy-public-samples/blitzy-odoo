"""Public schema surface for the ``rest_api`` REST API addon.

This module turns :mod:`odoo.addons.rest_api.schemas` into a Python package
whose sole responsibility is to **re-export**, at package level, every public
pydantic DTO defined by its sibling modules. It contains *no* DTO definitions,
*no* business logic and, deliberately, *no* ``import odoo`` -- every concrete
model lives in one of the sibling modules and this file merely aggregates them
into a single, auditable public surface.

Two import styles are supported and are a hard cross-agent contract that the
OpenAPI assembler (:mod:`odoo.addons.rest_api.openapi`) and the per-model
controllers rely upon:

* direct name import ::

      from odoo.addons.rest_api.schemas import PartnerCreate, RestErrorResponse

* attribute access on the package module (used by the OpenAPI assembler) ::

      from odoo.addons.rest_api import schemas
      schemas.PartnerCreate

Both work because every symbol is imported here and enumerated in
:data:`__all__`.

Provenance of the re-exported names:

* :mod:`.base` -- shared building blocks:

  * :class:`~odoo.addons.rest_api.schemas.base.BaseRestModel` -- strict base for
    request DTOs (``strict=True``, ``extra='forbid'``);
  * :class:`~odoo.addons.rest_api.schemas.base.BaseRestReadModel` -- lenient base
    for response DTOs (``from_attributes=True``);
  * :class:`~odoo.addons.rest_api.schemas.base.RestErrorResponse` -- canonical
    REST error envelope;
  * :class:`~odoo.addons.rest_api.schemas.base.PageMeta` -- pagination metadata.

* the five per-model modules -- request/response DTOs for each pilot model:
  ``account_move`` (``AccountMove*``), ``crm_lead`` (``CrmLead*``),
  ``res_partner`` (``Partner*``), ``sale_order`` (``SaleOrder*``) and
  ``stock_picking`` (``StockPicking*``).

Import-safety and ordering notes:

* This package is imported at module-load time by the controllers and at request
  time by the OpenAPI assembler; it must stay side-effect-free beyond the imports
  themselves.
* The import order is acyclic: every sibling module imports only from ``.base``
  (never from this package ``__init__``), so re-exporting them here introduces no
  circular-import hazard regardless of the order in which they are listed.
* This is the ``schemas`` **sub-package** initializer only -- it is intentionally
  distinct from the addon's top-level ``__init__.py`` (which wires ``models`` and
  ``controllers``).
"""

from .account_move import (
    AccountMoveCreate,
    AccountMoveList,
    AccountMoveRead,
    AccountMoveUpdate,
)
from .base import (
    BaseRestModel,
    BaseRestReadModel,
    PageMeta,
    RestErrorResponse,
)
from .crm_lead import (
    CrmLeadCreate,
    CrmLeadList,
    CrmLeadRead,
    CrmLeadUpdate,
)
from .res_partner import (
    PartnerCreate,
    PartnerList,
    PartnerRead,
    PartnerUpdate,
)
from .sale_order import (
    SaleOrderCreate,
    SaleOrderList,
    SaleOrderRead,
    SaleOrderUpdate,
)
from .stock_picking import (
    StockPickingCreate,
    StockPickingList,
    StockPickingRead,
    StockPickingUpdate,
)

# Explicit public surface (sorted). Every name below is re-exported from one of
# the sibling modules above; keeping this list exhaustive lets
# ``from ...schemas import *`` and static linters agree with the OpenAPI
# assembler and the controllers on the exact set of available DTOs. See the
# module docstring for the provenance of each name.
__all__ = [
    'AccountMoveCreate',
    'AccountMoveList',
    'AccountMoveRead',
    'AccountMoveUpdate',
    'BaseRestModel',
    'BaseRestReadModel',
    'CrmLeadCreate',
    'CrmLeadList',
    'CrmLeadRead',
    'CrmLeadUpdate',
    'PageMeta',
    'PartnerCreate',
    'PartnerList',
    'PartnerRead',
    'PartnerUpdate',
    'RestErrorResponse',
    'SaleOrderCreate',
    'SaleOrderList',
    'SaleOrderRead',
    'SaleOrderUpdate',
    'StockPickingCreate',
    'StockPickingList',
    'StockPickingRead',
    'StockPickingUpdate',
]
