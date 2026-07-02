"""Machine-generated OpenAPI 3.1 document assembler for the ``rest_api`` addon.

This module is the *single source of truth* for the REST surface's
machine-readable contract. Its sole public entry point, :func:`build_openapi`,
returns a plain, JSON-serialisable :class:`dict` that is a valid **OpenAPI
3.1.0** document describing every ``/api/v1`` endpoint exposed by the addon's
per-model controllers.

Zero-drift by construction
--------------------------
The document is assembled **at request time** (it is served by the
unauthenticated ``GET /api/v1/openapi.json`` route in
:mod:`odoo.addons.rest_api.controllers.meta`) from the very same pydantic DTO
classes the controllers validate against. There is intentionally **no
hand-written JSON Schema** and **no checked-in static specification**:

* Every ``components.schemas[X]`` entry is produced by calling
  :meth:`pydantic.BaseModel.model_json_schema` on the corresponding DTO with
  ``ref_template='#/components/schemas/{model}'`` -- so the schema embedded in
  the document is byte-identical to what the live validator would emit. This is
  the property AAP validation Gate 4 verifies: the served component schema can
  never fall out of sync with the class that actually validates the request or
  shapes the response.
* Pydantic v2 emits JSON Schema **Draft 2020-12**, which *is* the dialect used
  by OpenAPI 3.1.0, so ``model_json_schema`` output drops directly into
  ``components.schemas`` with no converter library and no FastAPI/Starlette
  dependency (AAP section 0.3.4).
* The request/response split of requirement 3.5 is honoured through the schema
  *mode*: request DTOs (``Create`` / ``Update``) are rendered with
  ``mode='validation'`` and response DTOs (``Read`` / ``List`` /
  ``RestErrorResponse`` / ``PageMeta``) with ``mode='serialization'``.

Path discovery
--------------
The ``paths`` object is enumerated from the **live routing map**
(``env['ir.http'].routing_map()``) rather than from a static list, so a
renamed, added or removed ``@route(type='rest')`` controller route is reflected
automatically. Only rules whose endpoint declares ``type='rest'`` are
considered; the ``type='http'`` discovery/``openapi.json`` routes are documented
explicitly (and marked unauthenticated) because they are intentionally excluded
from the ``rest`` filter.

Purity and isolation constraints (AAP sections 0.2, 0.6, 0.7)
-------------------------------------------------------------
* :func:`build_openapi` is deterministic and side-effect-free: it performs *no*
  ORM data reads or writes. Enumerating the routing map and calling
  ``model_json_schema`` are the only operations, both safe under an
  ``auth='none'`` route with no bound user.
* The module imports **only** :mod:`odoo.http` (for the ``request`` proxy used
  to reach the routing map) and the sibling :mod:`~odoo.addons.rest_api.schemas`
  package. It never imports from ``odoo.service`` or ``odoo.orm``, and -- to
  avoid the import cycle ``__init__`` -> ``controllers`` -> ``meta`` ->
  ``openapi`` -- it never imports back into :mod:`~odoo.addons.rest_api.controllers`.
* The return value is a plain ``dict`` composed of ``dict`` / ``list`` / ``str``
  / ``int`` / ``bool`` values (every ``model_json_schema`` result is already
  JSON-able); :mod:`~odoo.addons.rest_api.controllers.meta` wraps it with
  ``request.make_json_response(...)``.
"""

import re
from typing import Any, NamedTuple

from odoo.http import request

# Sibling schema package. Imported as a module (not ``from ... import X``) so the
# DTO classes are referenced as ``schemas.PartnerCreate`` etc. -- the exact
# attribute-access contract advertised by ``schemas/__init__.py`` for this
# assembler. This is a pure-pydantic package with no ``import odoo``, so it is
# import-safe here and introduces no cycle.
from . import schemas

# ---------------------------------------------------------------------------
# Document-level constants
# ---------------------------------------------------------------------------

#: OpenAPI specification version. MUST be the exact string ``'3.1.0'`` -- it is
#: the dialect whose JSON-Schema (Draft 2020-12) matches pydantic v2 output, and
#: AAP Gate 4 asserts ``doc['openapi'] == '3.1.0'``.
OPENAPI_VERSION = '3.1.0'

