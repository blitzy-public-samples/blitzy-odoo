"""Pydantic v2 request/response DTOs for the ``crm.lead`` REST pilot.

This module is one of the five per-model schema modules of the
:mod:`odoo.addons.rest_api.schemas` package. It backs the ``/api/v1/crm-leads``
resource with four data-transfer objects, split into a strict *request* pair
and a lenient *response* pair:

* :class:`CrmLeadCreate` -- body of ``POST /api/v1/crm-leads`` (create).
* :class:`CrmLeadUpdate` -- body of ``PATCH /api/v1/crm-leads/{id}`` (partial
  update); every field is optional so the caller sends only what changes.
* :class:`CrmLeadRead` -- single-record representation returned by ``GET
  /api/v1/crm-leads/{id}`` and embedded in collection responses.
* :class:`CrmLeadList` -- paginated collection returned by ``GET
  /api/v1/crm-leads`` (a list of :class:`CrmLeadRead` plus a
  :class:`~odoo.addons.rest_api.schemas.base.PageMeta`).

Design rules honoured here (AAP sections 0.3.3, 0.6.4 and 0.7):

* **Request DTOs are strict.** :class:`CrmLeadCreate` and :class:`CrmLeadUpdate`
  subclass :class:`~odoo.addons.rest_api.schemas.base.BaseRestModel`
  (``strict=True`` + ``extra='forbid'``), so an unknown key or a wrongly-typed
  scalar raises :class:`pydantic.ValidationError`, which the controller turns
  into an HTTP ``422`` *before* any ORM access (validation Gate 2).
* **Response DTOs are lenient.** :class:`CrmLeadRead` is a plain
  :class:`pydantic.BaseModel` configured with ``from_attributes=True`` so it can
  be built directly from an ORM record/read-dict and silently drops keys it does
  not declare, preserving field-set parity with the ORM (Gate 3).
* **Fields are derived strictly from the source model** ``crm.lead``
  (``addons/crm/models/crm_lead.py``); no field is invented. In particular,
  this Odoo 19.0 tree's ``crm.lead`` has **no** ``mobile`` field, so none is
  declared -- contact reachability is exposed through ``phone`` and
  ``email_from`` only.
* **Read-only / computed fields are exposed for reading but never accepted for
  writing.** ``won_status`` (computed) and ``date_closed`` (``readonly=True``,
  auto-set on close) appear on :class:`CrmLeadRead` only and are absent from the
  request DTOs.

ORM-type -> Python-type mapping applied below: ``Char``/``Html`` -> ``str``;
``Monetary``/``Float`` -> ``float``; ``Many2one`` -> ``int`` (the related record
id); ``Date`` -> :class:`datetime.date`; ``Datetime`` -> :class:`datetime.datetime`;
a stable ``Selection`` -> :data:`typing.Literal`; a ``Selection`` backed by a
shared/open constant (``priority`` over ``crm.stage.AVAILABLE_PRIORITIES``) ->
``str``.

This module intentionally performs **no** ``import odoo``: the schemas are pure
pydantic models with no ORM coupling, which keeps them import-safe wherever they
are consumed (sibling modules at load time, the OpenAPI assembler at request
time).
"""

from __future__ import annotations

# ``datetime`` is required at *runtime*, not merely for static typing: pydantic
# resolves these annotations while building the model's validators, so the name
# must exist in the module namespace. It therefore must NOT be moved into a
# ``typing.TYPE_CHECKING`` block (hence the targeted ``noqa`` for the
# flake8-type-checking rule).
import datetime  # noqa: TC003
from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseRestModel, BaseRestReadModel, PageMeta


