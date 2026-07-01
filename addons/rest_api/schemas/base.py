"""Foundational pydantic v2 schemas for the ``rest_api`` REST surface.

This module is the base layer of the :mod:`odoo.addons.rest_api.schemas`
package. It defines the shared building blocks that every per-model schema
module (``res_partner``, ``sale_order``, ``account_move``, ``stock_picking``,
``crm_lead``) and the OpenAPI assembler (:mod:`odoo.addons.rest_api.openapi`)
build upon:

* :class:`BaseRestModel` -- the *strict* base class for every REST **request**
  DTO (``Create``/``Update``). It is the anti-corruption boundary of the REST
  surface: because it is configured with ``strict=True`` and ``extra='forbid'``,
  any unexpected key or wrongly-typed scalar raises a
  :class:`pydantic.ValidationError`, which the controllers translate into an
  HTTP ``422`` response *before* any ORM access occurs.
* :class:`BaseRestReadModel` -- the *lenient* base class for every REST
  **response** DTO (``Read``/``List``). It enables construction directly from
  ORM records via ``from_attributes=True`` and silently drops keys the DTO does
  not declare, preserving field-set parity with the ORM.
* :class:`RestErrorResponse` -- the canonical REST error envelope. Its field
  names are a hard cross-agent contract: they must stay byte-identical to the
  JSON body emitted by ``RestDispatcher.handle_error`` in ``odoo/http.py`` and
  to the ``#/components/schemas/RestErrorResponse`` reference emitted by the
  OpenAPI assembler.
* :class:`PageMeta` -- pagination metadata embedded in every ``<Model>List``
  response.

Design constraints (see AAP sections 0.2 and 0.7):

* These are **plain pydantic ``BaseModel`` subclasses -- NOT Odoo ORM models**.
  There is intentionally no ``_name``, no ``env``, no persistence and, above
  all, **no** ``import odoo`` anywhere in this module. It must remain import-safe
  in any context (it is imported at module-load time by every sibling schema
  module and at request time by the OpenAPI assembler, potentially outside a
  live Odoo registry).
* Only the ``pydantic`` dependency is used, and only its v2 public API
  (:class:`~pydantic.BaseModel`, :func:`~pydantic.Field`,
  :class:`~pydantic.ConfigDict`). No pydantic v1 idioms (``class Config``,
  ``Schema(...)``, ``@validator``) appear here.
* No business fields live here -- those belong to the per-model schema modules.
"""

from pydantic import BaseModel, ConfigDict, Field


class BaseRestModel(BaseModel):
    """Base class for all REST **request** DTOs (``Create`` / ``Update``).

    The combination of ``strict=True`` and ``extra='forbid'`` makes every
    subclass a strict validation gate -- the anti-corruption boundary between
    the raw HTTP wire format and the Odoo ORM:

    * ``extra='forbid'`` -- any key not declared on the model is rejected with a
      pydantic ``extra_forbidden`` error (rendered as ``additionalProperties:
      false`` in the generated JSON Schema / OpenAPI document).
    * ``strict=True`` -- no lax type coercion is performed. For example, the
      string ``"123"`` is **not** silently coerced into the integer ``123``;
      instead an ``int_type`` (or ``string_type`` / ``bool_type`` / ...) error
      is raised.

    Both settings are mandatory: together they guarantee that a schema-invalid
    payload raises :class:`pydantic.ValidationError`, which the REST controllers
    translate into an HTTP ``422`` response *before* touching
    ``request.env[model]`` -- satisfying the "extra fields rejected" and
    "``422`` before any ORM access" requirements (AAP G3, validation Gate 2).

    This class deliberately declares **no fields of its own**; it is a
    configuration-only base. Concrete request DTOs (``PartnerCreate``,
    ``PartnerUpdate``, ...) subclass it and add their model-specific fields.

    Note for controller authors: under ``strict=True``, ISO-8601 date/datetime
    *strings* validate only through :meth:`pydantic.BaseModel.model_validate_json`
    (parsing the raw request body), not through
    :meth:`pydantic.BaseModel.model_validate` on a pre-parsed ``dict`` (which
    would reject them with a ``date_type`` error). Controllers should therefore
    validate the raw JSON body rather than a pre-decoded mapping.
    """

    model_config = ConfigDict(strict=True, extra='forbid')


class BaseRestReadModel(BaseModel):
    """Base class for all REST **response** DTOs (``Read`` / ``List``).

    Response DTOs are populated server-side from ORM data, so they must be
    *lenient* rather than strict. ``from_attributes=True`` lets a DTO be built
    directly from an ORM record (or any attribute-bearing object) via
    :meth:`pydantic.BaseModel.model_validate`, in addition to plain mappings.

    Response models must **never** be strict or use ``extra='forbid'``: surplus
    keys sourced from the ORM are simply ignored, which is exactly what keeps the
    exposed field set aligned with what the ORM would return for the
    authenticated user (field-set parity -- AAP section 0.6.4). Concrete
    ``Read`` / ``List`` DTOs subclass this class and declare the fields they
    expose.
    """

    model_config = ConfigDict(from_attributes=True)


class RestErrorResponse(BaseModel):
    """Canonical error envelope for the REST surface.

    This model mirrors, byte-for-byte, the JSON body emitted by
    ``RestDispatcher.handle_error`` in ``odoo/http.py`` and is referenced as
    ``#/components/schemas/RestErrorResponse`` by the OpenAPI assembler for the
    ``401`` / ``404`` / ``422`` responses. The field names and their order are a
    hard cross-agent contract and must not diverge:

    * ``status`` -- the numeric HTTP status code (e.g. ``422``, ``404``,
      ``401``).
    * ``code`` -- a stable, machine-readable error identifier
      (e.g. ``'validation_error'``, ``'not_found'``, ``'unauthorized'``).
    * ``message`` -- a human-readable description of the error.
    * ``details`` -- an optional list of structured, per-field error entries
      (for a ``422`` this typically holds ``{'loc': ..., 'msg': ..., 'type':
      ...}`` dictionaries derived from :meth:`pydantic.ValidationError.errors`).
      It defaults to an empty list.

    This envelope is intentionally **distinct** from the JSON-RPC error envelope
    ``{code, message, data}``; the two error contracts must never be mixed
    (AAP section 0.2.2).

    Being a server-generated **response** model, this is a plain
    :class:`~pydantic.BaseModel` -- it is neither strict nor ``extra``-forbidding.
    """

    status: int
    code: str
    message: str
    details: list = Field(default_factory=list)


class PageMeta(BaseModel):
    """Pagination metadata carried by every ``<Model>List`` response.

    * ``limit`` -- the maximum number of records requested (echoes the ``limit``
      query parameter honoured by the collection ``GET``).
    * ``offset`` -- the number of records skipped (echoes the ``offset`` query
      parameter).
    * ``total`` -- the total number of records matching the query *before*
      pagination, i.e. the unpaginated ``search_count``.

    Being a server-generated **response** model, this is a plain
    :class:`~pydantic.BaseModel`.
    """

    limit: int
    offset: int
    total: int


__all__ = [
    'BaseRestModel',
    'BaseRestReadModel',
    'PageMeta',
    'RestErrorResponse',
]