#: Human-facing API title.
API_TITLE = 'Odoo REST API'

#: API contract version (the ``v1`` surface). This is intentionally independent
#: of the Odoo server release: it versions the REST *contract*, not the product.
API_VERSION = '1.0.0'

#: Versioned base path under which every REST endpoint lives.
API_BASE_PATH = '/api/v1'

#: ``$ref`` template that retargets pydantic's default ``#/$defs/{model}``
#: pointers at the OpenAPI components location. Keeping this string identical to
#: the one AAP Gate 4 uses is what makes ``components.schemas[X]`` byte-equal to
#: ``X.model_json_schema(ref_template=REF_TEMPLATE, mode=...)``.
REF_TEMPLATE = '#/components/schemas/{model}'

#: Route ``type`` that identifies a REST endpoint (see ``RestDispatcher`` in
#: ``odoo/http.py``). Only rules whose endpoint declares this type are turned
#: into ``paths`` entries.
REST_ROUTING_TYPE = 'rest'

# -- Security scheme identifiers (keys under ``components.securitySchemes``) ---

#: Odoo API key presented as ``Authorization: Bearer <api_key>``.
SECURITY_API_KEY = 'ApiKeyBearer'

#: OAuth 2.0 access token presented as ``Authorization: Bearer <token>``.
SECURITY_OAUTH = 'OAuthBearer'

#: Default security requirement applied to every authenticated model operation.
#: A list of alternative requirement objects means "any one of these satisfies
#: authentication", mirroring ``_auth_method_rest_bearer`` which accepts *either*
#: an Odoo API key *or* an OAuth access token in the ``Authorization`` header.
MODEL_SECURITY = [{SECURITY_API_KEY: []}, {SECURITY_OAUTH: []}]

# -- Collection pagination defaults (mirrors the controllers' query handling) --

#: Default ``limit`` when the collection ``GET`` client omits the parameter.
DEFAULT_PAGE_SIZE = 80

#: Hard ceiling the controllers clamp ``limit`` to. Documented so tooling knows
#: the accepted range.
MAX_PAGE_SIZE = 200

#: JSON media type used by every request/response body on this surface.
JSON_MEDIA_TYPE = 'application/json'


class _ResourceSpec(NamedTuple):
    """Static mapping of a REST resource base path to its four pydantic DTOs.

    This table is the explicit, drift-free bridge between a URL resource (e.g.
    ``/api/v1/partners``) and the request/response models that shape it. It is
    cross-checked against the *enumerated* ``type='rest'`` routes at build time:
    a route whose base is absent here still appears in ``paths`` (via a generic
    operation), and a spec whose route is missing simply never gets emitted --
    so a renamed or dropped route is caught rather than silently mis-documented
    (AAP section 0.4.1, Gate 4).

    Attributes:
        tag: Display name used as the OpenAPI ``tag`` grouping the operations
            (e.g. ``"Partners"``).
        singular: Lower-case singular noun for human-readable summaries
            (e.g. ``"partner"``).
        plural: Lower-case plural noun for human-readable summaries
            (e.g. ``"partners"``).
        create: Request DTO for ``POST`` (validated, ``mode='validation'``).
        update: Request DTO for ``PATCH`` (validated, ``mode='validation'``).
        read: Response DTO for single-record reads (``mode='serialization'``).
        list_: Response DTO wrapping the paginated collection
            (``mode='serialization'``).
    """

    tag: str
    singular: str
    plural: str
    create: type
    update: type
    read: type
    list_: type


