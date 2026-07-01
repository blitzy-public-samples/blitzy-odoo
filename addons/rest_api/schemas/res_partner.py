"""Pydantic request/response DTOs for the ``res.partner`` REST resource.

Part of the :mod:`odoo.addons.rest_api.schemas` package. Defines the four
Data-Transfer Objects that shape the ``/api/v1/partners`` endpoints of the
additive REST surface:

* :class:`PartnerCreate` -- request body for ``POST /api/v1/partners`` (ORM
  ``create``). Strict: extra or wrongly-typed keys raise a
  :class:`pydantic.ValidationError` that the controller renders as HTTP
  ``422`` *before* any ORM access (AAP G3 / validation Gate 2).
* :class:`PartnerUpdate` -- request body for ``PATCH /api/v1/partners/{id}``
  (ORM ``write``). Strict as well, but every field is optional so a caller
  may update any subset of fields (partial update semantics).
* :class:`PartnerRead` -- response body for the single-record and
  collection-item shape (ORM ``read`` / ``search_read``). Lenient: it is
  built server-side from ORM data and silently drops keys it does not
  declare, which is what preserves field-set parity with an equivalent
  JSON-RPC read for the same user (AAP section 0.6.4 / Gate 3).
* :class:`PartnerList` -- response wrapper for the collection ``GET``: a list
  of :class:`PartnerRead` items plus a :class:`PageMeta` pagination block.

Design constraints (AAP sections 0.2, 0.7 and the file's own directive):

* Pure pydantic, no Odoo. There is intentionally no ``import odoo`` and no
  ``_name``; these are plain pydantic v2 models, not ORM models. The module
  stays import-safe outside a live Odoo registry (it is imported at
  module-load time by the package and at request time by the OpenAPI
  assembler).
* Fields are derived strictly from the authoritative source
  ``odoo/addons/base/models/res_partner.py`` -- no invented fields. In this
  Odoo 19.0 tree the ``res.partner`` model has no ``mobile`` field and no
  ``title`` field, so neither appears here.
* Odoo -> pydantic type mapping applied consistently: ``Char`` / ``Text`` /
  ``Html`` -> ``str``; ``Integer`` -> ``int``; ``Boolean`` -> ``bool``;
  ``Many2one`` -> ``int`` (related record id); ``Many2many`` /
  ``One2many`` -> ``list[int]`` (related record ids); a ``Selection`` with a
  *stable* value set -> :data:`typing.Literal`; a ``Selection`` whose values
  are *dynamic* (installed languages, timezones) -> ``str``.

The request base :class:`BaseRestModel`, the read base
:class:`BaseRestReadModel`, and :class:`PageMeta` are imported from the
sibling :mod:`odoo.addons.rest_api.schemas.base` module.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .base import BaseRestModel, BaseRestReadModel, PageMeta


class PartnerCreate(BaseRestModel):
    """Request DTO for creating a partner (``POST /api/v1/partners``).

    Subclasses :class:`BaseRestModel`, so it inherits ``strict=True`` and
    ``extra='forbid'``: any undeclared key or loosely-typed scalar is
    rejected with a :class:`pydantic.ValidationError` that the controller
    maps to HTTP ``422`` *before* touching ``request.env['res.partner']``.

    ``name`` is the only required field. Although ``res.partner.name`` is not
    ORM-level ``required=True`` (it becomes mandatory only through the model's
    business logic), it is the essential human identifier of a partner, so the
    REST contract requires it on create. Every other field is optional and,
    when omitted, is simply not forwarded to ``create`` -- letting the ORM
    apply its own defaults / computes.
    """

    # -- Identity -----------------------------------------------------------
    name: str  # Char; required by the REST contract.
    ref: Optional[str] = None  # Char -- reference.

    # -- Localization (dynamic Selection -> str) ----------------------------
    lang: Optional[str] = None  # Selection(_lang_get); installed languages.
    tz: Optional[str] = None  # Selection(_tzs); IANA timezones.

    # -- Tax / web ----------------------------------------------------------
    vat: Optional[str] = None  # Char -- Tax ID.
    website: Optional[str] = None  # Char -- website link.

    # -- Descriptive --------------------------------------------------------
    comment: Optional[str] = None  # Html -> str; internal notes.
    function: Optional[str] = None  # Char -- job position.

    # -- Address type (stable Selection -> Literal) -------------------------
    type: Optional[Literal['contact', 'invoice', 'delivery', 'other']] = None

    # -- Postal address -----------------------------------------------------
    street: Optional[str] = None  # Char.
    street2: Optional[str] = None  # Char.
    zip: Optional[str] = None  # Char.
    city: Optional[str] = None  # Char.
    state_id: Optional[int] = None  # M2o res.country.state -> id.
    country_id: Optional[int] = None  # M2o res.country -> id.

    # -- Contact channels ---------------------------------------------------
    email: Optional[str] = None  # Char. (no `mobile` field exists)
    phone: Optional[str] = None  # Char.

    # -- Company classification ---------------------------------------------
    is_company: Optional[bool] = None  # Boolean.
    # company_type is a computed+inverse Selection with a stable value set;
    # it may be supplied on create and its inverse writes ``is_company``.
    company_type: Optional[Literal['person', 'company']] = None

    # -- Relations ----------------------------------------------------------
    parent_id: Optional[int] = None  # M2o res.partner -> id.
    category_id: Optional[list[int]] = None  # M2m res.partner.category.
    user_id: Optional[int] = None  # M2o res.users (salesperson) -> id.
    company_id: Optional[int] = None  # M2o res.company -> id.
    industry_id: Optional[int] = None  # M2o res.partner.industry -> id.

    # -- Lifecycle ----------------------------------------------------------
    active: Optional[bool] = None  # Boolean -- archive flag.


class PartnerUpdate(BaseRestModel):
    """Request DTO for a partial partner update (``PATCH .../{id}``).

    Subclasses :class:`BaseRestModel`, so it remains strict (``strict=True``,
    ``extra='forbid'``) -- an unknown or wrongly-typed key still yields a
    ``422``. Unlike :class:`PartnerCreate`, **every** field (including
    ``name``) is optional: a PATCH may carry any subset of fields, and only
    the supplied fields are forwarded to the ORM ``write``. The field set is
    otherwise identical to :class:`PartnerCreate`.
    """

    # -- Identity -----------------------------------------------------------
    name: Optional[str] = None  # Char; optional for partial update.
    ref: Optional[str] = None  # Char.

    # -- Localization (dynamic Selection -> str) ----------------------------
    lang: Optional[str] = None  # Selection(_lang_get).
    tz: Optional[str] = None  # Selection(_tzs).

    # -- Tax / web ----------------------------------------------------------
    vat: Optional[str] = None  # Char.
    website: Optional[str] = None  # Char.

    # -- Descriptive --------------------------------------------------------
    comment: Optional[str] = None  # Html -> str.
    function: Optional[str] = None  # Char.

    # -- Address type (stable Selection -> Literal) -------------------------
    type: Optional[Literal['contact', 'invoice', 'delivery', 'other']] = None

    # -- Postal address -----------------------------------------------------
    street: Optional[str] = None  # Char.
    street2: Optional[str] = None  # Char.
    zip: Optional[str] = None  # Char.
    city: Optional[str] = None  # Char.
    state_id: Optional[int] = None  # M2o res.country.state -> id.
    country_id: Optional[int] = None  # M2o res.country -> id.

    # -- Contact channels ---------------------------------------------------
    email: Optional[str] = None  # Char.
    phone: Optional[str] = None  # Char.

    # -- Company classification ---------------------------------------------
    is_company: Optional[bool] = None  # Boolean.
    company_type: Optional[Literal['person', 'company']] = None

    # -- Relations ----------------------------------------------------------
    parent_id: Optional[int] = None  # M2o res.partner -> id.
    category_id: Optional[list[int]] = None  # M2m res.partner.category.
    user_id: Optional[int] = None  # M2o res.users -> id.
    company_id: Optional[int] = None  # M2o res.company -> id.
    industry_id: Optional[int] = None  # M2o res.partner.industry -> id.

    # -- Lifecycle ----------------------------------------------------------
    active: Optional[bool] = None  # Boolean -- archive flag.


class PartnerRead(BaseRestReadModel):
    """Response DTO for a single partner (single-read and collection item).

    Subclasses :class:`BaseRestReadModel`, so it is **lenient**:
    ``from_attributes=True`` allows construction directly from an ORM record,
    and undeclared keys returned by the ORM (e.g. ``__last_update`` or
    relation name/label tuples the controller has not reduced to ids) are
    silently dropped rather than raising. This leniency keeps the exposed
    field set aligned with what the ORM would return for the authenticated
    user (field-set parity -- AAP section 0.6.4 / Gate 3).

    All business scalars are ``Optional`` because Odoo returns ``False`` for
    an empty ``Char`` / ``Many2one`` value; the controller coerces
    ``False -> None`` (and a ``(id, name)`` relation pair -> ``id``) before
    validating, so the lenient typing here makes that coercion forgiving.
    ``category_id`` defaults to an empty list because a many-to-many always
    reads back as a list of ids.

    Field-set contract: the controller must ``read`` / ``search_read``
    exactly the business fields declared here so that a REST read returns the
    same visible field set as an equivalent JSON-RPC read for the same user.
    """

    # -- Identity -----------------------------------------------------------
    id: int  # Record id (always present on a read).
    name: Optional[str] = None  # Char.
    ref: Optional[str] = None  # Char.

    # -- Localization -------------------------------------------------------
    lang: Optional[str] = None  # Selection(_lang_get).
    tz: Optional[str] = None  # Selection(_tzs).

    # -- Tax / web ----------------------------------------------------------
    vat: Optional[str] = None  # Char.
    website: Optional[str] = None  # Char.

    # -- Descriptive --------------------------------------------------------
    comment: Optional[str] = None  # Html -> str.
    function: Optional[str] = None  # Char.

    # -- Address type -------------------------------------------------------
    type: Optional[Literal['contact', 'invoice', 'delivery', 'other']] = None

    # -- Postal address -----------------------------------------------------
    street: Optional[str] = None  # Char.
    street2: Optional[str] = None  # Char.
    zip: Optional[str] = None  # Char.
    city: Optional[str] = None  # Char.
    state_id: Optional[int] = None  # M2o res.country.state -> id.
    country_id: Optional[int] = None  # M2o res.country -> id.

    # -- Contact channels ---------------------------------------------------
    email: Optional[str] = None  # Char.
    phone: Optional[str] = None  # Char.

    # -- Company classification ---------------------------------------------
    is_company: Optional[bool] = None  # Boolean.
    company_type: Optional[Literal['person', 'company']] = None

    # -- Relations ----------------------------------------------------------
    parent_id: Optional[int] = None  # M2o res.partner -> id.
    category_id: list[int] = Field(default_factory=list)  # M2m -> ids.
    user_id: Optional[int] = None  # M2o res.users -> id.
    company_id: Optional[int] = None  # M2o res.company -> id.
    industry_id: Optional[int] = None  # M2o res.partner.industry -> id.

    # -- Lifecycle ----------------------------------------------------------
    active: Optional[bool] = None  # Boolean -- archive flag.

    # -- Convenience (universally readable computed identifier) -------------
    display_name: Optional[str] = None  # Computed label; optional.


class PartnerList(BaseModel):
    """Paginated collection response for ``GET /api/v1/partners``.

    A plain, lenient :class:`pydantic.BaseModel` wrapper holding the page of
    :class:`PartnerRead` items and a :class:`PageMeta` pagination block
    (``limit`` / ``offset`` / ``total``). In the generated OpenAPI document
    the ``items`` array references ``#/components/schemas/PartnerRead`` and
    ``meta`` references ``#/components/schemas/PageMeta``.
    """

    items: list[PartnerRead] = Field(default_factory=list)
    meta: PageMeta


__all__ = [
    'PartnerCreate',
    'PartnerUpdate',
    'PartnerRead',
    'PartnerList',
]