class CrmLeadCreate(BaseRestModel):
    """Request body for ``POST /api/v1/crm-leads`` (ORM ``create``).

    Inherits the strict configuration of
    :class:`~odoo.addons.rest_api.schemas.base.BaseRestModel`
    (``strict=True`` + ``extra='forbid'``): any undeclared key -- notably the
    non-existent ``mobile`` field -- or a wrongly-typed value is rejected with a
    ``422`` before the ORM is touched.

    Only ``name`` is genuinely client-required:

    * ``name`` -- the opportunity/lead title (ORM ``Char``, ``required=True``
      with no ORM default), so it is required here.
    * ``type`` -- ``'lead'`` or ``'opportunity'`` (ORM ``Selection``); although
      the column is ORM ``required=True`` it also carries an ORM ``default``
      (``'lead'`` or ``'opportunity'`` depending on the user's groups), so it is
      **not** genuinely client-required and is therefore **optional** here: a
      create that omits it is valid and must receive the Odoo default, exactly as
      an equivalent JSON-RPC ``create`` would (codebase-wins field derivation,
      R7 / G3). Requiring it would wrongly reject such a create. Typed as a
      :data:`~typing.Literal` because the value set is stable and closed.

    Every other field is optional and defaults to ``None`` so callers send only
    the attributes they wish to set; omitted attributes fall back to the ORM's
    own defaults/computations. Computed read-only attributes (``won_status``,
    ``date_closed``) are intentionally not accepted here.
    """

    # --- Required -----------------------------------------------------------
    name: str

    # --- Optional: ORM-defaulted, so NOT marked required (R7 / G3) ----------
    # ``crm.lead.type`` is ORM ``required=True`` but has an ORM ``default``, so a
    # create that omits it is valid and receives the Odoo default. With
    # ``exclude_unset=True`` in the controller, omitting it here lets that ORM
    # default apply -- matching JSON-RPC-equivalent behaviour.
    type: Literal['lead', 'opportunity'] | None = None

    # --- Ownership / routing (Many2one -> id) -------------------------------
    user_id: int | None = None
    team_id: int | None = None
    company_id: int | None = None

    # --- Pipeline management ------------------------------------------------
    stage_id: int | None = None
    # ``priority`` is a Selection over the shared ``crm.stage.AVAILABLE_PRIORITIES``
    # constant; typed as ``str`` rather than a Literal to stay robust to that
    # shared/extensible value set.
    priority: str | None = None

    # --- Revenue / forecasting ----------------------------------------------
    expected_revenue: float | None = None
    # ``probability`` is computed but user-overridable (``readonly=False``), so
    # it is accepted on write as an optional override.
    probability: float | None = None
    date_deadline: datetime.date | None = None

    # --- Customer / contact -------------------------------------------------
    partner_id: int | None = None
    contact_name: str | None = None
    partner_name: str | None = None
    email_from: str | None = None
    phone: str | None = None
    function: str | None = None
    website: str | None = None

    # --- Address ------------------------------------------------------------
    street: str | None = None
    street2: str | None = None
    zip: str | None = None
    city: str | None = None
    state_id: int | None = None
    country_id: int | None = None
    lang_id: int | None = None

    # --- Misc ---------------------------------------------------------------
    description: str | None = None
    referred: str | None = None
    lost_reason_id: int | None = None


class CrmLeadUpdate(BaseRestModel):
    """Request body for ``PATCH /api/v1/crm-leads/{id}`` (ORM ``write``).

    This is the partial-update counterpart of :class:`CrmLeadCreate`: it exposes
    the same writable attribute set but makes **every** field optional --
    including ``name`` and ``type`` -- so a client transmits only the attributes
    it intends to change. Any field left unset is simply absent from the
    resulting ``write`` payload and the stored value is preserved.

    It inherits the same strict configuration
    (``strict=True`` + ``extra='forbid'``) from
    :class:`~odoo.addons.rest_api.schemas.base.BaseRestModel`, so unknown keys
    (again including the non-existent ``mobile``) and wrongly-typed values are
    rejected with a ``422`` before any ORM access. Computed read-only attributes
    (``won_status``, ``date_closed``) remain excluded from the writable set.
    """

    # --- Identity (optional on update) --------------------------------------
    name: str | None = None
    type: Literal['lead', 'opportunity'] | None = None

    # --- Ownership / routing (Many2one -> id) -------------------------------
    user_id: int | None = None
    team_id: int | None = None
    company_id: int | None = None

    # --- Pipeline management ------------------------------------------------
    stage_id: int | None = None
    priority: str | None = None

    # --- Revenue / forecasting ----------------------------------------------
    expected_revenue: float | None = None
    probability: float | None = None
    date_deadline: datetime.date | None = None

    # --- Customer / contact -------------------------------------------------
    partner_id: int | None = None
    contact_name: str | None = None
    partner_name: str | None = None
    email_from: str | None = None
    phone: str | None = None
    function: str | None = None
    website: str | None = None

    # --- Address ------------------------------------------------------------
    street: str | None = None
    street2: str | None = None
    zip: str | None = None
    city: str | None = None
    state_id: int | None = None
    country_id: int | None = None
    lang_id: int | None = None

    # --- Misc ---------------------------------------------------------------
    description: str | None = None
    referred: str | None = None
    lost_reason_id: int | None = None