#: The five pilot resources, keyed by their collection base path. Item paths are
#: this base plus a trailing ``/{record_id}``. Only these five ``type='rest'``
#: resources exist; no path is invented for any other model.
_RESOURCES = {
    '/api/v1/partners': _ResourceSpec(
        'Partners', 'partner', 'partners',
        schemas.PartnerCreate, schemas.PartnerUpdate,
        schemas.PartnerRead, schemas.PartnerList,
    ),
    '/api/v1/sale-orders': _ResourceSpec(
        'Sale Orders', 'sale order', 'sale orders',
        schemas.SaleOrderCreate, schemas.SaleOrderUpdate,
        schemas.SaleOrderRead, schemas.SaleOrderList,
    ),
    '/api/v1/account-moves': _ResourceSpec(
        'Account Moves', 'journal entry', 'journal entries',
        schemas.AccountMoveCreate, schemas.AccountMoveUpdate,
        schemas.AccountMoveRead, schemas.AccountMoveList,
    ),
    '/api/v1/stock-pickings': _ResourceSpec(
        'Stock Pickings', 'transfer', 'transfers',
        schemas.StockPickingCreate, schemas.StockPickingUpdate,
        schemas.StockPickingRead, schemas.StockPickingList,
    ),
    '/api/v1/crm-leads': _ResourceSpec(
        'CRM Leads', 'lead', 'leads',
        schemas.CrmLeadCreate, schemas.CrmLeadUpdate,
        schemas.CrmLeadRead, schemas.CrmLeadList,
    ),
}


# ---------------------------------------------------------------------------
# components.schemas -- zero-drift assembly from the pydantic DTOs
# ---------------------------------------------------------------------------

def _iter_schema_models():
    """Yield every ``(model, mode)`` pair that becomes a component schema.

    The ordering follows the resource table (``Create``, ``Update``, ``Read``,
    ``List`` for each pilot) and appends the two shared response models. The
    *mode* implements the request/response split of AAP requirement 3.5:

    * request DTOs -> ``'validation'`` (the shape a client must send);
    * response DTOs -> ``'serialization'`` (the shape the server returns).

    Yields:
        tuple[type, str]: a pydantic model class and its JSON-Schema mode.
    """
    for spec in _RESOURCES.values():
        yield spec.create, 'validation'
        yield spec.update, 'validation'
        yield spec.read, 'serialization'
        yield spec.list_, 'serialization'
    # Shared response models referenced by ``$ref`` from the operations.
    yield schemas.RestErrorResponse, 'serialization'
    yield schemas.PageMeta, 'serialization'


def _build_component_schemas() -> dict:
    """Assemble ``components.schemas`` from the live pydantic validators.

    For every enumerated ``(model, mode)`` the entry is produced **verbatim** by
    ``model.model_json_schema(ref_template=REF_TEMPLATE, mode=mode)``. Storing
    the per-model output unchanged is what guarantees the AAP Gate 4 equality::

        doc['components']['schemas'][M.__name__]
            == M.model_json_schema(ref_template=REF_TEMPLATE, mode=<its mode>)

    holds for *every* DTO -- including the ``<Model>List`` wrappers, whose
    per-model output carries a nested ``$defs`` block. That nested block is
    harmless: because ``ref_template`` already rewrote the wrapper's ``$ref``
    pointers to ``#/components/schemas/<Model>Read`` and
    ``#/components/schemas/PageMeta`` (both emitted as top-level components in
    their own right), the pointers resolve against the top-level components and
    the embedded ``$defs`` is never dereferenced. A redundant ``$defs`` inside a
    schema object is valid JSON Schema 2020-12 (hence valid OpenAPI 3.1), so the
    document stays spec-compliant.

    As a defensive measure the nested ``$defs`` of every model are also hoisted
    to the top level (via :meth:`dict.setdefault`, so an explicitly enumerated
    model always wins): should a DTO ever gain a nested sub-model that is *not*
    in :func:`_iter_schema_models`, its ``$ref`` target would still exist as a
    component. For the current five pilots every referenced model is already
    enumerated, so this hoist changes nothing.

    Returns:
        dict: mapping of component name -> JSON Schema object, ready to place at
        ``components.schemas``.
    """
    components: dict[str, Any] = {}
    for model, mode in _iter_schema_models():
        schema = model.model_json_schema(ref_template=REF_TEMPLATE, mode=mode)
        # Defensive hoist of nested definitions so every ``$ref`` resolves.
        for nested_name, nested_schema in schema.get('$defs', {}).items():
            components.setdefault(nested_name, nested_schema)
        # Store the model's own schema verbatim (authoritative -- overrides any
        # value a prior hoist may have set for the same name).
        components[model.__name__] = schema
    return components


