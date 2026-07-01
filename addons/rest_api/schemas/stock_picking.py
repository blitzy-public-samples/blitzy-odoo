"""Pydantic v2 DTOs for the ``stock.picking`` REST pilot (``/api/v1/stock-pickings``).

This module is one of the five per-model schema modules of the
:mod:`odoo.addons.rest_api.schemas` package. It declares the request and
response Data Transfer Objects (DTOs) that the ``stock.picking`` REST
controller and the OpenAPI assembler consume:

* :class:`StockPickingCreate` -- **strict** request DTO for ``POST`` (create).
* :class:`StockPickingUpdate` -- **strict** request DTO for ``PATCH`` (partial
  update); every field is optional.
* :class:`StockPickingRead` -- **lenient** response DTO for ``GET`` (single) and
  the elements of a collection response.
* :class:`StockPickingList` -- **lenient** response DTO wrapping a paginated
  collection of :class:`StockPickingRead` records plus :class:`~.base.PageMeta`.

Design rules (AAP sections 0.3.3, 0.6.4 and the file mission):

* **Fields are derived strictly from the ORM model** ``stock.picking``
  (``addons/stock/models/stock_picking.py``, ``_name`` at source line 538). No
  field is invented; each maps 1:1 to a real ORM field.
* **Request DTOs subclass** :class:`~.base.BaseRestModel` and are therefore
  strict (``strict=True``) and reject unknown keys (``extra='forbid'``). A
  schema-invalid payload raises :class:`pydantic.ValidationError`, which the
  controller turns into an HTTP ``422`` *before* any ORM access -- the
  anti-corruption boundary (validation Gate 2).
* **Response DTOs are lenient** (plain :class:`pydantic.BaseModel` with
  ``from_attributes=True``): surplus keys returned by the ORM are silently
  dropped, keeping the exposed field set aligned with what the ORM would return
  for the authenticated user (field-set parity, Gate 3).
* **Read-only / computed fields are exposed in the response only.** ``name``
  (auto-generated reference, default ``'/'``, ``readonly=True``), ``state``
  (computed status), ``date_done`` (completion timestamp) and
  ``picking_type_code`` (related mirror of ``picking_type_id.code``) are present
  in :class:`StockPickingRead` but intentionally **excluded** from the write
  DTOs.

There is deliberately **no** ``import odoo`` here: this module must stay
import-safe (it is imported at addon-load time and by the OpenAPI assembler),
depending only on :mod:`pydantic` and the sibling :mod:`.base` module.

Type mapping applied (ORM -> Python/pydantic):

======================  ===========================
ORM field type          Python annotation
======================  ===========================
``Char`` / ``Html``     ``str``
``Many2one``            ``int`` (the related record id)
``One2many``            ``list[int]`` (related record ids)
``Datetime``            ``datetime.datetime``
stable ``Selection``    ``Literal[...]`` (fixed value set)
shared ``Selection``    ``str`` (open / shared-constant value set)
======================  ===========================
"""

from __future__ import annotations

# ``datetime`` is used only inside annotations, but it must remain a real
# runtime import (not a ``TYPE_CHECKING``-only one): because of
# ``from __future__ import annotations`` the annotations are strings that
# pydantic evaluates at model-build time, so the name has to exist at runtime.
# The ``noqa`` therefore silences ruff's TC003, a false positive for pydantic
# models.
import datetime  # noqa: TC003
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseRestModel, PageMeta

# ---------------------------------------------------------------------------
# Stable Selection value sets, mirrored verbatim from the ORM model so the
# generated OpenAPI enum stays in lock-step with ``stock.picking``.
# ---------------------------------------------------------------------------

#: ``stock.picking.state`` -- computed/read-only status (source line 574).
StockPickingState = Literal[
    'draft',
    'waiting',
    'confirmed',
    'assigned',
    'done',
    'cancel',
]

#: ``stock.picking.picking_type_code`` -- related/read-only mirror of
#: ``picking_type_id.code`` (values from ``stock.picking.type.code``,
#: source line 41: incoming / outgoing / internal).
StockPickingTypeCode = Literal[
    'incoming',
    'outgoing',
    'internal',
]


