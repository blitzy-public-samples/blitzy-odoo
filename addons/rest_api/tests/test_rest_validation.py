# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Strict schema-validation integration tests for the REST surface (Gate 2).

This module proves the **anti-corruption boundary** of the additive REST API
introduced by :mod:`odoo.addons.rest_api`: a REST *write* payload carrying an
**extra/unknown field** or a **type-invalid field** is rejected with HTTP
``422`` -- and **no ORM record is created or modified**. Validation happens
*before* any ORM access ("422 before ORM", zero writes), which is exactly what
makes the strict pydantic request DTOs an anti-corruption layer rather than a
cosmetic check.

Why this holds by construction (see AAP sections 0.3.2, 0.6.5 / validation
Gate 2)
--------------------------------------------------------------------------
* Every ``*Create`` / ``*Update`` request DTO derives from
  ``BaseRestModel`` = ``ConfigDict(strict=True, extra='forbid')``. An unknown
  key therefore raises a pydantic ``extra_forbidden`` error and a wrongly-typed
  scalar (e.g. an ``int`` where a ``str`` is declared) raises a strict type
  error; both surface as :class:`pydantic.ValidationError`.
* Each per-model controller validates the *raw* request body with
  ``<Model>Create.model_validate_json(...)`` **first**, and only proceeds to
  ``request.env[model].create(...)`` on success -- so a schema-invalid body
  never reaches the ORM.
* ``RestDispatcher.handle_error`` maps a pydantic ``ValidationError`` to the
  REST error envelope ``{"status": 422, "code": "validation_error",
  "message": <str>, "details": [ ...per-field... ]}`` -- intentionally
  **distinct** from the JSON-RPC envelope ``{code, message, data}`` (the REST
  body carries no ``data`` key).

Transport contract
------------------
``type='rest'`` routes require ``Content-Type: application/json`` (and a
``/api/`` path); otherwise ``RestDispatcher.is_compatible_with`` yields ``415``
*before* validation. Every request below therefore sends the JSON content type
and an ``Authorization: Bearer`` token (an ``rpc``-scope API key), and builds
the body explicitly with :func:`json.dumps` so a deliberately schema-invalid
shape reaches the validator unaltered.

Minimal-install robustness
--------------------------
``rest_api`` depends only on ``['base', 'web', 'auth_oauth']``; the ``sale``,
``account``, ``stock`` and ``crm`` business modules are absent under a bare
``-i rest_api`` install. All five controllers still load and register their
routes, and an extra-field POST still returns ``422`` because validation runs
before the (possibly non-existent) ORM model is touched. Every ORM
``search_count`` / fixture is therefore guarded by ``if model_name in
self.env:``; ``res.partner`` (from ``base``) is always present.