# ---------------------------------------------------------------------------
# components.securitySchemes -- the two accepted bearer mechanisms
# ---------------------------------------------------------------------------

def _build_security_schemes() -> dict:
    """Return the two bearer authentication schemes advertised by the surface.

    Both mirror ``_auth_method_rest_bearer``, which authenticates an
    ``Authorization: Bearer <credential>`` header holding *either* an Odoo API
    key *or* an OAuth 2.0 access token. They are modelled as HTTP ``bearer``
    schemes so tooling prompts for a single bearer token; the two entries
    document the two credential kinds a caller may supply.

    Returns:
        dict: mapping suitable for ``components.securitySchemes``.
    """
    return {
        SECURITY_API_KEY: {
            'type': 'http',
            'scheme': 'bearer',
            'description': (
                "Odoo API key presented as 'Authorization: Bearer <api_key>'. "
                "The key is verified through res.users.apikeys._check_credentials "
                "(honouring its scope and expiration)."
            ),
        },
        SECURITY_OAUTH: {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'OAuth2 access token',
            'description': (
                "OAuth 2.0 access token presented as "
                "'Authorization: Bearer <token>', validated through the "
                "auth_oauth provider (res.users._auth_oauth_validate)."
            ),
        },
    }


# ---------------------------------------------------------------------------
# paths -- enumerated from the live ``type='rest'`` routing rules
# ---------------------------------------------------------------------------

#: HTTP verbs a REST controller may declare. Everything else werkzeug/Odoo add
#: automatically (``HEAD`` for ``GET``, ``OPTIONS`` for CORS pre-flight) is not
#: a documented operation and is filtered out.
_REST_VERBS = ('GET', 'POST', 'PATCH', 'PUT', 'DELETE')

#: Matches a werkzeug path converter ``<converter:name>`` or a bare ``<name>``.
#: Group ``conv`` captures the optional converter, group ``name`` the variable.
_PATH_VAR_RE = re.compile(
    r'<(?:(?P<conv>[a-zA-Z_][a-zA-Z0-9_]*):)?(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)>',
)

#: Matches a single trailing ``/{param}`` segment, used to derive a collection
#: base path from an item path.
_TRAILING_PARAM_RE = re.compile(r'/\{[^/{}]+\}$')

#: werkzeug converter name -> OpenAPI ``schema.type``. Unknown/absent converters
#: fall back to ``string``.
_CONVERTER_TYPES = {
    'int': 'integer',
    'float': 'number',
    'string': 'string',
    'path': 'string',
    'any': 'string',
    'uuid': 'string',
}


def _convert_path(rule_string: str):
    """Convert a werkzeug URL rule to an OpenAPI path template.

    ``/api/v1/partners/<int:record_id>`` becomes
    ``('/api/v1/partners/{record_id}', [('record_id', 'integer')])``. The
    variable *name* is preserved exactly (not normalised to ``id``) so the
    emitted ``parameters[].name`` matches the ``{name}`` placeholder in the path,
    as OpenAPI requires.

    Args:
        rule_string: the werkzeug rule string (``rule.rule``).

    Returns:
        tuple[str, list[tuple[str, str]]]: the OpenAPI path template and the
        ordered list of ``(param_name, openapi_type)`` for each path variable.
    """
    params: list[tuple[str, str]] = []

    def _replace(match: "re.Match") -> str:
        converter = match.group('conv')
        name = match.group('name')
        params.append((name, _CONVERTER_TYPES.get(converter, 'string')))
        return '{' + name + '}'

    openapi_path = _PATH_VAR_RE.sub(_replace, rule_string)
    return openapi_path, params


def _split_base(openapi_path: str):
    """Split an OpenAPI path into its collection base and item-ness.

    ``/api/v1/partners/{record_id}`` -> ``('/api/v1/partners', True)`` while
    ``/api/v1/partners`` -> ``('/api/v1/partners', False)``.

    Args:
        openapi_path: a converted OpenAPI path template.

    Returns:
        tuple[str, bool]: the collection base path and whether the input was an
        item path (i.e. ended in a ``/{param}`` segment).
    """
    base = _TRAILING_PARAM_RE.sub('', openapi_path)
    return base, base != openapi_path