class StockPickingCreate(BaseRestModel):
    """Strict request body for ``POST /api/v1/stock-pickings`` (ORM ``create``).

    Inherits ``strict=True`` and ``extra='forbid'`` from
    :class:`~.base.BaseRestModel`, so any unknown key or wrongly-typed scalar is
    rejected with an HTTP ``422`` before the ORM is touched.

    Only ``picking_type_id`` is required, mirroring the single hard ORM
    requirement that is not auto-computed. ``location_id`` and
    ``location_dest_id`` are ORM-``required`` too, but they are computed with
    ``precompute=True`` from the chosen operation type, so the ORM fills them in
    when omitted; the API therefore exposes them as **optional overrides** --
    making them mandatory here would wrongly reject a valid create that supplies
    only ``picking_type_id``.

    The auto-generated / computed fields ``name``, ``state``, ``date_done`` and
    ``picking_type_code`` are intentionally **not** accepted on create.
    """

    # -- Required -----------------------------------------------------------
    picking_type_id: int = Field(
        description="Operation type (stock.picking.type) driving locations and "
        "sequence. The only strictly required field.",
    )

    # -- Optional overrides (ORM-required but auto-computed from the type) ---
    location_id: int | None = Field(
        default=None,
        description="Source location (stock.location). Auto-computed from the "
        "operation type when omitted.",
    )
    location_dest_id: int | None = Field(
        default=None,
        description="Destination location (stock.location). Auto-computed from "
        "the operation type when omitted.",
    )

    # -- Optional descriptive / relational fields ---------------------------
    origin: str | None = Field(
        default=None,
        description="Reference of the source document.",
    )
    note: str | None = Field(
        default=None,
        description="Free-form notes (HTML).",
    )
    backorder_id: int | None = Field(
        default=None,
        description="Back order of another stock.picking, if any.",
    )
    priority: str | None = Field(
        default=None,
        description="Reservation priority ('0' = Normal, '1' = Urgent).",
    )
    scheduled_date: datetime.datetime | None = Field(
        default=None,
        description="Scheduled processing date/time for the transfer.",
    )
    date_deadline: datetime.datetime | None = Field(
        default=None,
        description="Deadline before which the transfer should be validated.",
    )
    partner_id: int | None = Field(
        default=None,
        description="Contact (res.partner) associated with the transfer.",
    )
    company_id: int | None = Field(
        default=None,
        description="Company (res.company) owning the transfer.",
    )
    user_id: int | None = Field(
        default=None,
        description="Responsible user (res.users).",
    )
    owner_id: int | None = Field(
        default=None,
        description="Owner (res.partner) the products get assigned to on "
        "validation.",
    )
    move_ids: list[int] | None = Field(
        default=None,
        description="Stock moves (stock.move) making up the transfer.",
    )
    move_line_ids: list[int] | None = Field(
        default=None,
        description="Detailed operations (stock.move.line) of the transfer.",
    )


class StockPickingUpdate(BaseRestModel):
    """Strict request body for ``PATCH /api/v1/stock-pickings/{id}`` (ORM ``write``).

    Identical field surface to :class:`StockPickingCreate` but for a **partial**
    update: every field -- including ``picking_type_id`` -- is optional so a
    client may send only the attributes it wants to change. Strictness
    (``extra='forbid'``) is preserved, and the same read-only/computed fields
    (``name``, ``state``, ``date_done``, ``picking_type_code``) remain excluded.
    """

    picking_type_id: int | None = Field(
        default=None,
        description="Operation type (stock.picking.type).",
    )
    location_id: int | None = Field(
        default=None,
        description="Source location (stock.location).",
    )
    location_dest_id: int | None = Field(
        default=None,
        description="Destination location (stock.location).",
    )
    origin: str | None = Field(
        default=None,
        description="Reference of the source document.",
    )
    note: str | None = Field(
        default=None,
        description="Free-form notes (HTML).",
    )
    backorder_id: int | None = Field(
        default=None,
        description="Back order of another stock.picking, if any.",
    )
    priority: str | None = Field(
        default=None,
        description="Reservation priority ('0' = Normal, '1' = Urgent).",
    )
    scheduled_date: datetime.datetime | None = Field(
        default=None,
        description="Scheduled processing date/time for the transfer.",
    )
    date_deadline: datetime.datetime | None = Field(
        default=None,
        description="Deadline before which the transfer should be validated.",
    )
    partner_id: int | None = Field(
        default=None,
        description="Contact (res.partner) associated with the transfer.",
    )
    company_id: int | None = Field(
        default=None,
        description="Company (res.company) owning the transfer.",
    )
    user_id: int | None = Field(
        default=None,
        description="Responsible user (res.users).",
    )
    owner_id: int | None = Field(
        default=None,
        description="Owner (res.partner) the products get assigned to on "
        "validation.",
    )
    move_ids: list[int] | None = Field(
        default=None,
        description="Stock moves (stock.move) making up the transfer.",
    )
    move_line_ids: list[int] | None = Field(
        default=None,
        description="Detailed operations (stock.move.line) of the transfer.",
    )


