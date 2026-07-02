# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""REST authentication contract tests for the ``rest_api`` addon (Gates 6 & 7).

This module is the HTTP-level proof of the *authentication contract* of the
additive REST surface introduced by :mod:`odoo.addons.rest_api`. It exercises
the surface **only** over real HTTP (via :class:`odoo.tests.common.HttpCase`) --
never by reaching into dispatcher internals or re-implementing any auth logic --
and asserts, end to end, that:

* **Gate 7 (unauthenticated discovery).** The two metadata endpoints
  ``GET /api/v1/`` (discovery) and ``GET /api/v1/openapi.json`` (the OpenAPI
  3.1 document) are reachable **without any credentials** and answer ``200``.
  They are declared ``type='http'`` / ``auth='none'`` in
  :mod:`odoo.addons.rest_api.controllers.meta`, so a bare ``GET`` (carrying no
  ``Authorization`` header and no ``Content-Type``) reaches them.

* **Gate 6 (bearer-only authentication).** Every per-model endpoint is declared
  ``@route(type='rest', auth='rest_bearer')`` and is authenticated by
  ``_auth_method_rest_bearer`` (added by the addon's ``ir.http`` inheritance in
  :mod:`odoo.addons.rest_api.models.ir_http`). This suite proves each half of
  that contract:

  - a valid **API key** bearer token is *accepted* (``200``);
  - a valid **OAuth 2.0** bearer token is *accepted* (``200``);
  - an **invalid** bearer token is *rejected* (``401``);
  - a **session cookie** -- even a fully authenticated one -- is *rejected*
    (``401``): the REST surface never falls back to interactive session auth;
  - an **unauthenticated** request to any of the five model collections is
    *rejected* (``401``).

Transport rule (why every model request sets ``Content-Type: application/json``)
-------------------------------------------------------------------------------
``RestDispatcher.is_compatible_with`` (``odoo/http.py``) is a guard that accepts
a ``type='rest'`` request only when its mimetype is ``application/json`` **and**
its path is under ``/api/``; otherwise the framework answers ``415 Unsupported
Media Type`` *before* authentication runs. Consequently **every** request to a
``type='rest'`` model route below -- including the ``GET`` and the negative /
unauthenticated cases -- explicitly sends ``Content-Type: application/json`` so
that the request actually reaches the ``rest_bearer`` auth layer and yields the
intended ``200`` / ``401`` rather than a spurious ``415``. The two
``type='http'`` metadata endpoints need no such header.

REST error envelope
-------------------
When the auth layer rejects a request, ``RestDispatcher.handle_error`` renders
the failure as the REST envelope ``{"status", "code", "message", "details"}`` --
deliberately distinct from the JSON-RPC ``{code, message, data}`` envelope. The
:meth:`_assert_rest_unauthorized` helper asserts the ``401`` status and, when the
body is JSON, that it is the REST envelope (and never the JSON-RPC one).