def _rest_methods(routing: dict) -> list:
    """Return the documented REST verbs declared by a routing rule.

    The declared methods live in ``endpoint.routing['methods']`` (the original,
    unmutated list -- ``routing_map`` appends ``OPTIONS`` only to a *copy* used
    for the werkzeug ``Rule``). A route that declares no ``methods`` accepts any
    verb; such a rule is not a documented REST operation and yields nothing.

    Args:
        routing: the endpoint's routing dict (``rule.endpoint.routing``).

    Returns:
        list[str]: the upper-case REST verbs to document, in a stable order.
    """
    declared = routing.get('methods')
    if not declared:
        return []
    declared_upper = {str(method).upper() for method in declared}
    return [verb for verb in _REST_VERBS if verb in declared_upper]


def _json_schema_content(ref_name: str) -> dict:
    """Build a ``content`` object referencing a named component schema.

    Args:
        ref_name: the component name (a key of ``components.schemas``).

    Returns:
        dict: an OpenAPI ``content`` map for :data:`JSON_MEDIA_TYPE`.
    """
    return {
        JSON_MEDIA_TYPE: {
            'schema': {'$ref': REF_TEMPLATE.format(model=ref_name)},
        },
    }


def _error_response(description: str) -> dict:
    """Build a Response Object whose body is the shared ``RestErrorResponse``.

    Args:
        description: the human-readable response description.

    Returns:
        dict: an OpenAPI Response Object referencing
        ``#/components/schemas/RestErrorResponse``.
    """
    return {
        'description': description,
        'content': _json_schema_content(schemas.RestErrorResponse.__name__),
    }


def _path_parameter_objects(path_params) -> list:
    """Build OpenAPI path Parameter Objects for an item route.

    Args:
        path_params: the ``[(name, openapi_type)]`` list from
            :func:`_convert_path`.

    Returns:
        list[dict]: one required path Parameter Object per variable.
    """
    parameters = []
    for name, openapi_type in path_params:
        parameters.append({
            'name': name,
            'in': 'path',
            'required': True,
            'schema': {'type': openapi_type},
            'description': f"Database identifier of the target record ({name}).",
        })
    return parameters


def _pagination_query_parameters() -> list:
    """Build the optional query Parameter Objects for a collection ``GET``.

    Mirrors the controllers' query handling: ``limit`` (clamped to
    ``[1, MAX_PAGE_SIZE]``, default :data:`DEFAULT_PAGE_SIZE`), ``offset``
    (``>= 0``, default ``0``) and ``domain`` (a JSON-encoded Odoo search
    domain).

    Returns:
        list[dict]: the three optional query Parameter Objects.
    """
    return [
        {
            'name': 'limit',
            'in': 'query',
            'required': False,
            'schema': {
                'type': 'integer',
                'default': DEFAULT_PAGE_SIZE,
                'minimum': 1,
                'maximum': MAX_PAGE_SIZE,
            },
            'description': (
                "Maximum number of records to return; clamped to "
                f"[1, {MAX_PAGE_SIZE}]."
            ),
        },
        {
            'name': 'offset',
            'in': 'query',
            'required': False,
            'schema': {'type': 'integer', 'default': 0, 'minimum': 0},
            'description': "Number of records to skip before collecting the page.",
        },
        {
            'name': 'domain',
            'in': 'query',
            'required': False,
            'schema': {'type': 'string'},
            'description': (
                "A JSON-encoded Odoo search domain (a list of criteria); "
                "defaults to an empty domain."
            ),
        },
    ]


def _model_security() -> list:
    """Return a fresh deep copy of :data:`MODEL_SECURITY`.

    A new list/dict/list tree is produced on every call (from the canonical
    :data:`MODEL_SECURITY` constant) so no two operations share a mutable object
    in the assembled document.

    Returns:
        list[dict]: ``[{ApiKeyBearer: []}, {OAuthBearer: []}]``.
    """
    return [
        {scheme: list(scopes) for scheme, scopes in requirement.items()}
        for requirement in MODEL_SECURITY
    ]