class StockPickingRead(BaseModel):
    """Lenient response DTO for a single ``stock.picking`` record.

    Built directly from an ORM record (``from_attributes=True``) and used both
    for the single-record ``GET`` and as the element type of
    :class:`StockPickingList`. It is deliberately **not** strict: extra keys the
    ORM may return are ignored, which keeps the response field set aligned with
    ORM/ACL visibility for the authenticated user (field-set parity, Gate 3).

    Unlike the write DTOs, this response surface **does** expose the read-only /
    computed fields ``name``, ``state``, ``date_done`` and ``picking_type_code``,
    matching what a JSON-RPC ``read`` of the same record would return.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Database identifier of the transfer.")
    name: str | None = Field(
        default=None,
        description="Auto-generated reference (read-only; defaults to '/').",
    )
    origin: str | None = Field(
        default=None,
        description="Reference of the source document.",
    )
    note: str | None = Field(
        default=None,
        description="Free-form notes (HTML).",
    )
    backorder_id: int | None = Field(
        default=None,
        description="Back order of another stock.picking, if any.",
    )
    state: StockPickingState | None = Field(
        default=None,
        description="Computed transfer status (read-only).",
    )
    priority: str | None = Field(
        default=None,
        description="Reservation priority ('0' = Normal, '1' = Urgent).",
    )
    scheduled_date: datetime.datetime | None = Field(
        default=None,
        description="Scheduled processing date/time for the transfer.",
    )
    date_deadline: datetime.datetime | None = Field(
        default=None,
        description="Deadline before which the transfer should be validated.",
    )
    date_done: datetime.datetime | None = Field(
        default=None,
        description="Completion timestamp (read-only).",
    )
    location_id: int | None = Field(
        default=None,
        description="Source location (stock.location).",
    )
    location_dest_id: int | None = Field(
        default=None,
        description="Destination location (stock.location).",
    )
    picking_type_id: int | None = Field(
        default=None,
        description="Operation type (stock.picking.type).",
    )
    picking_type_code: StockPickingTypeCode | None = Field(
        default=None,
        description="Related operation-type code (read-only).",
    )
    partner_id: int | None = Field(
        default=None,
        description="Contact (res.partner) associated with the transfer.",
    )
    company_id: int | None = Field(
        default=None,
        description="Company (res.company) owning the transfer.",
    )
    user_id: int | None = Field(
        default=None,
        description="Responsible user (res.users).",
    )
    owner_id: int | None = Field(
        default=None,
        description="Owner (res.partner) assigned on validation.",
    )
    move_ids: list[int] = Field(
        default_factory=list,
        description="Stock moves (stock.move) making up the transfer.",
    )
    move_line_ids: list[int] = Field(
        default_factory=list,
        description="Detailed operations (stock.move.line) of the transfer.",
    )
    display_name: str | None = Field(
        default=None,
        description="Human-readable display name of the transfer.",
    )


class StockPickingList(BaseModel):
    """Lenient response DTO for a paginated ``stock.picking`` collection.

    Wraps the page of records returned by the collection ``GET`` together with
    :class:`~.base.PageMeta` pagination metadata. In the generated OpenAPI
    document, ``items`` renders as an array whose element ``$ref`` points at
    ``StockPickingRead``.
    """

    items: list[StockPickingRead] = Field(
        default_factory=list,
        description="Page of stock.picking records.",
    )
    meta: PageMeta = Field(description="Pagination metadata for this page.")


__all__ = [
    'StockPickingCreate',
    'StockPickingList',
    'StockPickingRead',
    'StockPickingUpdate',
]
