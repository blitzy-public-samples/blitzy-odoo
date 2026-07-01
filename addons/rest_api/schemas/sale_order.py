"""Pydantic v2 request/response DTOs for the ``sale.order`` REST resource.

This module is part of the :mod:`odoo.addons.rest_api.schemas` package. It
defines the four data-transfer objects that shape every payload exchanged over
the ``/api/v1/sale-orders`` REST endpoints served by the ``RestDispatcher``:

* :class:`SaleOrderCreate` -- strict request body for ``POST`` (create).
* :class:`SaleOrderUpdate` -- strict, fully-optional request body for ``PATCH``
  (partial update).
* :class:`SaleOrderRead` -- lenient response body for a single order.
* :class:`SaleOrderList` -- lenient, paginated collection response.

Field provenance
----------------
Every field is derived directly from the authoritative ORM definition of the
``sale.order`` model in ``addons/sale/models/sale_order.py``; no field is
invented. The ORM ``fields`` types are mapped to Python / pydantic types as
follows: ``Char`` / ``Html`` -> ``str``, ``Monetary`` -> ``float``,
``Many2one`` -> ``int`` (the related record id), ``One2many`` -> ``list[int]``
(a list of related record ids), ``Date`` -> :class:`datetime.date`,
``Datetime`` -> :class:`datetime.datetime`, and a stable ``Selection`` ->
:data:`typing.Literal`.

Read-only / server-managed fields
----------------------------------
The following ``sale.order`` fields are computed, workflow-driven or otherwise
server-assigned, so they are **excluded** from the write DTOs
(:class:`SaleOrderCreate` / :class:`SaleOrderUpdate`) and exposed only on
:class:`SaleOrderRead`:

* ``name`` -- the order reference (auto-sequenced, e.g. ``S00001``).
* ``state`` -- the quotation/sale workflow status (``draft`` -> ``sent`` ->
  ``sale`` / ``cancel``); it is ``readonly=True`` on the model.
* ``amount_untaxed`` / ``amount_tax`` / ``amount_total`` -- computed monetary
  totals (``compute='_compute_amounts'``).
* ``invoice_status`` -- computed invoicing status.

Request vs response strictness
------------------------------
Request DTOs subclass :class:`~odoo.addons.rest_api.schemas.base.BaseRestModel`
(``strict=True`` + ``extra='forbid'``), so any unknown key or wrongly-typed
scalar raises :class:`pydantic.ValidationError`, which the controllers turn into
an HTTP ``422`` *before* any ORM access occurs (validation Gate 2). Because
``strict=True`` disables lax coercion, ISO-8601 date/datetime *strings* validate
only through :meth:`pydantic.BaseModel.model_validate_json` (parsing the raw
request body), not through :meth:`~pydantic.BaseModel.model_validate` on a
pre-decoded ``dict``; controllers must therefore validate the raw JSON body.

Response DTOs are plain, lenient :class:`pydantic.BaseModel` subclasses built
from ORM records via ``from_attributes=True``; surplus ORM keys are ignored,
preserving field-set parity with what the ORM returns for the authenticated
user (AAP section 0.6.4, Gate 3).

This module contains **no** ``import odoo`` and defines no ORM model; it depends
only on pydantic v2 and on the shared :mod:`~odoo.addons.rest_api.schemas.base`
building blocks.
"""

from __future__ import annotations

# ``datetime`` MUST remain a runtime import (not a TYPE_CHECKING-only one):
# pydantic evaluates these annotations at model-build time to construct the
# validators, so hiding ``datetime`` behind ``TYPE_CHECKING`` would raise
# ``PydanticUserError: ... is not fully defined``. The TC003 hint is therefore
# a false positive here and is suppressed intentionally.
import datetime  # noqa: TC003
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseRestModel, PageMeta