def _generic_operation(method: str, is_item: bool, path_params, op_prefix: str) -> dict:
    """Build a minimal, valid Operation Object for a REST route with no spec.

    This keeps :func:`build_openapi` total: any enumerated ``type='rest'`` route
    whose base is absent from :data:`_RESOURCES` still appears in ``paths`` (AAP
    Gate 4 -- "every enumerated route present") without inventing a
    model-specific schema. It is unreachable for the five pilot resources and
    exists purely as forward-compatible defence should a REST route be added
    before its resource spec is registered here.

    Args:
        method: the upper-case HTTP verb.
        is_item: whether the route is an item (``.../{id}``) route.
        path_params: the ``[(name, type)]`` list for item routes.
        op_prefix: the operationId prefix derived from the route base.

    Returns:
        dict: a spec-compliant Operation Object.
    """
    suffix = '_item' if is_item else ''
    responses = {
        '200': {'description': "Successful response."},
        '401': _error_response(
            "Authentication is required and no valid bearer credential was supplied.",
        ),
    }
    if is_item:
        responses['404'] = _error_response("The requested resource does not exist.")
    if method in ('POST', 'PATCH', 'PUT'):
        responses['422'] = _error_response(
            "The request body failed strict schema validation.",
        )
    operation = {
        'summary': f"{method} {op_prefix}",
        'operationId': f"{op_prefix}_{method.lower()}{suffix}",
        'security': _model_security(),
        'responses': responses,
    }
    if is_item:
        operation['parameters'] = _path_parameter_objects(path_params)
    return operation


def _build_operation(method: str, spec: _ResourceSpec | None, is_item: bool,
                     path_params, base: str) -> dict:
    """Build the OpenAPI Operation Object for one ``(path, verb)`` pair.

    The verb-to-operation mapping follows the platform Authorization Control
    Matrix (AAP section 0.3.2):

    * ``GET`` collection  -> paginated ``<Model>List`` response;
    * ``POST`` collection -> ``<Model>Create`` body, ``<Model>Read`` response
      (the controller returns HTTP ``200`` via ``make_json_response``);
    * ``GET`` item        -> ``<Model>Read`` response, ``404`` on absence;
    * ``PATCH`` item      -> ``<Model>Update`` body, ``<Model>Read`` response;
    * ``DELETE`` item     -> ``204`` no-content, ``404`` on absence.

    Every model operation carries the bearer ``security`` requirement and each
    error response references ``#/components/schemas/RestErrorResponse``. An
    unexpected verb, or a route with no matching resource spec, falls back to
    :func:`_generic_operation`.

    Args:
        method: the HTTP verb (case-insensitive).
        spec: the resource spec for the route base, or ``None`` if unknown.
        is_item: whether this is an item (``.../{id}``) route.
        path_params: the ``[(name, type)]`` list from :func:`_convert_path`.
        base: the collection base path (used for the operationId prefix).

    Returns:
        dict: a spec-compliant Operation Object.
    """
    method = method.upper()
    op_prefix = base.rsplit('/', 1)[-1].replace('-', '_')

    if spec is None:
        return _generic_operation(method, is_item, path_params, op_prefix)

    read_content = _json_schema_content(spec.read.__name__)
    unauthorized = _error_response(
        "Authentication is required and no valid bearer credential was supplied.",
    )
    not_found = _error_response(
        f"No {spec.singular} matching the given id is visible to the "
        "authenticated user.",
    )
    invalid_body = _error_response(
        "The request body failed strict schema validation "
        "(unknown or wrongly-typed field); no ORM operation was performed.",
    )
    parameters = _path_parameter_objects(path_params) if is_item else []

    operation = {'tags': [spec.tag], 'security': _model_security()}

    if method == 'GET' and not is_item:
        operation.update({
            'summary': f"List {spec.plural}",
            'operationId': f"{op_prefix}_list",
            'description': (
                f"Return a paginated collection of {spec.plural} visible to the "
                "authenticated user (ORM search_read; record rules and "
                "field-group filtering apply)."
            ),
            'parameters': _pagination_query_parameters(),
            'responses': {
                '200': {
                    'description': f"A paginated page of {spec.plural}.",
                    'content': _json_schema_content(spec.list_.__name__),
                },
                '401': unauthorized,
            },
        })
        return operation

    if method == 'POST' and not is_item:
        operation.update({
            'summary': f"Create a {spec.singular}",
            'operationId': f"{op_prefix}_create",
            'description': (
                f"Create a {spec.singular}. The request body is validated "
                f"against {spec.create.__name__} (strict, extra fields "
                "forbidden) before any ORM access."
            ),
            'requestBody': {
                'required': True,
                'content': _json_schema_content(spec.create.__name__),
            },
            'responses': {
                '200': {
                    'description': f"The created {spec.singular}.",
                    'content': read_content,
                },
                '401': unauthorized,
                '422': invalid_body,
            },
        })
        return operation

    if method == 'GET' and is_item:
        operation.update({
            'summary': f"Retrieve a {spec.singular}",
            'operationId': f"{op_prefix}_retrieve",
            'description': f"Return a single {spec.singular} by database id.",
            'parameters': parameters,
            'responses': {
                '200': {
                    'description': f"The requested {spec.singular}.",
                    'content': read_content,
                },
                '401': unauthorized,
                '404': not_found,
            },
        })
        return operation

    if method == 'PATCH' and is_item:
        operation.update({
            'summary': f"Update a {spec.singular}",
            'operationId': f"{op_prefix}_update",
            'description': (
                f"Partially update a {spec.singular}. The request body is "
                f"validated against {spec.update.__name__} (strict, extra "
                "fields forbidden) before any ORM access; only supplied fields "
                "are written."
            ),
            'parameters': parameters,
            'requestBody': {
                'required': True,
                'content': _json_schema_content(spec.update.__name__),
            },
            'responses': {
                '200': {
                    'description': f"The updated {spec.singular}.",
                    'content': read_content,
                },
                '401': unauthorized,
                '404': not_found,
                '422': invalid_body,
            },
        })
        return operation

    if method == 'DELETE' and is_item:
        operation.update({
            'summary': f"Delete a {spec.singular}",
            'operationId': f"{op_prefix}_delete",
            'description': f"Delete a {spec.singular} by database id.",
            'parameters': parameters,
            'responses': {
                '204': {
                    'description': (
                        f"The {spec.singular} was deleted; the response has no "
                        "body."
                    ),
                },
                '401': unauthorized,
                '404': not_found,
            },
        })
        return operation

    # Any other verb for a known resource: emit a valid generic operation.
    return _generic_operation(method, is_item, path_params, op_prefix)