class CrmLeadRead(BaseRestReadModel):
    """Response representation of a single ``crm.lead`` record.

    Lenient by inheritance from :class:`BaseRestReadModel`
    (``from_attributes=True``): it is built directly from an ORM record or a
    ``read``/``search_read`` dict, and because it is not ``extra='forbid'`` any
    surplus keys returned by the ORM are silently ignored -- exactly what keeps
    the exposed field set aligned with what the ORM would return for the
    authenticated user (field-set parity, Gate 3).

    Every attribute except ``id`` is optional and defaults to ``None`` so the
    model can be populated from a projection that includes only a subset of
    columns. In addition to the writable attributes shared with the request
    DTOs, this model also surfaces the two computed/read-only attributes
    ``date_closed`` and ``won_status`` (which are never accepted on write), and
    the standard ``display_name`` convenience label.

    The controller for ``/api/v1/crm-leads`` reads exactly the fields declared
    here; adding or removing a field here changes the REST projection, so the
    set is kept in deliberate one-to-one correspondence with the ORM columns of
    ``crm.lead``.
    """

    # --- Identity -----------------------------------------------------------
    id: int
    name: str | None = None
    type: Literal['lead', 'opportunity'] | None = None

    # --- Ownership / routing ------------------------------------------------
    user_id: int | None = None
    team_id: int | None = None
    company_id: int | None = None

    # --- Pipeline management ------------------------------------------------
    stage_id: int | None = None
    priority: str | None = None

    # --- Revenue / forecasting ----------------------------------------------
    expected_revenue: float | None = None
    probability: float | None = None
    date_deadline: datetime.date | None = None
    # ``date_closed`` is ``readonly=True`` on the model (auto-set on close): it
    # is read-only exposure only, never part of a request DTO.
    date_closed: datetime.datetime | None = None

    # --- Customer / contact -------------------------------------------------
    partner_id: int | None = None
    contact_name: str | None = None
    partner_name: str | None = None
    email_from: str | None = None
    phone: str | None = None
    function: str | None = None
    website: str | None = None

    # --- Address ------------------------------------------------------------
    street: str | None = None
    street2: str | None = None
    zip: str | None = None
    city: str | None = None
    state_id: int | None = None
    country_id: int | None = None
    lang_id: int | None = None

    # --- Misc ---------------------------------------------------------------
    description: str | None = None
    referred: str | None = None
    lost_reason_id: int | None = None
    # ``won_status`` is a computed Selection (won/lost/pending): read-only
    # exposure only, excluded from the request DTOs.
    won_status: Literal['won', 'lost', 'pending'] | None = None
    display_name: str | None = None


class CrmLeadList(BaseModel):
    """Paginated collection returned by ``GET /api/v1/crm-leads``.

    Wraps the page of records (``items``) together with the pagination metadata
    (``meta``) shared across every ``<Model>List`` response on the REST surface.
    ``items`` defaults to an empty list so an empty page serialises cleanly;
    ``meta`` is required and carries ``limit``/``offset``/``total``.
    """

    items: list[CrmLeadRead] = Field(default_factory=list)
    meta: PageMeta


__all__ = [
    'CrmLeadCreate',
    'CrmLeadList',
    'CrmLeadRead',
    'CrmLeadUpdate',
]