class SaleOrderCreate(BaseRestModel):
    """Strict request body for creating a ``sale.order`` (``POST``).

    Only client-settable fields are accepted. ``partner_id`` (the customer) is
    the sole required field: on the ORM model it is ``required=True`` with no
    default. Every other field is optional -- the ORM supplies sensible defaults
    when they are omitted (for example ``date_order`` defaults to the current
    time and ``company_id`` to the current company).

    Computed, workflow-driven and auto-sequenced fields (``name``, ``state``,
    ``amount_untaxed``, ``amount_tax``, ``amount_total``, ``invoice_status``)
    are intentionally **not** accepted here; because the base model sets
    ``extra='forbid'``, supplying any of them -- or any other unknown key --
    raises a ``422`` validation error before the ORM is touched.
    """

    # Required: the customer the order is placed for (``res.partner`` id).
    partner_id: int

    # Optional scalar and relational fields (ORM-defaulted when omitted).
    company_id: Optional[int] = None
    date_order: Optional[datetime.datetime] = None
    validity_date: Optional[datetime.date] = None
    client_order_ref: Optional[str] = None
    commitment_date: Optional[datetime.datetime] = None
    note: Optional[str] = None
    pricelist_id: Optional[int] = None
    currency_id: Optional[int] = None
    user_id: Optional[int] = None
    team_id: Optional[int] = None
    payment_term_id: Optional[int] = None
    fiscal_position_id: Optional[int] = None
    # Related order lines expressed as a list of ``sale.order.line`` ids.
    order_line: Optional[list[int]] = None


class SaleOrderUpdate(BaseRestModel):
    """Strict request body for partially updating a ``sale.order`` (``PATCH``).

    Every field is optional -- including ``partner_id`` -- so a client may send
    only the subset of fields it wishes to change. The same read-only /
    server-managed fields excluded from :class:`SaleOrderCreate` remain excluded
    here, and ``extra='forbid'`` still rejects any unknown key with a ``422``.
    """

    partner_id: Optional[int] = None
    company_id: Optional[int] = None
    date_order: Optional[datetime.datetime] = None
    validity_date: Optional[datetime.date] = None
    client_order_ref: Optional[str] = None
    commitment_date: Optional[datetime.datetime] = None
    note: Optional[str] = None
    pricelist_id: Optional[int] = None
    currency_id: Optional[int] = None
    user_id: Optional[int] = None
    team_id: Optional[int] = None
    payment_term_id: Optional[int] = None
    fiscal_position_id: Optional[int] = None
    order_line: Optional[list[int]] = None


class SaleOrderRead(BaseModel):
    """Lenient response body for a single ``sale.order`` record.

    This DTO is populated server-side from an ORM record, so it is deliberately
    lenient: ``from_attributes=True`` allows construction directly from a record
    (or from a ``read()`` mapping) and unknown keys are silently ignored. It
    must never be strict, otherwise surplus ORM keys would break serialization
    and the field-set parity guarantee with JSON-RPC.

    ``id`` is always present; every other field is optional because a given user
    may lack read access to some of them (in which case the controller simply
    omits them), keeping the exposed field set aligned with what the ORM returns
    for that user.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: Optional[str] = None
    partner_id: Optional[int] = None
    company_id: Optional[int] = None
    state: Optional[Literal['draft', 'sent', 'sale', 'cancel']] = None
    date_order: Optional[datetime.datetime] = None
    validity_date: Optional[datetime.date] = None
    client_order_ref: Optional[str] = None
    commitment_date: Optional[datetime.datetime] = None
    note: Optional[str] = None
    pricelist_id: Optional[int] = None
    currency_id: Optional[int] = None
    user_id: Optional[int] = None
    team_id: Optional[int] = None
    payment_term_id: Optional[int] = None
    fiscal_position_id: Optional[int] = None
    order_line: list[int] = Field(default_factory=list)
    amount_untaxed: Optional[float] = None
    amount_tax: Optional[float] = None
    amount_total: Optional[float] = None
    invoice_status: Optional[str] = None
    display_name: Optional[str] = None


class SaleOrderList(BaseModel):
    """Lenient, paginated collection response for ``sale.order``.

    Wraps the page of :class:`SaleOrderRead` items returned by a collection
    ``GET`` together with :class:`~odoo.addons.rest_api.schemas.base.PageMeta`
    pagination metadata (``limit`` / ``offset`` / ``total``).
    """

    items: list[SaleOrderRead] = Field(default_factory=list)
    meta: PageMeta


__all__ = [
    'SaleOrderCreate',
    'SaleOrderList',
    'SaleOrderRead',
    'SaleOrderUpdate',
]