def _add_meta_paths(paths: dict) -> None:
    """Document the two unauthenticated ``type='http'`` meta endpoints.

    The discovery (``GET /api/v1/``) and specification (``GET
    /api/v1/openapi.json``) routes are served by ``controllers/meta.py`` with
    ``type='http', auth='none'``, so they are deliberately excluded from the
    ``type='rest'`` enumeration. They are added here explicitly and marked
    ``security: []`` (no authentication) so the document fully describes the
    surface. :meth:`dict.setdefault` avoids clobbering an entry should one ever
    be produced by enumeration.

    Args:
        paths: the ``paths`` object being assembled (mutated in place).
    """
    no_body_response = {
        '200': {
            'description': "Metadata document.",
            'content': {JSON_MEDIA_TYPE: {'schema': {'type': 'object'}}},
        },
    }
    paths.setdefault(f'{API_BASE_PATH}/', {
        'get': {
            'tags': ['Meta'],
            'summary': "REST API version discovery",
            'operationId': 'meta_version',
            'description': (
                "Return REST API version metadata, following the existing "
                "/web/version and /json/version convention. Requires no "
                "authentication."
            ),
            'security': [],
            'responses': {
                '200': {
                    'description': "API version metadata.",
                    'content': {JSON_MEDIA_TYPE: {'schema': {'type': 'object'}}},
                },
            },
        },
    })
    paths.setdefault(f'{API_BASE_PATH}/openapi.json', {
        'get': {
            'tags': ['Meta'],
            'summary': "OpenAPI 3.1 specification document",
            'operationId': 'meta_openapi',
            'description': (
                "Return this machine-readable OpenAPI 3.1.0 document, generated "
                "at request time from the live pydantic validators. Requires no "
                "authentication."
            ),
            'security': [],
            'responses': dict(no_body_response),
        },
    })


