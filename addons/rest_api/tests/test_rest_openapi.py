# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""OpenAPI 3.1 accuracy / zero-drift integration tests (validation **Gate 4**).

This module proves that the machine-generated document served at
``GET /api/v1/openapi.json`` by :mod:`odoo.addons.rest_api` is a valid
**OpenAPI 3.1.0** contract that **cannot drift** from the pydantic validators
the per-model controllers actually enforce. Concretely it asserts, over HTTP
(:class:`odoo.tests.common.HttpCase`), that:

* the document declares ``openapi == '3.1.0'`` and carries the mandatory
  ``info`` / ``paths`` / ``components`` sections (``components`` exposing both
  ``schemas`` and ``securitySchemes``);
* **every** ``components.schemas[X]`` is byte-identical to the corresponding
  pydantic DTO's :meth:`pydantic.BaseModel.model_json_schema` output -- rendered
  with the *same* ``ref_template`` and per-DTO *mode* the assembler uses -- which
  is the zero-drift property Gate 4 exists to guarantee;
* the ten strict request DTOs advertise ``additionalProperties: false`` (the
  JSON-Schema rendering of ``extra='forbid'``);
* every ``/api/v1`` pilot resource is present with its correct verbs
  (collection ``get`` + ``post``; item ``get`` + ``patch`` + ``delete``);
* ``securitySchemes`` describes at least an API-key HTTP-bearer scheme and an
  OAuth bearer scheme.

Contract source of truth
-------------------------
The assertions below mirror the **staged** assembler
:func:`odoo.addons.rest_api.openapi.build_openapi` and the shared DTOs in
:mod:`odoo.addons.rest_api.schemas`. Two assembler details, confirmed by reading
``openapi.py`` and verified against pydantic 2.9.2, shape the checks:

1. **Modes.** ``openapi._iter_schema_models`` renders request DTOs
   (``*Create`` / ``*Update``) with ``mode='validation'`` and response/auxiliary
   DTOs (``*Read`` / ``*List`` / ``RestErrorResponse`` / ``PageMeta``) with
   ``mode='serialization'``. :data:`SCHEMA_MAP` reproduces that mapping exactly so
   the equality holds by construction (AAP Gate 4).
2. **``$defs`` placement.** ``openapi._build_component_schemas`` stores each
   model's ``model_json_schema`` output **verbatim** -- so the five ``*List``
   wrappers (which reference ``*Read`` + ``PageMeta``) keep a nested ``$defs``
   block, while the other seventeen DTOs have none. The referenced sub-schemas
   are *also* emitted as top-level components in their own right, so the nested
   ``$defs`` bag is redundant. The zero-drift comparison therefore normalises
   **both** the served schema and the freshly-computed expected schema by
   dropping ``$defs`` (see :meth:`TestRestOpenApi._strip_defs`): this proves the
   schema *body* (properties, ``required``, ``type``, ``additionalProperties``,
   enums, ...) is identical to the live validator's output, independently of
   whether a given assembler revision hoists ``$defs`` up to the shared
   ``components.schemas`` map or keeps it inline. Removing the redundant bag from
   both sides masks no real drift: every referenced sub-schema is asserted in its
   own right as a top-level component.

Server-base / path-prefix tolerance
------------------------------------
The assembler sets ``servers=[{'url': '/api/v1'}]`` and keys ``paths``
**relative** to that base (``/partners``, ``/partners/{record_id}``, ``/``,
``/openapi.json``), so an operation's effective URL is ``servers[0].url`` joined
with its path key. :meth:`TestRestOpenApi._paths_index` reconstructs the
absolute path of every key using ``servers[0].url`` as the base, so the path
assertions pass regardless of whether a given assembler revision keys ``paths``
server-relative (the current design) or absolutely.

Boundaries (AAP sections 0.2, 0.7 / Gates 1 & 4)
------------------------------------------------
* This is a purpose-written ("-- (new)") test module in Odoo ``HttpCase`` style;
  it does **not** import or modify any legacy RPC integration test -- Gate 1
  keeps the existing XML-RPC / JSON-RPC suites passing unmodified.
