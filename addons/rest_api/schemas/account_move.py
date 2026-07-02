"""Pydantic v2 request/response DTOs for the ``account.move`` REST pilot.

This module is one of the five per-model schema modules of the
:mod:`odoo.addons.rest_api.schemas` package. It defines the data-transfer
objects (DTOs) that govern the ``/api/v1/account-moves`` endpoints, mapping the
Odoo ``account.move`` model (journal entries, customer invoices, vendor bills,
credit notes and receipts) onto a strict, versioned REST contract.

Four DTOs make up the public API of this module, mirroring the CRUD verb map of
the REST surface (AAP section 0.3.2):

* :class:`AccountMoveCreate` -- the **request** body for ``POST
  /api/v1/account-moves`` (ORM ``create``). Strict: it subclasses
  :class:`~odoo.addons.rest_api.schemas.base.BaseRestModel`, so any unknown key
  or wrongly-typed scalar is rejected with an HTTP ``422`` *before* the ORM is
  touched (validation Gate 2). ``move_type`` -- the journal-entry discriminator
  -- is the only required field.
* :class:`AccountMoveUpdate` -- the **request** body for ``PATCH
  /api/v1/account-moves/{id}`` (ORM ``write``). A partial update: every field,
  including ``move_type``, is optional. Also strict.
* :class:`AccountMoveRead` -- the **response** body for a single move
  (``GET .../{id}`` and the element type of a collection ``GET``). Lenient: it
  subclasses :class:`~odoo.addons.rest_api.schemas.base.BaseRestReadModel`
  (``from_attributes=True``), so it can be built directly from an ORM record and
  silently ignores ORM keys it does not declare -- preserving field-set parity
  with what the ORM would return for the authenticated user (AAP section 0.6.4).
* :class:`AccountMoveList` -- the paginated **response** body for the collection
  ``GET``: a list of :class:`AccountMoveRead` plus a
  :class:`~odoo.addons.rest_api.schemas.base.PageMeta` block.

Design constraints (AAP sections 0.2, 0.4.1 and 0.7):

* **No Odoo imports.** These are plain pydantic models, not ORM models. The
  module must stay import-safe when loaded by the OpenAPI assembler outside a
  live registry. Field *derivation* is sourced from
  ``addons/account/models/account_move.py`` at authoring time only; no field is
  invented and none is read from Odoo at runtime.
* **Read-only fields are excluded from the write DTOs.** ``name`` (the computed,
  sequenced document number), ``state`` (workflow-controlled, defaulting to
  ``draft``), the computed monetary totals (``amount_untaxed``, ``amount_tax``,
  ``amount_total``, ``amount_residual``) and the computed ``payment_state`` are
  exposed only in :class:`AccountMoveRead`, never accepted on create/update.
* **Class names are a hard cross-agent contract.** ``AccountMoveCreate`` /
  ``AccountMoveUpdate`` / ``AccountMoveRead`` / ``AccountMoveList`` are imported
  by ``controllers/account_move.py``, re-exported by ``schemas/__init__.py`` and
  reflected into the OpenAPI document by ``openapi.py`` (whose generated
  ``components.schemas`` titles equal these class names -- validation Gate 4).

Field-to-type mapping applied (AAP section 0.3.2 / the module type map):

===================  ==================  ==========================
Odoo field kind      Example field       Python / pydantic type
===================  ==================  ==========================
``Char``             ``ref``             ``str``
``Monetary``         ``amount_total``    ``float``
``Many2one``         ``partner_id``      ``int`` (the related id)
``One2many``         ``invoice_line_ids``  ``list[int]`` (member ids)
``Date``             ``invoice_date``    ``datetime.date``
stable ``Selection`` ``move_type``       ``Literal[...]``
open ``Selection``   ``payment_state``   ``str``
===================  ==================  ==========================
"""

from __future__ import annotations

import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .base import BaseRestModel, BaseRestReadModel, PageMeta

# --------------------------------------------------------------------------- #
# Shared enumerations (derived verbatim from account.move Selection fields)   #
# --------------------------------------------------------------------------- #
# ``move_type`` is a *stable* selection -- its seven members are the journal
# entry / document discriminators baked into the accounting engine and are not
# extended at runtime, so they are modelled as a closed ``Literal``. Keeping the
# alias here guarantees the Create, Update and Read DTOs stay in lock-step.
MoveType = Literal[
    'entry',
    'out_invoice',
    'out_refund',
    'in_invoice',
    'in_refund',
    'out_receipt',
    'in_receipt',
]

# ``state`` is likewise a stable, closed selection (draft -> posted -> cancel).
# It is workflow-controlled and therefore appears only on the read model.
MoveState = Literal[
    'draft',
    'posted',
    'cancel',
]