Style reference (NOT imported, NOT modified): the legacy
``odoo/addons/test_rpc/tests/test_error.py`` HttpCase -- its ``mute_logger``
usage and ``@tagged('-at_install', 'post_install')`` decoration. The legacy RPC
tests must keep passing unmodified (Gate 1); nothing from them is imported here.
"""

import json

from odoo.tests import common
from odoo.tools import mute_logger


@common.tagged('post_install', '-at_install')
class TestRestValidation(common.HttpCase):
    """Prove Gate 2: schema-invalid REST writes ``422`` with zero ORM writes.

    All requests are made over HTTP (``HttpCase``) as a dedicated internal user
    authenticated with a single ``rpc``-scope API key. The suite is parametric
    over the five pilot models so the same guarantee is asserted uniformly for
    ``res.partner``, ``sale.order``, ``account.move``, ``stock.picking`` and
    ``crm.lead``.
    """

    #: The unknown key injected into an otherwise-valid payload to trigger the
    #: strict ``extra='forbid'`` rejection. Deliberately implausible so it can
    #: never collide with a real field on any pilot model.
    UNKNOWN_KEY = 'this_field_does_not_exist'

    #: Per-model *type-invalid* payloads: each corrupts the model's required
    #: field with a wrongly-typed scalar. Under ``strict=True`` no coercion is
    #: attempted, so each raises a pydantic type error -> ``422``.
    TYPE_INVALID_PAYLOADS = {
        'res.partner': {'name': 12345},                       # int for Char(name)
        'sale.order': {'partner_id': 'not-an-integer'},       # str for M2o int
        'account.move': {'move_type': 12345},                 # int for Selection
        'stock.picking': {'picking_type_id': 'not-an-integer'},  # str for M2o int
        'crm.lead': {'name': 12345, 'type': 'lead'},          # int for Char(name)
    }

    def setUp(self):
        super().setUp()

        # A dedicated internal user for the REST calls. It is granted
        # ``group_user`` (base internal-user access) AND ``group_partner_manager``
        # so that the Phase D "valid payload" POST can genuinely CREATE a
        # ``res.partner`` (a plain ``group_user`` has read-only access to
        # ``res.partner`` -- 1,0,0,0 -- and could not create one). This does not
        # weaken the Gate 2 guarantee: schema-invalid payloads are rejected with
        # ``422`` *before* any ORM/ACL check, so the "zero writes" assertions
        # hold irrespective of the user's create rights.
        #
        # NB: the writable groups field on ``res.users`` is ``group_ids`` in this
        # Odoo 19.0 tree (the pre-19.0 ``groups_id`` no longer exists); the
        # ``(6, 0, ids)`` command sets the exact group membership.
        self.user = self.env['res.users'].create({
            'name': 'REST Val User',
            'login': 'rest_val_user',
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('base.group_partner_manager').id,
            ])],
        })

        # A persistent (no-expiration) ``rpc``-scope API key OWNED BY that user.
        # ``.sudo()`` is required to generate a key regardless of the user's own
        # privileges; the key's owner remains ``self.user``. The same key both
        # authenticates the REST bearer and identifies the acting user.
        self.key = self.env['res.users.apikeys'].with_user(
            self.user,
        ).sudo()._generate('rpc', 'REST validation test', False)

        # Mandatory headers for every ``type='rest'`` request: the JSON content
        # type (else 415 before validation) and the bearer token (else 401).
        self.headers = {
            'Authorization': 'Bearer %s' % self.key,
            'Content-Type': 'application/json',
        }

        # Parametric description of the five pilot models:
        #   (model_name, collection_path, declared_valid_payload_or_None)
        # ``None`` marks a model whose required field is a relational id, which
        # is resolved to a real fixture id (when installed) or a literal
        # placeholder (when not) by :meth:`_resolve_base_payload`.
        self.MODELS = [
            ('res.partner', '/api/v1/partners', {'name': 'Valid Partner'}),
            ('sale.order', '/api/v1/sale-orders', None),
            ('account.move', '/api/v1/account-moves', {'move_type': 'entry'}),
            ('stock.picking', '/api/v1/stock-pickings', None),
            ('crm.lead', '/api/v1/crm-leads', {'name': 'Lead', 'type': 'lead'}),
        ]

        # Flush the pending fixtures (user + API key) so the HTTP worker, which
        # shares this test's cursor, observes them when it authenticates the
        # request.
        self.env.flush_all()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_base_payload(self, model_name, declared):
        """Return a per-model *base valid* create payload.

        Models whose minimal valid payload is a set of literals
        (``res.partner``, ``account.move``, ``crm.lead``) return their declared
        payload verbatim. ``sale.order`` / ``stock.picking`` -- whose required
        field is a relational id -- resolve a real fixture id when the model is
        installed, falling back to a literal placeholder id otherwise. The id is
        never dereferenced by these tests: strict schema validation rejects the
        payload before any ORM access, so any integer satisfies the ``int``
        typing of the required field.

        :param str model_name: the pilot model's technical name.
        :param declared: the literal payload declared in :data:`MODELS`, or
            ``None`` when a fixture-resolved relational id is required.
        :return: a fresh ``dict`` usable as the base of a create payload.
        :rtype: dict
        """
        if declared is not None:
            # Return a copy so callers may freely mutate (e.g. inject a key).
            return dict(declared)
        if model_name == 'sale.order':
            if model_name in self.env:
                partner = self.env['res.partner'].create({
                    'name': 'REST Val SO Partner',
                })
                self.env.flush_all()
                return {'partner_id': partner.id}
            return {'partner_id': 1}
        if model_name == 'stock.picking':
            if model_name in self.env:
                picking_type = self.env['stock.picking.type'].search([], limit=1)
                return {'picking_type_id': picking_type.id if picking_type else 1}
            return {'picking_type_id': 1}
        return {}

    def _assert_validation_error_envelope(self, resp):
        """Assert ``resp`` is a REST ``422`` validation-error envelope.

        Checks the full REST error contract and, crucially, that it is **not**
        the JSON-RPC envelope (which uses ``{code, message, data}``): the REST
        body carries ``status`` / ``code`` / ``message`` / ``details`` and no
        ``data`` key.

        :param resp: the :class:`requests.Response` returned by ``url_open``.
        :return: the decoded JSON body (a ``dict``).
        :rtype: dict
        """
        self.assertEqual(
            resp.status_code, 422,
            "a schema-invalid payload must be rejected with HTTP 422; "
            "got %s: %r" % (resp.status_code, resp.text),
        )
        body = resp.json()
        self.assertIsInstance(body, dict, "the 422 body must be a JSON object")
        self.assertEqual(body.get('status'), 422, "envelope 'status' must be 422")
        self.assertEqual(
            body.get('code'), 'validation_error',
            "envelope 'code' must be 'validation_error'",
        )
        self.assertIn('message', body, "envelope must carry a 'message'")
        self.assertIsInstance(
            body.get('details'), list,
            "envelope 'details' must be a list",
        )
        self.assertTrue(
            body['details'],
            "envelope 'details' must be non-empty for a validation failure",
        )
        # The REST envelope must NEVER be confused with the JSON-RPC envelope
        # {code, message, data}. The distinguishing marker is the absence of a
        # 'data' key and the presence of 'status' / 'details'.
        self.assertNotIn(
            'data', body,
            "REST envelope must not leak the JSON-RPC 'data' member",
        )
        return body

    # ------------------------------------------------------------------
    # Gate 2 core -- extra/unknown field -> 422 with zero ORM writes
    # ------------------------------------------------------------------
    def test_extra_field_rejected_before_orm(self):
        """An unknown key yields ``422`` and creates no record (all 5 models).

        For each pilot model an otherwise-valid create payload is augmented with
        an unknown key. The strict ``extra='forbid'`` DTO rejects it with a
        pydantic ``extra_forbidden`` error, which the dispatcher renders as a
        ``422`` REST envelope. For installed models the ``search_count`` is
        asserted unchanged across the request -- the crux of Gate 2 (validation
        happens before any ORM access, so nothing is written).
        """
        for model_name, path, declared in self.MODELS:
            with self.subTest(model=model_name):
                base = self._resolve_base_payload(model_name, declared)
                payload = dict(base)
                payload[self.UNKNOWN_KEY] = 'x'

                installed = model_name in self.env
                count_before = (
                    self.env[model_name].sudo().search_count([])
                    if installed else None
                )

                # The request intentionally errors; mute the framework logger so
                # the expected 422 does not spam the test output.
                with mute_logger('odoo.http'):
                    resp = self.url_open(
                        path,
                        data=json.dumps(payload),
                        headers=self.headers,
                        method='POST',
                    )

                body = self._assert_validation_error_envelope(resp)

                # At least one per-field detail should reference the offending
                # key. Be tolerant of pydantic's ``loc`` structure by searching
                # the serialized details for the injected key name.
                self.assertIn(
                    self.UNKNOWN_KEY, json.dumps(body['details']),
                    "the offending key should appear in the error details",
                )

                if installed:
                    count_after = self.env[model_name].sudo().search_count([])
                    self.assertEqual(
                        count_before, count_after,
                        "no record must be created for an invalid payload "
                        "(422 before ORM / zero writes)",
                    )

    # ------------------------------------------------------------------
    # Gate 2 strict typing -- wrongly-typed field -> 422
    # ------------------------------------------------------------------
    def test_type_invalid_rejected(self):
        """A wrongly-typed field yields ``422`` with no record written.

        Primarily asserted on ``res.partner`` (always available via ``base``):
        posting ``{"name": 12345}`` sends an ``int`` where a ``str`` is
        declared, which ``strict=True`` rejects without coercion. The other
        pilot models are exercised opportunistically when installed, each with
        an analogous type violation on their required field.
        """
        for model_name, path, _declared in self.MODELS:
            # ``res.partner`` is mandatory; the rest are opportunistic and only
            # run when their business module is installed.
            if model_name != 'res.partner' and model_name not in self.env:
                continue
            with self.subTest(model=model_name):
                payload = self.TYPE_INVALID_PAYLOADS[model_name]

                installed = model_name in self.env
                count_before = (
                    self.env[model_name].sudo().search_count([])
                    if installed else None
                )

                with mute_logger('odoo.http'):
                    resp = self.url_open(
                        path,
                        data=json.dumps(payload),
                        headers=self.headers,
                        method='POST',
                    )

                self._assert_validation_error_envelope(resp)

                if installed:
                    count_after = self.env[model_name].sudo().search_count([])
                    self.assertEqual(
                        count_before, count_after,
                        "no record must be created for a type-invalid payload "
                        "(422 before ORM / zero writes)",
                    )

    # ------------------------------------------------------------------
    # Sanity -- a genuinely valid payload is NOT a 422 (no over-rejection)
    # ------------------------------------------------------------------
    def test_valid_payload_not_422(self):
        """A valid ``res.partner`` create must not be rejected as a ``422``.

        This guards against a schema so strict that it rejects *everything*:
        posting a genuinely valid ``{"name": ...}`` must pass validation and
        reach the ORM. The assertion is intentionally lenient -- ``!= 422``
        rather than a specific ``2xx`` -- to avoid coupling to the exact success
        status while still proving the validator did not reject a valid body.
        """
        with mute_logger('odoo.http'):
            resp = self.url_open(
                '/api/v1/partners',
                data=json.dumps({'name': 'Genuinely Valid'}),
                headers=self.headers,
                method='POST',
            )
        self.assertNotEqual(
            resp.status_code, 422,
            "a genuinely valid payload must not be rejected as a "
            "schema-validation 422; got %s: %r" % (resp.status_code, resp.text),
        )
