"""REST CRUD controller for the ``res.partner`` pilot model.

This module exposes full Create/Read/Update/Delete semantics for
``res.partner`` under the versioned ``/api/v1/partners`` path of the additive
REST surface introduced by the :mod:`odoo.addons.rest_api` addon. It is the
**canonical** per-model controller: the four sibling controllers
(``sale_order``, ``account_move``, ``stock_picking``, ``crm_lead``) mirror this
structure exactly, swapping only the target model, base path and pydantic DTOs.

Design contract (AAP sections 0.3.2, 0.6.4, 0.6.5)
--------------------------------------------------
The controller is deliberately **thin**. Every cross-cutting concern is handled
by the reused serving pipeline, never re-implemented here:

* **Authentication** is performed by ``_auth_method_rest_bearer`` (added by the
  addon's ``ir.http`` inheritance) during ``ir.http._authenticate(endpoint)``,
  *before* dispatch. It accepts an API key or an OAuth 2.0 bearer token, binds
  ``request.env`` to the authenticated user and rejects session cookies,
  raising ``werkzeug.exceptions.Unauthorized`` (HTTP 401) when no valid token is
  present. This controller writes no authentication code; it merely declares
  ``auth='rest_bearer'`` on every route.
* **Dispatch / response wrapping** is performed by ``RestDispatcher`` in
  ``odoo/http.py``: it merges the JSON body and path parameters into
  ``request.params`` and delegates through ``registry['ir.http']._dispatch``.
  An endpoint returning a plain ``dict`` is wrapped into a ``200`` JSON response
  automatically; an endpoint returning a :class:`~odoo.http.Response` (used for
  the ``204`` delete) is passed through unchanged.
* **Error rendering** is performed by ``RestDispatcher.handle_error`` which
  emits the REST envelope ``{status, code, message, details}``. This controller
  simply lets exceptions propagate: a pydantic ``ValidationError`` becomes a
  ``422`` (``code='validation_error'`` with per-field ``details``), a
  ``werkzeug`` ``NotFound`` becomes a ``404``, and ORM ``AccessError`` /
  ``MissingError`` / ``UserError`` map to ``403`` / ``404`` / ``422``. It never
  builds an error envelope itself and never catches ``ValidationError``.

The two guarantees this controller is responsible for are:

* **Validation gate (Gate 2).** Each write verb validates the *raw* request
  body against a strict pydantic DTO (``extra='forbid'``, ``strict=True``)
  **before** any ``request.env['res.partner']`` access, so a schema-invalid
  payload yields ``422`` with zero ORM side effects.
* **Authorization parity (Gate 3).** Every data operation is executed through
  ``request.env['res.partner'].<op>()`` bound to the authenticated user -- no
  ``sudo()``, no direct SQL, no parallel access path -- so ``ir.model.access``,
  ``ir.rule`` and field-group filtering apply identically to an equivalent
  JSON-RPC call. The exposed field set is derived from the response DTO
  (:func:`PartnerController._read_fields`), keeping REST reads field-for-field
  aligned with a JSON-RPC read of the same fields for the same user.

HTTP verb -> ORM operation mapping (AAP section 0.3.2)
------------------------------------------------------
====== ================================== ============== ============ =========
Verb   Path                               ORM operation  Cursor       Permission
====== ================================== ============== ============ =========
GET    ``/api/v1/partners``               ``search_read``read-only    ``read``
GET    ``/api/v1/partners/{record_id}``   ``read``       read-only    ``read``
POST   ``/api/v1/partners``               ``create``     read-write   ``create``
PATCH  ``/api/v1/partners/{record_id}``   ``write``      read-write   ``write``
DELETE ``/api/v1/partners/{record_id}``   ``unlink``     read-write   ``unlink``
====== ================================== ============== ============ =========

GET routes declare ``readonly=True`` so they run on the read-only replica
cursor; the write verbs use the standard read/write cursor.
"""

import json

import werkzeug.exceptions

from odoo.fields import Command
from odoo.http import Controller, request, route