def _build_paths(routing_map) -> dict:
    """Enumerate ``type='rest'`` routes into an OpenAPI ``paths`` object.

    Iterates the live routing map, keeping only rules whose endpoint declares
    ``type='rest'``; converts each werkzeug URL rule to an OpenAPI path
    template; groups verbs under a single path key; and builds an Operation
    Object per declared REST verb. Finally the unauthenticated meta endpoints
    are documented.

    Args:
        routing_map: a ``werkzeug.routing.Map`` (from
            ``env['ir.http'].routing_map()``).

    Returns:
        dict: the assembled ``paths`` object.
    """
    paths: dict[str, Any] = {}
    for rule in routing_map.iter_rules():
        endpoint = getattr(rule, 'endpoint', None)
        routing = getattr(endpoint, 'routing', None)
        if not isinstance(routing, dict) or routing.get('type') != REST_ROUTING_TYPE:
            continue
        openapi_path, path_params = _convert_path(rule.rule)
        base, is_item = _split_base(openapi_path)
        spec = _RESOURCES.get(base)
        path_item = paths.setdefault(openapi_path, {})
        for method in _rest_methods(routing):
            path_item[method.lower()] = _build_operation(
                method, spec, is_item, path_params, base,
            )
    _add_meta_paths(paths)
    return paths


def _document_tags() -> list:
    """Return the document-level ``tags`` array grouping the operations.

    Returns:
        list[dict]: one tag object per pilot resource plus the ``Meta`` group.
    """
    tags = [
        {'name': spec.tag, 'description': f"CRUD operations for {spec.plural}."}
        for spec in _RESOURCES.values()
    ]
    tags.append({
        'name': 'Meta',
        'description': "Unauthenticated discovery and specification endpoints.",
    })
    return tags


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_openapi(env=None) -> dict:
    """Assemble and return the complete OpenAPI 3.1.0 document as a ``dict``.

    Called at request time by the unauthenticated ``GET /api/v1/openapi.json``
    route in :mod:`~odoo.addons.rest_api.controllers.meta`, which serialises the
    returned mapping with ``request.make_json_response(...)``.

    The document is rebuilt on every call from the live pydantic validators and
    the live routing map, so it can never drift from the code that actually
    validates requests and serves routes (AAP Gate 4). The function is
    deterministic and side-effect-free: it performs no ORM data access.

    Args:
        env: an optional Odoo :class:`~odoo.api.Environment`. When omitted it
            defaults to ``request.env`` (the function is normally called within
            a request). The parameter exists so the assembler can be exercised
            from a test with an explicit environment; passing nothing preserves
            the ``build_openapi()`` call contract used by ``meta.py``.

    Returns:
        dict: a JSON-serialisable OpenAPI 3.1.0 document with ``openapi``,
        ``info``, ``servers``, ``tags``, ``paths``, ``components`` (``schemas``
        and ``securitySchemes``) and a document-level ``security`` requirement.
    """
    env = env if env is not None else request.env
    routing_map = env['ir.http'].routing_map()

    return {
        'openapi': OPENAPI_VERSION,
        'info': {
            'title': API_TITLE,
            'version': API_VERSION,
            'description': (
                "Additive, versioned REST surface for Odoo, layered over the "
                "ORM alongside the existing JSON-RPC and XML-RPC interfaces. "
                f"All endpoints live under {API_BASE_PATH}. Authentication uses "
                "an 'Authorization: Bearer' header carrying either an Odoo API "
                "key or an OAuth 2.0 access token; session cookies are not "
                "accepted. This document is generated at request time from the "
                "same pydantic models used to validate requests and shape "
                "responses."
            ),
        },
        'servers': [{
            'url': '/',
            'description': (
                "Odoo host root. Every REST endpoint is served under the "
                f"{API_BASE_PATH} prefix, which is already included in each "
                "path key below."
            ),
        }],
        'tags': _document_tags(),
        'paths': _build_paths(routing_map),
        'components': {
            'schemas': _build_component_schemas(),
            'securitySchemes': _build_security_schemes(),
        },
        'security': _model_security(),
    }