* It uses **no** external OpenAPI validator library (none is a declared
  dependency); every check is a self-contained structural assertion.
* Importing :mod:`odoo.addons.rest_api.schemas` -- the addon's own public
  package -- is required and allowed; the DTO classes are the drift reference.
* No model-availability skipping: ``components.schemas`` and ``paths`` are
  derived from imports and route registration, not from whether the ``sale`` /
  ``account`` / ``stock`` / ``crm`` ORM models are installed, so all five pilots
  are asserted unconditionally under a bare ``-i rest_api`` install.
"""

import re

from odoo.tests import common

# The addon's OWN public schema package (allowed, and the drift reference). Every
# name below is re-exported from ``odoo/addons/rest_api/schemas/__init__.py``
# (its ``__all__``); these are plain pydantic v2 models, not ORM models.
from odoo.addons.rest_api.schemas import (
    AccountMoveCreate,
    AccountMoveList,
    AccountMoveRead,
    AccountMoveUpdate,
    CrmLeadCreate,
    CrmLeadList,
    CrmLeadRead,
    CrmLeadUpdate,
    PageMeta,
    PartnerCreate,
    PartnerList,
    PartnerRead,
    PartnerUpdate,
    RestErrorResponse,
    SaleOrderCreate,
    SaleOrderList,
    SaleOrderRead,
    SaleOrderUpdate,
    StockPickingCreate,
    StockPickingList,
    StockPickingRead,
    StockPickingUpdate,
)

# ``$ref`` template used by the assembler; the zero-drift equality only holds
# when the test regenerates each schema with this exact template (it retargets
# pydantic's default ``#/$defs/{model}`` pointers at the OpenAPI components
# location). MUST stay identical to ``openapi.REF_TEMPLATE``.
REF_TEMPLATE = '#/components/schemas/{model}'

# JSON-Schema generation modes (see the module docstring). Request DTOs render
# the shape a client must *send*; response/aux DTOs render the shape the server
# *returns* -- honouring the request/response split of AAP requirement 3.5.
VALIDATION = 'validation'
SERIALIZATION = 'serialization'

# The ten strict request DTOs (``*Create`` / ``*Update``). Rendered with
# ``mode='validation'`` and expected to advertise ``additionalProperties: false``
# because they derive from ``BaseRestModel`` (``extra='forbid'``).
REQUEST_DTOS = (
    PartnerCreate,
    PartnerUpdate,
    SaleOrderCreate,
    SaleOrderUpdate,
    AccountMoveCreate,
    AccountMoveUpdate,
    StockPickingCreate,
    StockPickingUpdate,
    CrmLeadCreate,
    CrmLeadUpdate,
)

# The twelve response / auxiliary DTOs (``*Read`` / ``*List`` + the two shared
# response models). Rendered with ``mode='serialization'``.
RESPONSE_DTOS = (
    PartnerRead,
    PartnerList,
    SaleOrderRead,
    SaleOrderList,
    AccountMoveRead,
    AccountMoveList,
    StockPickingRead,
    StockPickingList,
    CrmLeadRead,
    CrmLeadList,
    RestErrorResponse,
    PageMeta,
)

# Component-name -> (pydantic model, JSON-Schema mode). Keyed on ``__name__`` so
# the component key can never diverge from the class name by a typo. This is the
# authoritative drift reference for :meth:`TestRestOpenApi.test_component_schemas_zero_drift`;
# it enumerates exactly the 22 schemas the assembler emits.
SCHEMA_MAP = {model.__name__: (model, VALIDATION) for model in REQUEST_DTOS}
SCHEMA_MAP.update({model.__name__: (model, SERIALIZATION) for model in RESPONSE_DTOS})

# The five pilot resources, keyed by their ``/api/v1`` collection path segment.
# Item routes are the collection path plus a trailing ``/{record_id}``.
RESOURCES = (
    'partners',
    'sale-orders',
    'account-moves',
    'stock-pickings',
    'crm-leads',
)

# Verb sets each resource path must expose (lower-cased, as OpenAPI path-item
# keys are). ``>=`` (superset) comparisons are used so an assembler that also
# documents an extra verb never breaks the gate.
COLLECTION_VERBS = {'get', 'post'}
ITEM_VERBS = {'get', 'patch', 'delete'}


@common.tagged('post_install', '-at_install')
class TestRestOpenApi(common.HttpCase):
    """Prove Gate 4: the served OpenAPI 3.1.0 document cannot drift from the DTOs.

    The specification endpoint is unauthenticated (``type='http'``,
    ``auth='none'`` in ``controllers/meta.py``), so the document is fetched once
    in :meth:`setUp` with a bare :meth:`~odoo.tests.common.HttpCase.url_open`
    (no credentials). Every test then makes structural / equality assertions
    against the parsed document; none touches the ORM, so all five pilot models
    are asserted unconditionally regardless of which business modules are
    installed alongside ``rest_api``.
    """

    def setUp(self):
        """Fetch and parse ``/api/v1/openapi.json`` once (no authentication).

        A plain ``GET`` with no ``Authorization`` header must return ``200``
        (Gate 7): the route is served through ``HttpDispatcher`` under
        ``auth='none'``. The parsed JSON body is stored on ``self.doc`` for the
        individual assertions.
        """
        super().setUp()
        response = self.url_open('/api/v1/openapi.json')
        self.assertEqual(
            response.status_code,
            200,
            "GET /api/v1/openapi.json must be reachable without credentials "
            "and return HTTP 200 (Gate 7); got %s." % response.status_code,
        )
        self.doc = response.json()
        self.assertIsInstance(
            self.doc,
            dict,
            "The OpenAPI document must deserialise to a JSON object (dict).",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_defs(schema):
        """Return a shallow copy of a JSON-Schema object without its ``$defs``.

        The assembler stores each model's ``model_json_schema`` output verbatim,
        so the five ``*List`` wrappers keep an inline ``$defs`` bag whose members
        are *also* emitted as standalone top-level components. Dropping ``$defs``
        from both the served and the expected schema before comparing focuses the
        equality on the schema *body* (properties, ``required``, ``type``,
        ``additionalProperties``, enums, ...) and makes the zero-drift check
        robust to whether a given assembler revision keeps ``$defs`` inline or
        hoists it into the shared ``components.schemas`` map -- without masking
        any real drift, since every referenced sub-schema is asserted in its own
        right as a top-level component.

        :param dict schema: a JSON-Schema object (an entry of
            ``components.schemas`` or a ``model_json_schema`` result).
        :return: a shallow copy with the top-level ``$defs`` key removed.
        :rtype: dict
        """
        normalised = dict(schema)
        normalised.pop('$defs', None)
        return normalised

    def _paths_index(self):
        """Index ``paths`` by absolute path, tolerating the server-base prefix.

        The assembler keys ``paths`` *relative* to the server base and declares
        ``servers=[{'url': '/api/v1'}]``. To stay robust should a revision key
        ``paths`` absolutely instead, every key is normalised to its absolute
        form: keys already under ``/api`` are kept as-is, otherwise the
        (trailing-slash-stripped) ``servers[0].url`` base is prepended.

        :return: mapping of absolute path string -> OpenAPI path-item object.
        :rtype: dict
        """
        paths = self.doc['paths']
        servers = self.doc.get('servers') or [{}]
        base = (servers[0].get('url') or '').rstrip('/')
        index = {}
        for key, path_item in paths.items():
            absolute = key if key.startswith('/api') else base + key
            index[absolute] = path_item
        return index

    # ------------------------------------------------------------------
    # Gate 4 -- document is a structurally valid OpenAPI 3.1.0 document
    # ------------------------------------------------------------------
    def test_openapi_version_and_structure(self):
        """The document declares 3.1.0 and carries the mandatory sections.

        Structural assertions only -- no external OpenAPI validator is used (none
        is a declared dependency). Verifies the ``openapi`` version string, the
        presence of ``info`` / ``paths`` / ``components``, that ``paths`` is a
        non-empty object, and that ``components`` exposes both ``schemas`` and
        ``securitySchemes``.
        """
        doc = self.doc

        self.assertEqual(
            doc.get('openapi'),
            '3.1.0',
            "The document must declare OpenAPI version '3.1.0' (Gate 4); "
            "got %r." % (doc.get('openapi'),),
        )

        self.assertIn('info', doc, "OpenAPI document must contain an 'info' block.")
        self.assertIsInstance(doc['info'], dict, "'info' must be an object.")

        self.assertIn('paths', doc, "OpenAPI document must contain a 'paths' object.")
        self.assertIsInstance(doc['paths'], dict, "'paths' must be an object.")
        self.assertTrue(doc['paths'], "'paths' must not be empty.")

        self.assertIn(
            'components', doc, "OpenAPI document must contain a 'components' object."
        )
        self.assertIsInstance(doc['components'], dict, "'components' must be an object.")
        self.assertIn(
            'schemas',
            doc['components'],
            "'components' must expose a 'schemas' object.",
        )
        self.assertIn(
            'securitySchemes',
            doc['components'],
            "'components' must expose a 'securitySchemes' object.",
        )

    # ------------------------------------------------------------------
    # Gate 4 -- zero-drift: every component schema equals model_json_schema(...)
    # ------------------------------------------------------------------
    def test_component_schemas_zero_drift(self):
        """Each ``components.schemas[X]`` equals the DTO's ``model_json_schema``.

        This is the core zero-drift assertion: for every one of the 22 DTOs the
        served component schema, normalised by :meth:`_strip_defs`, must equal the
        freshly-computed ``model_json_schema(ref_template=REF_TEMPLATE, mode=...)``
        (same normalisation). Because the document is assembled at request time
        from these very classes, any change to a DTO immediately changes the
        served schema -- the specification can never fall out of sync with the
        live validators.
        """
        served = self.doc['components']['schemas']
        self.assertIsInstance(served, dict, "'components.schemas' must be an object.")

        for class_name, (model, mode) in SCHEMA_MAP.items():
            with self.subTest(schema=class_name):
                self.assertIn(
                    class_name,
                    served,
                    "Expected component schema %r to be present." % class_name,
                )
                expected = model.model_json_schema(
                    ref_template=REF_TEMPLATE, mode=mode
                )
                self.assertEqual(
                    self._strip_defs(served[class_name]),
                    self._strip_defs(expected),
                    "Component schema %r drifted from %s.model_json_schema("
                    "mode=%r): the served OpenAPI schema no longer matches the "
                    "live pydantic validator." % (class_name, model.__name__, mode),
                )

        # Every enumerated DTO is present (superset check above); guard the count
        # too so a wholesale omission is caught with a clear message. A superset
        # (never fewer) is required; extra helper schemas would not be a defect.
        self.assertGreaterEqual(
            len(served),
            len(SCHEMA_MAP),
            "Expected at least %d component schemas; found %d."
            % (len(SCHEMA_MAP), len(served)),
        )

    def test_request_models_forbid_extra(self):
        """The ten strict request DTOs render ``additionalProperties: false``.

        ``*Create`` / ``*Update`` derive from ``BaseRestModel``
        (``ConfigDict(strict=True, extra='forbid')``); pydantic renders
        ``extra='forbid'`` as ``additionalProperties: false`` in the generated
        JSON Schema. Asserting it on the *served* component documents the strict
        anti-corruption boundary directly in the published contract.
        """
        served = self.doc['components']['schemas']
        for model in REQUEST_DTOS:
            name = model.__name__
            with self.subTest(schema=name):
                self.assertIn(
                    name,
                    served,
                    "Expected request-DTO component %r to be present." % name,
                )
                self.assertEqual(
                    served[name].get('additionalProperties'),
                    False,
                    "Request DTO %r must publish 'additionalProperties: false' "
                    "(documents extra='forbid')." % name,
                )

    # ------------------------------------------------------------------
    # Gate 4 -- every /api/v1 pilot resource is present with the right verbs
    # ------------------------------------------------------------------
    def test_all_model_paths_present(self):
        """All five pilot collection + item paths exist with the correct verbs.

        For each resource the collection path ``/api/v1/<resource>`` must expose
        ``get`` + ``post``, and the item path ``/api/v1/<resource>/{record_id}``
        must expose ``get`` + ``patch`` + ``delete``. The item path is located by
        a regex that tolerates any path-parameter name (the staged routes use
        ``{record_id}``), and exactly one such key must exist per resource.
        """
        index = self._paths_index()

        for resource in RESOURCES:
            with self.subTest(resource=resource):
                collection = '/api/v1/%s' % resource
                self.assertIn(
                    collection,
                    index,
                    "Missing collection path %r." % collection,
                )
                collection_ops = set(index[collection])
                self.assertGreaterEqual(
                    collection_ops,
                    COLLECTION_VERBS,
                    "Collection path %r must expose %s; found %s."
                    % (collection, sorted(COLLECTION_VERBS), sorted(collection_ops)),
                )

                item_pattern = re.compile(
                    r'^/api/v1/%s/\{[^}]+\}$' % re.escape(resource)
                )
                item_keys = [key for key in index if item_pattern.match(key)]
                self.assertEqual(
                    len(item_keys),
                    1,
                    "Expected exactly one item path matching "
                    "'/api/v1/%s/{<param>}'; found %r." % (resource, item_keys),
                )
                item_ops = set(index[item_keys[0]])
                self.assertGreaterEqual(
                    item_ops,
                    ITEM_VERBS,
                    "Item path %r must expose %s; found %s."
                    % (item_keys[0], sorted(ITEM_VERBS), sorted(item_ops)),
                )

    # ------------------------------------------------------------------
    # Gate 4 -- securitySchemes advertise API-key bearer + OAuth bearer
    # ------------------------------------------------------------------
    def test_security_schemes(self):
        """``securitySchemes`` includes an HTTP-bearer and an OAuth scheme.

        At least two schemes must be declared: one HTTP ``bearer`` scheme (the
        Odoo API-key credential) and one OAuth scheme (the ``auth_oauth`` access
        token). The OAuth scheme is matched by *characteristics* -- an
        ``oauth2`` type or the string ``'oauth'`` appearing in its name/body --
        rather than by a hardcoded scheme name, so a rename does not break the
        gate. If a document-level ``security`` requirement is present, it must
        reference at least one defined scheme.
        """
        schemes = self.doc['components']['securitySchemes']
        self.assertIsInstance(schemes, dict, "'securitySchemes' must be an object.")
        self.assertGreaterEqual(
            len(schemes),
            2,
            "Expected at least two security schemes (API-key bearer + OAuth "
            "bearer); found %d." % len(schemes),
        )

        has_http_bearer = any(
            isinstance(scheme, dict)
            and scheme.get('type') == 'http'
            and scheme.get('scheme') == 'bearer'
            for scheme in schemes.values()
        )
        self.assertTrue(
            has_http_bearer,
            "securitySchemes must include an HTTP 'bearer' scheme (the Odoo "
            "API-key credential).",
        )

        has_oauth = any(
            (isinstance(scheme, dict) and scheme.get('type') == 'oauth2')
            or 'oauth' in (name + str(scheme)).lower()
            for name, scheme in schemes.items()
        )
        self.assertTrue(
            has_oauth,
            "securitySchemes must include an OAuth bearer scheme (the auth_oauth "
            "access-token credential).",
        )

        # Optional document-level security requirement: if present it must
        # reference at least one of the defined schemes (a dangling requirement
        # would be a defect).
        security = self.doc.get('security')
        if security:
            referenced = set()
            for requirement in security:
                if isinstance(requirement, dict):
                    referenced.update(requirement)
            self.assertTrue(
                referenced & set(schemes),
                "Document-level 'security' must reference a defined scheme; "
                "referenced %r, defined %r." % (sorted(referenced), sorted(schemes)),
            )