from odoo.addons.rest_api.schemas.base import PageMeta
from odoo.addons.rest_api.schemas.res_partner import (
    PartnerCreate,
    PartnerList,
    PartnerRead,
    PartnerUpdate,
)

# Maximum page size a client may request on the collection endpoint. The
# ``limit`` query parameter is clamped to this ceiling to bound the amount of
# work a single request can trigger, mirroring the defensive pagination limits
# used elsewhere in the platform.
MAX_PAGE_SIZE = 200

# Default page size when the client does not supply a ``limit`` query
# parameter. Matches the ORM's own conventional default search window.
DEFAULT_PAGE_SIZE = 80


class PartnerController(Controller):
    """Thin REST controller exposing ``/api/v1/partners`` CRUD endpoints.

    All five endpoints share ``type='rest'`` and ``auth='rest_bearer'``; the two
    ``GET`` endpoints additionally declare ``readonly=True``. Each endpoint does
    exactly three things -- validate (for write verbs), delegate to the ORM
    bound to the authenticated user, and serialize -- and lets any raised
    exception propagate to ``RestDispatcher.handle_error``.
    """

    # ------------------------------------------------------------------
    # Collection endpoint -- GET /api/v1/partners  (ORM: search_read)
    # ------------------------------------------------------------------
    @route(
        '/api/v1/partners',
        type='rest',
        auth='rest_bearer',
        methods=['GET'],
        readonly=True,
    )
    def list_partners(self, **kwargs):
        """List partners (paginated collection).

        Reads ``limit`` / ``offset`` / ``domain`` from the query string,
        performs a ``search_read`` restricted to the DTO field set (so the ORM
        applies record rules and field-group filtering for the current user),
        and returns a :class:`PartnerList` payload with pagination metadata.

        :return: JSON-native ``dict`` shaped as :class:`PartnerList`
            (``{"items": [...], "meta": {"limit", "offset", "total"}}``); the
            dispatcher wraps it in an HTTP ``200`` response.
        """
        limit, offset, domain = self._read_query()
        model = request.env['res.partner']
        fields = self._read_fields()
        # ORM operation: search_read (record rules + field groups enforced).
        rows = model.search_read(domain, fields, limit=limit, offset=offset)
        # Unpaginated total for the pagination block.
        total = model.search_count(domain)
        items = [self._serialize_row(model, row) for row in rows]
        payload = PartnerList(
            items=items,
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )
        return payload.model_dump(mode='json')

    # ------------------------------------------------------------------
    # Create endpoint -- POST /api/v1/partners  (ORM: create)
    # ------------------------------------------------------------------
    @route(
        '/api/v1/partners',
        type='rest',
        auth='rest_bearer',
        methods=['POST'],
    )
    def create_partner(self, **kwargs):
        """Create a partner.

        The raw request body is validated against :class:`PartnerCreate`
        **before** any ORM access. Under the DTO's ``strict=True`` /
        ``extra='forbid'`` configuration an unknown key or wrongly-typed value
        raises a pydantic ``ValidationError`` which propagates uncaught and is
        rendered as HTTP ``422`` -- with the partner table left untouched
        (validation Gate 2).

        Only the fields explicitly supplied by the client
        (``exclude_unset=True``) are forwarded to ``create`` so the ORM's own
        defaults and computes are preserved for omitted fields.

        :return: the created record serialized as :class:`PartnerRead`.
        """
        # Validate the RAW JSON body (not a pre-parsed dict): under strict mode
        # ``model_validate_json`` correctly parses scalar/date literals and sees
        # exactly the client-sent keys for ``extra='forbid'`` enforcement.
        dto = PartnerCreate.model_validate_json(
            request.httprequest.get_data(as_text=True),
        )
        model = request.env['res.partner']
        # Translate any x2many list-of-id payloads (e.g. ``category_id``) into
        # explicit Odoo commands before create -- a bare id list would only
        # *link* records rather than set the full relation (see
        # :meth:`_to_orm_write_values`).
        values = self._to_orm_write_values(
            model, dto.model_dump(exclude_unset=True),
        )
        # ORM operation: create -- bound to the authenticated user so ACL /
        # record rules apply exactly as they would for JSON-RPC.
        record = model.create(values)
        return self._serialize_record(record)

    # ------------------------------------------------------------------
    # Single-record read -- GET /api/v1/partners/<id>  (ORM: read)
    # ------------------------------------------------------------------
    @route(
        '/api/v1/partners/<int:record_id>',
        type='rest',
        auth='rest_bearer',
        methods=['GET'],
        readonly=True,
    )
    def get_partner(self, record_id, **kwargs):
        """Read a single partner by id.

        :param int record_id: the ``res.partner`` database id (an ``<int:...>``
            path converter, deliberately not named ``id`` to avoid shadowing the
            builtin).
        :raises werkzeug.exceptions.NotFound: if no record with ``record_id``
            exists or it is not visible to the current user (HTTP ``404``).
        :return: the record serialized as :class:`PartnerRead`.
        """
        record = request.env['res.partner'].browse(record_id)
        # Explicit existence check: read() on a non-existent id returns [] rather
        # than raising, so translate absence into a clean 404.
        if not record.exists():
            raise werkzeug.exceptions.NotFound(
                f"res.partner {record_id} not found",
            )
        return self._serialize_record(record)

    # ------------------------------------------------------------------
    # Partial update -- PATCH /api/v1/partners/<id>  (ORM: write)
    # ------------------------------------------------------------------
    @route(
        '/api/v1/partners/<int:record_id>',
        type='rest',
        auth='rest_bearer',
        methods=['PATCH'],
    )
    def update_partner(self, record_id, **kwargs):
        """Partially update a partner.

        The raw body is validated against :class:`PartnerUpdate` (every field
        optional, still strict and ``extra``-forbidding) **before** the record
        is fetched or written, so an invalid payload yields ``422`` before any
        ORM access (Gate 2). Only the supplied fields are written
        (``exclude_unset=True``), giving partial-update semantics.

        :param int record_id: the ``res.partner`` database id.
        :raises werkzeug.exceptions.NotFound: if the record does not exist or is
            not visible to the current user (HTTP ``404``).
        :return: the updated record serialized as :class:`PartnerRead`.
        """
        # Validate FIRST (before touching request.env) so a schema-invalid body
        # 422s with zero ORM access.
        dto = PartnerUpdate.model_validate_json(
            request.httprequest.get_data(as_text=True),
        )
        record = request.env['res.partner'].browse(record_id)
        if not record.exists():
            raise werkzeug.exceptions.NotFound(
                f"res.partner {record_id} not found",
            )
        # Translate x2many list-of-id payloads into explicit Odoo commands so a
        # PATCH *replaces* the full relation (and ``category_id=[]`` clears it)
        # rather than merely linking records (see :meth:`_to_orm_write_values`).
        values = self._to_orm_write_values(
            record, dto.model_dump(exclude_unset=True),
        )
        # ORM operation: write -- ACL / record rules / field groups enforced.
        record.write(values)
        return self._serialize_record(record)

    # ------------------------------------------------------------------
    # Delete -- DELETE /api/v1/partners/<id>  (ORM: unlink)
    # ------------------------------------------------------------------
    @route(
        '/api/v1/partners/<int:record_id>',
        type='rest',
        auth='rest_bearer',
        methods=['DELETE'],
    )
    def delete_partner(self, record_id, **kwargs):
        """Delete a partner.

        :param int record_id: the ``res.partner`` database id.
        :raises werkzeug.exceptions.NotFound: if the record does not exist or is
            not visible to the current user (HTTP ``404``).
        :return: an explicit ``204 No Content`` :class:`~odoo.http.Response`
            (passed through unchanged by the dispatcher), matching the OpenAPI
            ``DELETE -> 204`` contract.
        """
        record = request.env['res.partner'].browse(record_id)
        if not record.exists():
            raise werkzeug.exceptions.NotFound(
                f"res.partner {record_id} not found",
            )
        # ORM operation: unlink -- ACL / record rules enforced.
        record.unlink()
        return request.make_response('', status=204)

    # ==================================================================
    # Private helpers
    #
    # Kept as methods on the controller so the module stays self-contained
    # (the addon scope forbids adding a shared/base controller module to this
    # folder). Each sibling per-model controller defines the analogous helpers
    # against its own Read DTO.
    # ==================================================================

    @staticmethod
    def _read_fields():
        """Return the ORM field list to read, derived from :class:`PartnerRead`.

        The field set is taken from ``PartnerRead.model_fields`` minus ``id``
        (which is sourced from ``record.id`` rather than read). Deriving the
        read fields from the response DTO is what makes REST field-set parity
        (Gate 3) and OpenAPI zero-drift (Gate 4) automatic: the controller reads
        exactly the fields the DTO documents, so a REST read returns the same
        visible field set as a JSON-RPC read of these fields for the same user.

        :return: ordered list of ``res.partner`` field names to read.
        :rtype: list[str]
        """
        return [name for name in PartnerRead.model_fields if name != 'id']

    @staticmethod
    def _to_orm_write_values(model, values):
        """Translate validated REST write values into ORM-ready values.

        The request DTOs expose ``one2many`` / ``many2many`` relations as a
        plain list of ids (``list[int]``) -- the natural REST contract, where a
        client always transmits the *complete* desired set of related ids.
        Odoo's ``create`` / ``write``, however, expect x2many values to be
        expressed as *commands*. A bare id list is interpreted by the ORM as a
        sequence of ``Command.link`` operations, which only *adds* the given
        records to the relation: it can neither replace the existing set nor
        clear it. A REST ``PATCH`` sending ``category_id=[1, 2]`` would then
        link ``1`` and ``2`` on top of whatever tags already exist, and
        ``category_id=[]`` would be a silent no-op rather than clearing the
        relation.

        To honour full-list replacement semantics each ``one2many`` /
        ``many2many`` value that is a list is wrapped in a single
        :meth:`odoo.fields.Command.set` -- equivalent to the ``(6, 0, ids)``
        command -- which replaces the relation with exactly ``ids`` and clears
        it when ``ids`` is empty. Scalar fields (including ``many2one``, sent as
        a bare id), fields carrying a value that is not a list, and any field
        absent from ``values`` are passed through unchanged.

        The conversion is written generically against ``model._fields`` (rather
        than hard-coding ``category_id``) so the four sibling controllers
        inherit identical, correct x2many semantics when they mirror this
        canonical controller.

        :param model: the target recordset, used only for field metadata via
            ``model._fields``.
        :param dict values: the DTO dump, already limited to client-supplied
            keys by ``exclude_unset=True``.
        :return: a new dict safe to pass to ``create`` / ``write``.
        :rtype: dict
        """
        converted = {}
        for fname, value in values.items():
            field = model._fields.get(fname)
            if (
                field is not None
                and field.type in ('one2many', 'many2many')
                and isinstance(value, list)
            ):
                # Full-list replacement -- (6, 0, ids); clears when ids == [].
                converted[fname] = [Command.set(value)]
            else:
                # Scalars (incl. many2one ids), explicit ``None`` and any
                # non-list value are forwarded verbatim.
                converted[fname] = value
        return converted

    @staticmethod
    def _serialize_row(model, row):
        """Coerce one ``read`` / ``search_read`` result row into a JSON dict.

        Odoo's ``read`` / ``search_read`` return relational and empty values in
        forms that must be normalized before validation against the (lenient)
        :class:`PartnerRead` DTO:

        * ``many2one`` -> an ``(id, display_name)`` tuple, or ``False`` when
          unset. Reduced here to the related id (or ``None``).
        * ``one2many`` / ``many2many`` -> a list of ids. Normalized to ``[]``
          when empty.
        * empty scalar (``Char`` / ``Selection`` / ``Date`` / ...) -> ``False``.
          Normalized to ``None`` -- but **only** for non-boolean fields, so a
          legitimate boolean ``False`` (e.g. ``is_company`` / ``active``) is
          preserved rather than corrupted into ``None``.

        The normalized mapping is round-tripped through
        ``PartnerRead.model_validate(...).model_dump(mode='json')``: the DTO is
        lenient (``from_attributes=True``, not strict) so it tolerates the
        coerced values and drops any stray keys, and ``mode='json'`` yields a
        fully JSON-serializable dict (dates rendered as ISO strings).

        :param model: a ``res.partner`` recordset (used only for field metadata
            via ``model._fields``).
        :param dict row: a single ``read`` / ``search_read`` result row.
        :return: a JSON-native dict matching the :class:`PartnerRead` shape.
        :rtype: dict
        """
        out = {'id': row['id']}
        for fname in PartnerController._read_fields():
            field = model._fields[fname]
            value = row.get(fname)
            if field.type == 'many2one':
                # (id, name) tuple | False  ->  id | None
                out[fname] = value[0] if value else None
            elif field.type in ('one2many', 'many2many'):
                # list of ids | False  ->  list of ids | []
                out[fname] = value or []
            elif value is False and field.type != 'boolean':
                # empty Char / Selection / Date / relation  ->  None
                out[fname] = None
            else:
                # genuine bool / int / float / str / date kept verbatim
                out[fname] = value
        return PartnerRead.model_validate(out).model_dump(mode='json')

    @classmethod
    def _serialize_record(cls, record):
        """Serialize a single ``res.partner`` browse record.

        Performs an ORM ``read`` of the DTO field set (so the same access rules
        and field-group filtering apply as for the collection endpoint) and
        normalizes the resulting row via :meth:`_serialize_row`.

        :param record: a singleton ``res.partner`` recordset.
        :return: a JSON-native dict matching the :class:`PartnerRead` shape.
        :rtype: dict
        """
        # ORM operation: read (keeps the verb -> ORM-op mapping crisp).
        row = record.read(cls._read_fields())[0]
        return cls._serialize_row(record, row)

    @staticmethod
    def _read_query():
        """Parse pagination / filter parameters from the query string.

        The REST dispatcher merges only the JSON body and path parameters into
        ``request.params``; query-string parameters are read directly from
        ``request.httprequest.args`` here.

        * ``limit`` -- positive integer, defaults to :data:`DEFAULT_PAGE_SIZE`
          and is clamped to ``[1, MAX_PAGE_SIZE]``.
        * ``offset`` -- non-negative integer, defaults to ``0``.
        * ``domain`` -- a JSON-encoded Odoo search domain (list), defaults to
          ``[]``.

        Query values are always strings, so they are coerced defensively. A
        non-integer ``limit`` / ``offset`` or a ``domain`` that is not a
        JSON-encoded list raises ``werkzeug.exceptions.BadRequest`` (HTTP
        ``400``).

        :return: ``(limit, offset, domain)``.
        :rtype: tuple[int, int, list]
        """
        args = request.httprequest.args

        raw_limit = args.get('limit')
        if raw_limit is None:
            limit = DEFAULT_PAGE_SIZE
        else:
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError) as exc:
                raise werkzeug.exceptions.BadRequest(
                    f"'limit' must be an integer, got {raw_limit!r}",
                ) from exc
        # Clamp to a sane window: at least 1 record, at most MAX_PAGE_SIZE.
        limit = max(1, min(limit, MAX_PAGE_SIZE))

        raw_offset = args.get('offset')
        if raw_offset is None:
            offset = 0
        else:
            try:
                offset = int(raw_offset)
            except (TypeError, ValueError) as exc:
                raise werkzeug.exceptions.BadRequest(
                    f"'offset' must be an integer, got {raw_offset!r}",
                ) from exc
        offset = max(0, offset)

        raw_domain = args.get('domain')
        if not raw_domain:
            domain = []
        else:
            try:
                domain = json.loads(raw_domain)
            except ValueError as exc:
                raise werkzeug.exceptions.BadRequest(
                    f"'domain' must be a JSON-encoded list: {exc}",
                ) from exc
            if not isinstance(domain, list):
                msg = "'domain' must be a JSON-encoded list of search criteria"
                raise werkzeug.exceptions.BadRequest(msg)
        return limit, offset, domain