class AccountMoveCreate(BaseRestModel):
    """Request DTO for ``POST /api/v1/account-moves`` (ORM ``create``).

    Strict by inheritance from :class:`BaseRestModel` (``strict=True``,
    ``extra='forbid'``): a payload carrying an unknown key, a wrongly-typed
    scalar, or omitting the required ``move_type`` raises a
    :class:`pydantic.ValidationError` that the controller renders as an HTTP
    ``422`` *before* any ``request.env['account.move']`` access (Gate 2).

    Only client-settable fields are declared. Computed / workflow / sequenced
    fields (``name``, ``state``, ``amount_*``, ``payment_state``) are
    intentionally absent and are rejected as extra keys if supplied.
    """

    # Required: the journal-entry / document discriminator. It is the single
    # mandatory field on creation; every other attribute is optional.
    move_type: MoveType

    # Optional descriptive / relational fields (``Optional[...] = None`` so that
    # omission is valid and only supplied keys are forwarded to ``create``).
    ref: Optional[str] = None
    date: Optional[datetime.date] = None
    journal_id: Optional[int] = None
    company_id: Optional[int] = None
    partner_id: Optional[int] = None
    invoice_date: Optional[datetime.date] = None
    invoice_date_due: Optional[datetime.date] = None
    delivery_date: Optional[datetime.date] = None
    invoice_payment_term_id: Optional[int] = None
    payment_reference: Optional[str] = None
    fiscal_position_id: Optional[int] = None
    partner_bank_id: Optional[int] = None
    currency_id: Optional[int] = None
    # One2many to ``account.move.line``: a list of existing line ids to link.
    invoice_line_ids: Optional[list[int]] = None


class AccountMoveUpdate(BaseRestModel):
    """Request DTO for ``PATCH /api/v1/account-moves/{id}`` (ORM ``write``).

    A **partial** update: every field -- including ``move_type`` -- is optional,
    so a client may send only the attributes it wishes to change. Still strict
    (``extra='forbid'``): unknown keys and the read-only fields (``name``,
    ``state``, ``amount_*``, ``payment_state``) are rejected with ``422``.

    Controllers should serialise this model with ``exclude_unset=True`` so that
    only the keys the client actually provided are handed to ``write`` -- a
    missing key must not be interpreted as "set to null".
    """

    move_type: Optional[MoveType] = None
    ref: Optional[str] = None
    date: Optional[datetime.date] = None
    journal_id: Optional[int] = None
    company_id: Optional[int] = None
    partner_id: Optional[int] = None
    invoice_date: Optional[datetime.date] = None
    invoice_date_due: Optional[datetime.date] = None
    delivery_date: Optional[datetime.date] = None
    invoice_payment_term_id: Optional[int] = None
    payment_reference: Optional[str] = None
    fiscal_position_id: Optional[int] = None
    partner_bank_id: Optional[int] = None
    currency_id: Optional[int] = None
    invoice_line_ids: Optional[list[int]] = None


class AccountMoveRead(BaseRestReadModel):
    """Response DTO for a single ``account.move`` record.

    Lenient by inheritance from :class:`BaseRestReadModel`
    (``from_attributes=True``): it is built directly from an ORM record via
    ``AccountMoveRead.model_validate(record)`` and silently drops any ORM
    attribute it does not declare. The declared field set is exactly the set the
    controller reads from the ORM, which is what enforces field-set parity with
    JSON-RPC for the same user and record (Gate 3).

    Unlike the write DTOs, this model exposes the computed / workflow fields:
    the sequenced ``name``, the ``state`` and ``payment_state`` lifecycle
    markers and the computed monetary totals.
    """

    # Primary identifier first, matching the ORM record key ordering.
    id: int
    name: Optional[str] = None
    ref: Optional[str] = None
    date: Optional[datetime.date] = None
    state: Optional[MoveState] = None
    move_type: Optional[MoveType] = None
    journal_id: Optional[int] = None
    company_id: Optional[int] = None
    partner_id: Optional[int] = None
    invoice_date: Optional[datetime.date] = None
    invoice_date_due: Optional[datetime.date] = None
    delivery_date: Optional[datetime.date] = None
    invoice_payment_term_id: Optional[int] = None
    payment_reference: Optional[str] = None
    fiscal_position_id: Optional[int] = None
    partner_bank_id: Optional[int] = None
    currency_id: Optional[int] = None
    # One2many member ids; defaults to an empty list when the move has no lines.
    invoice_line_ids: list[int] = Field(default_factory=list)
    # Computed, read-only monetary totals.
    amount_untaxed: Optional[float] = None
    amount_tax: Optional[float] = None
    amount_total: Optional[float] = None
    amount_residual: Optional[float] = None
    # Computed, read-only payment lifecycle marker (open selection -> ``str``).
    payment_state: Optional[str] = None
    # Standard Odoo computed human-readable label.
    display_name: Optional[str] = None


class AccountMoveList(BaseModel):
    """Paginated collection response for ``GET /api/v1/account-moves``.

    Wraps the page of :class:`AccountMoveRead` items together with a
    :class:`PageMeta` block echoing the ``limit`` / ``offset`` used and the
    unpaginated ``total`` (``search_count``). This is a plain
    :class:`~pydantic.BaseModel` assembled server-side from already-validated
    parts, so it needs neither strict validation nor ``from_attributes``.
    """

    items: list[AccountMoveRead] = Field(default_factory=list)
    meta: PageMeta


__all__ = [
    'AccountMoveCreate',
    'AccountMoveUpdate',
    'AccountMoveRead',
    'AccountMoveList',
]
