"""REST API discovery & OpenAPI-specification controller (unauthenticated).

This module hosts the single, deliberately **tiny** HTTP controller that
surfaces the ``rest_api`` addon's *machine-readable metadata*. It exposes the
only two endpoints of the additive REST surface that are reachable **without
authentication**:

* ``GET /api/v1/`` -- a version/discovery document that names the API, states
  the contract version (``v1``) and links to the OpenAPI specification. It
  follows the shape of the legacy ``/web/version`` / ``/json/version`` endpoint
  (``addons/rpc/controllers/__init__.py``).
* ``GET /api/v1/openapi.json`` -- the machine-generated **OpenAPI 3.1.0**
  document, assembled *at request time* by the sibling
  :func:`odoo.addons.rest_api.openapi.build_openapi`.

Both endpoints exist so that tooling (Swagger UI, Postman, code generators) and
humans can discover the API and its schema before presenting any credential.
This is the ONLY controller in the addon whose routes are unauthenticated; every
per-model controller (``/api/v1/partners`` and friends) declares
``auth='rest_bearer'`` and answers ``401`` without a valid token.

Why ``type='http'`` and NOT ``type='rest'`` (the single most important detail)
------------------------------------------------------------------------------
Dispatcher selection in ``odoo/http.py`` is keyed on the route's *declared*
``type`` (``dispatcher_cls = _dispatchers[routing['type']]``). The staged
``RestDispatcher.is_compatible_with`` acts as a *guard* that returns ``True``
only when the incoming request's mimetype is ``application/json`` **and** the
path starts with ``/api/``; otherwise the framework raises
``415 Unsupported Media Type``. A plain browser ``GET`` (or a ``curl`` without
``-H 'Content-Type: application/json'``) to ``/api/v1/openapi.json`` carries no
JSON content type, so declaring these routes ``type='rest'`` would make the
discovery/spec endpoints unreachable by a bare ``GET``.

Declaring them ``type='http'`` routes them through ``HttpDispatcher``, whose
``is_compatible_with`` returns ``True`` unconditionally, so a credential-free,
content-type-free ``GET`` reaches them and returns ``200`` (AAP section 0.6.2,
validation Gate 7). The five per-model controllers, in contrast, are always
called with a JSON body and therefore correctly use ``type='rest'``.

Zero-drift specification (Gate 4)
---------------------------------
``/api/v1/openapi.json`` serves the return value of :func:`build_openapi` --
generated on every request from the very same pydantic DTO classes the per-model
controllers validate against -- rather than a checked-in static file. The served
document can therefore never fall out of sync with the live validators
(``doc['openapi'] == '3.1.0'``; component schemas equal the models'
``model_json_schema(...)`` output).

Isolation & purity constraints (AAP sections 0.2.2, 0.7)
--------------------------------------------------------
This controller is intentionally thin and side-effect-free:

* it contains **no** business logic, performs **no** ORM writes and imports
  **no** pydantic (schema handling lives entirely in ``openapi.py`` /
  ``schemas``);
* it exposes **no** model data and adds **no** endpoint beyond the two above;
* every response body is JSON produced via ``request.make_json_response(...)`` --
  never HTML and never the JSON-RPC ``{code, message, data}`` envelope;
* the discovery payload is static (plus a couple of ``odoo.release`` constants),
  so it can never ``500`` under ``auth='none'`` by touching a database-specific
  model.

Import graph
------------
``from odoo.addons.rest_api.openapi import build_openapi`` is the only intra-addon
import. It is acyclic: ``openapi`` imports only :mod:`odoo.http` and the
``schemas`` package (never back into ``controllers``), so the load chain
``controllers/__init__ -> meta -> openapi -> schemas`` terminates cleanly.
"""

import odoo.release
from odoo.http import Controller, request, route

# Absolute import of the sibling OpenAPI assembler. ``build_openapi`` is the
# module's sole public entry point and returns a plain, JSON-serialisable dict
# (a complete OpenAPI 3.1.0 document). No import cycle exists: ``openapi`` never
# imports from ``controllers`` (it depends only on ``odoo.http`` and the
# ``schemas`` package), so importing it here at controller-load time is safe.
from odoo.addons.rest_api.openapi import build_openapi


class RestApiMeta(Controller):
    """Unauthenticated discovery + OpenAPI-specification endpoints for ``/api/v1``.

    Mirrors the style of the legacy RPC ``version()`` controller
    (``addons/rpc/controllers/__init__.py``): both routes are ``type='http'``,
    ``auth='none'`` and ``readonly=True`` and return their payload through
    ``request.make_json_response(...)``.

    These are the only two ``/api/v1`` routes that respond without credentials;
    they let API consumers discover the surface and fetch its schema before
    authenticating. All substantive REST behaviour (CRUD, validation,
    authorization) lives in the per-model ``type='rest'`` controllers and in the
    shared serving pipeline, never here.
    """

    @route('/api/v1/', type='http', auth='none', methods=['GET'], readonly=True)
    def api_v1_root(self, **kwargs):
        """Serve the REST API discovery / version document.

        Reachable without authentication (Gate 7) via a bare ``GET`` -- the
        ``type='http'`` declaration routes the request through
        ``HttpDispatcher`` so no ``application/json`` content type is required.

        The payload is intentionally **static** (augmented only with two
        ``odoo.release`` constants) so it never touches a database-specific model
        and thus cannot ``500`` under ``auth='none'``. It advertises:

        * ``name`` -- human-facing API name;
        * ``version`` -- the REST *contract* discriminator (``'v1'``), distinct
          from the Odoo server release;
        * ``openapi`` / ``documentation`` -- the location of the machine-readable
          OpenAPI 3.1 document;
        * ``server_version`` / ``server_version_info`` -- the running Odoo
          release, mirroring the legacy ``/web/version`` endpoint for parity with
          existing tooling.

        The ``**kwargs`` sink absorbs any stray query-string parameters so the
        framework never emits a ``filter_kwargs`` warning for an unexpected arg.

        :return: a JSON ``200`` response describing the API surface.
        :rtype: odoo.http.Response
        """
        return request.make_json_response({
            'name': 'Odoo REST API',
            'version': 'v1',
            'openapi': '/api/v1/openapi.json',
            'documentation': '/api/v1/openapi.json',
            'server_version': odoo.release.version,
            'server_version_info': odoo.release.version_info,
        })

    @route('/api/v1/openapi.json', type='http', auth='none', methods=['GET'], readonly=True)
    def api_v1_openapi(self, **kwargs):
        """Serve the machine-generated OpenAPI 3.1.0 specification.

        Reachable without authentication (Gate 7) via a bare ``GET``; the
        ``type='http'`` declaration avoids the ``RestDispatcher`` JSON-content-type
        guard that would otherwise answer a plain ``GET`` with ``415``.

        The body is produced by calling :func:`build_openapi` with no arguments
        (it defaults its ``env`` to ``request.env``). Because the document is
        assembled at request time from the same pydantic DTOs the controllers
        validate against -- and its ``paths`` are enumerated from the live
        routing map -- it can never drift from the code that actually validates
        requests and serves routes (Gate 4). The returned mapping is a plain,
        JSON-serialisable ``dict`` (with ``doc['openapi'] == '3.1.0'``) and is
        handed straight to ``request.make_json_response(...)``.

        The ``**kwargs`` sink absorbs any stray query-string parameters.

        :return: a JSON ``200`` response carrying the OpenAPI 3.1.0 document.
        :rtype: odoo.http.Response
        """
        return request.make_json_response(build_openapi())