Style reference (NOT imported, NOT modified): the legacy XML-RPC ``HttpCase``
suite shipped by the ``rpc`` addon -- its ``@tagged('post_install',
'-at_install')`` decoration, ``mute_logger`` usage and API-key idiom. The legacy
RPC integration tests must keep passing unmodified (Gate 1); nothing from them
is imported here.
"""

from unittest.mock import patch

from odoo.tests import common
from odoo.tools import mute_logger


@common.tagged('post_install', '-at_install')
class TestRestAuth(common.HttpCase):
    """Prove the REST authentication contract (Gate 6) and public discovery (Gate 7).

    All assertions are made over HTTP as a dedicated internal user. The user is
    granted only ``base.group_user`` (internal access), which is sufficient to
    *read* ``res.partner`` -- so the "accepted" ``GET`` on ``/api/v1/partners``
    returns ``200`` -- while keeping the fixture minimal.
    """

    #: The five per-model *collection* endpoints. Every one is declared
    #: ``@route(type='rest', auth='rest_bearer')`` and therefore answers ``401``
    #: without a valid bearer token, regardless of whether the underlying pilot
    #: business module (``sale`` / ``account`` / ``stock`` / ``crm``) is
    #: installed: authentication runs *before* dispatch and any ORM access, and
    #: all five controllers are imported (and their routes registered)
    #: unconditionally by the addon.
    MODEL_COLLECTION_PATHS = (
        '/api/v1/partners',
        '/api/v1/sale-orders',
        '/api/v1/account-moves',
        '/api/v1/stock-pickings',
        '/api/v1/crm-leads',
    )

    def setUp(self):
        """Create a dedicated internal user and a persistent ``rpc`` API key.

        The API key is the bearer token used by the "accepted" tests; it is
        generated with ``.sudo()`` (so a persistent, no-expiry key is allowed)
        while remaining *owned by* ``self.user`` -- so ``_check_credentials``
        resolves the key back to that user on the REST surface.
        """
        super().setUp()

        # A dedicated internal user. NB: the writable groups field on
        # ``res.users`` in this Odoo 19.0 tree is ``group_ids`` (the pre-19.0
        # ``groups_id`` no longer exists); ``(6, 0, ids)`` sets exact membership.
        self.user = self.env['res.users'].create({
            'name': 'REST Auth User',
            'login': 'rest_auth_user',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })

        # A persistent (no-expiration) ``rpc``-scope API key OWNED BY that user.
        # ``.sudo()`` grants the privilege to mint a persistent key; the owner
        # remains ``self.user`` (``_generate`` records ``self.env.user``), so the
        # key authenticates as ``self.user`` on the REST surface.
        self.api_key = self.env['res.users.apikeys'].with_user(
            self.user,
        ).sudo()._generate('rpc', 'REST auth test', False)

        # Headers for an *authenticated* REST model request: the JSON content
        # type (else ``415`` before auth) and the API-key bearer token.
        self.auth_headers = {
            'Authorization': 'Bearer %s' % self.api_key,
            'Content-Type': 'application/json',
        }

        # Headers for a *credential-free* REST model request: the JSON content
        # type only, so the request clears the ``415`` guard and reaches -- and
        # is rejected by -- the ``rest_bearer`` auth layer with a ``401``.
        self.json_headers = {'Content-Type': 'application/json'}

    # ------------------------------------------------------------------
    # Shared assertion helper
    # ------------------------------------------------------------------
    def _assert_rest_unauthorized(self, resp):
        """Assert ``resp`` is a REST ``401`` with the correct error envelope.

        The primary, always-required assertion is ``status_code == 401``. When
        the auth layer emits a JSON body (as ``RestDispatcher.handle_error``
        does -- ``{"status", "code", "message", "details"}``), this additionally
        asserts the REST envelope shape and that it is **not** the JSON-RPC
        ``{code, message, data}`` envelope (no ``data`` key). A non-JSON body (a
        bare Werkzeug ``WWW-Authenticate`` challenge) is tolerated: the ``401``
        status alone is sufficient in that case, per the auth-layer contract.

        :param resp: the :class:`requests.Response` returned by ``url_open``.
        """
        self.assertEqual(
            resp.status_code, 401,
            "expected HTTP 401 on the REST surface; got %s: %r" % (
                resp.status_code, resp.text,
            ),
        )
        try:
            body = resp.json()
        except ValueError:
            # Bare Werkzeug challenge without a JSON body -- 401 status suffices.
            return
        if isinstance(body, dict):
            # REST envelope markers -- distinct from JSON-RPC {code, message, data}.
            self.assertEqual(
                body.get('status'), 401,
                "REST 401 body should carry status=401; got %r" % (body,),
            )
            self.assertIn('code', body, "REST error envelope must expose 'code'")
            self.assertIn('message', body, "REST error envelope must expose 'message'")
            self.assertIn('details', body, "REST error envelope must expose 'details'")
            self.assertNotIn(
                'data', body,
                "a REST 401 must use the REST envelope, never the JSON-RPC "
                "{code, message, data} envelope",
            )

    # ==================================================================
    # Gate 7 -- metadata reachable WITHOUT credentials
    # ==================================================================
    def test_openapi_json_public(self):
        """``GET /api/v1/openapi.json`` returns ``200`` + the OpenAPI 3.1 doc, no creds.

        A bare ``GET`` (fresh ``self.opener`` -> no session cookie, no
        ``Authorization`` header, no ``Content-Type``) must reach the
        ``type='http'`` / ``auth='none'`` route and receive the machine-generated
        OpenAPI 3.1.0 document (Gate 7, and the discoverable surface for Gate 4).
        """
        resp = self.url_open('/api/v1/openapi.json')
        self.assertEqual(
            resp.status_code, 200,
            "openapi.json must be public (200 without credentials); got %s" % (
                resp.status_code,
            ),
        )
        body = resp.json()
        self.assertEqual(
            body.get('openapi'), '3.1.0',
            "served spec must declare OpenAPI 3.1.0; got %r" % (body.get('openapi'),),
        )
        self.assertIn('paths', body, "the OpenAPI document must contain 'paths'")
        self.assertIn('components', body, "the OpenAPI document must contain 'components'")

    def test_discovery_public(self):
        """``GET /api/v1/`` returns ``200`` + version-discovery JSON, no creds.

        Mirrors the legacy ``/web/version`` / ``/json/version`` discovery style:
        the ``type='http'`` / ``auth='none'`` root advertises the API name, the
        ``v1`` contract version and the OpenAPI location -- all without
        credentials (Gate 7).
        """
        resp = self.url_open('/api/v1/')
        self.assertEqual(
            resp.status_code, 200,
            "the discovery root must be public (200 without credentials); got %s" % (
                resp.status_code,
            ),
        )
        body = resp.json()
        self.assertEqual(
            body.get('version'), 'v1',
            "discovery must advertise contract version 'v1'; got %r" % (body.get('version'),),
        )
        self.assertEqual(
            body.get('openapi'), '/api/v1/openapi.json',
            "discovery must link to the OpenAPI document location",
        )
        self.assertIn('name', body, "the discovery document must carry a 'name'")

    # ==================================================================
    # Gate 6 -- API-key bearer ACCEPTED
    # ==================================================================
    def test_api_key_accepted(self):
        """A valid ``rpc`` API-key bearer authenticates and returns the collection.

        ``GET /api/v1/partners`` with the API-key bearer + JSON content type must
        return ``200`` and the collection envelope
        ``{"items": [...], "meta": {"limit", "offset", "total"}}`` -- proving the
        key resolved to ``self.user`` (an internal user who can read
        ``res.partner``) and the request rode the standard serving pipeline.
        """
        resp = self.url_open(
            '/api/v1/partners', method='GET', headers=self.auth_headers,
        )
        self.assertEqual(
            resp.status_code, 200,
            "a valid API-key bearer must authenticate (200); got %s: %r" % (
                resp.status_code, resp.text,
            ),
        )
        body = resp.json()
        self.assertIn('items', body, "the collection envelope must carry 'items'")
        self.assertIn('meta', body, "the collection envelope must carry 'meta'")
        self.assertIsInstance(body['items'], list, "'items' must be a list")
        self.assertGreaterEqual(
            set(body['meta']), {'limit', 'offset', 'total'},
            "'meta' must expose the pagination keys limit/offset/total; got %r" % (
                body.get('meta'),
            ),
        )

    # ==================================================================
    # Gate 6 -- OAuth 2.0 bearer ACCEPTED  +  invalid bearer REJECTED
    # ==================================================================
    def test_oauth_bearer_accepted(self):
        """A valid OAuth 2.0 bearer token authenticates the REST surface (``200``).

        ``_auth_method_rest_bearer`` validates an OAuth token by iterating
        enabled ``auth.oauth.provider`` records and calling
        ``res.users._auth_oauth_validate(provider_id, token)`` (normally a
        network round-trip), then matching an existing user by
        ``(oauth_uid, oauth_provider_id)``. This test drives that path
        deterministically by:

        * creating an enabled provider (all required fields populated),
        * linking ``self.user`` to it via ``oauth_provider_id`` / ``oauth_uid``,
        * patching ``ResUsers._auth_oauth_validate`` to return the linked
          subject (so no real HTTP call is made), and
        * sending ``Authorization: Bearer <token>`` + JSON content type.

        The patch takes effect across the in-process ``HttpCase`` server thread
        because it replaces the method on the shared class object. If the
        ``auth.oauth.provider`` model is somehow unavailable, the OAuth positive
        path is skipped for this subtest only -- the negative bearer proof
        (:meth:`test_invalid_bearer_rejected`) is non-skippable and always runs.
        """
        if 'auth.oauth.provider' not in self.env:
            self.skipTest(
                'OAuth positive path not deterministically exercisable: the '
                'auth.oauth.provider model is not available in this installation',
            )

        # An enabled provider with EVERY required field populated. ``name``,
        # ``auth_endpoint``, ``validation_endpoint`` and ``body`` are all
        # ``required=True`` on ``auth.oauth.provider``; the endpoints point at an
        # unreachable host on purpose -- the validation call is mocked, so no
        # network I/O ever occurs.
        provider = self.env['auth.oauth.provider'].create({
            'name': 'REST Test Provider',
            'client_id': 'rest-test-client',
            'auth_endpoint': 'https://example.invalid/auth',
            'validation_endpoint': 'https://example.invalid/validate',
            'scope': 'openid',
            'body': 'REST Test Provider',
            'enabled': True,
        })
        # Link the user to that provider under a unique external subject. The
        # OAuth branch of ``_auth_method_rest_bearer`` matches an EXISTING user
        # by ``(oauth_uid, oauth_provider_id)``; the mock returns this subject.
        subject = 'rest-oauth-subject'
        self.user.write({
            'oauth_provider_id': provider.id,
            'oauth_uid': subject,
        })
        # Flush so the in-process HTTP handler (which shares the test cursor)
        # observes the provider record and the user's OAuth links.
        self.env.flush_all()

        with patch(
            'odoo.addons.auth_oauth.models.res_users.ResUsers._auth_oauth_validate',
            return_value={'user_id': subject},
        ):
            resp = self.url_open(
                '/api/v1/partners',
                method='GET',
                headers={
                    'Authorization': 'Bearer rest-oauth-access-token',
                    'Content-Type': 'application/json',
                },
            )
        self.assertEqual(
            resp.status_code, 200,
            "a valid OAuth 2.0 bearer must authenticate (200); got %s: %r" % (
                resp.status_code, resp.text,
            ),
        )
        body = resp.json()
        self.assertIn(
            'items', body,
            "an authenticated OAuth request must return the collection envelope",
        )
        self.assertIn('meta', body, "the collection envelope must carry 'meta'")

    def test_invalid_bearer_rejected(self):
        """An invalid/garbage bearer token is rejected with ``401`` (non-skippable).

        Sending ``Authorization: Bearer <garbage>`` (a value that is neither a
        valid API key nor a linked OAuth token) + JSON content type must yield a
        clean ``401`` -- proving the bearer branch *rejects* unknown tokens
        rather than answering ``415`` (missing content type) or ``500``
        (unhandled error). This is the always-on negative proof for the bearer
        contract.
        """
        with mute_logger('odoo.http'):
            resp = self.url_open(
                '/api/v1/partners',
                method='GET',
                headers={
                    'Authorization': 'Bearer this-is-not-a-valid-key',
                    'Content-Type': 'application/json',
                },
            )
        self._assert_rest_unauthorized(resp)

    # ==================================================================
    # Gate 6 -- session cookie REJECTED (no interactive fallback)
    # ==================================================================
    def test_session_cookie_rejected(self):
        """A valid session cookie must NOT authenticate the REST surface (``401``).

        ``self.authenticate('admin', 'admin')`` establishes a genuine
        ``session_id`` cookie in ``self.opener``. A subsequent REST request that
        carries that cookie but **no** ``Authorization`` header must still be
        rejected with ``401``: ``_auth_method_rest_bearer`` deliberately omits
        the base method's interactive session fallback, so a browser session can
        never authenticate against ``/api/v1``.
        """
        # Establish a valid interactive session (sets the ``session_id`` cookie
        # and resets ``self.opener`` as a side effect).
        self.authenticate('admin', 'admin')
        with mute_logger('odoo.http'):
            resp = self.url_open(
                '/api/v1/partners',
                method='GET',
                headers=self.json_headers,  # JSON content type, NO Authorization
            )
        self._assert_rest_unauthorized(resp)

    # ==================================================================
    # Gate 6/7 -- unauthenticated model endpoints -> 401 for ALL five
    # ==================================================================
    def test_unauthenticated_endpoints_401(self):
        """Every model collection answers ``401`` without a bearer token.

        Iterates all five ``type='rest'`` collection paths. Each request carries
        the JSON content type (to clear the ``415`` guard) but **no**
        ``Authorization`` header, and must be rejected with ``401`` by the
        ``rest_bearer`` auth layer. No model-availability skipping is needed:
        authentication runs before dispatch/ORM and all five routes are
        registered unconditionally, so the ``401`` is produced by the auth layer
        irrespective of whether the pilot business module is installed. The
        fresh ``self.opener`` from ``setUp`` carries no session cookie, so this
        stays a genuinely credential-free probe.
        """
        for path in self.MODEL_COLLECTION_PATHS:
            with self.subTest(path=path), mute_logger('odoo.http'):
                resp = self.url_open(
                    path, method='GET', headers=self.json_headers,
                )
                self._assert_rest_unauthorized(resp)
