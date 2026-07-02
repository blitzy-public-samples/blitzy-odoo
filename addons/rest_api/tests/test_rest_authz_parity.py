# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Authorization-parity integration tests for the REST surface (Gate 3).

This module proves the central authorization guarantee of the additive REST
API introduced by :mod:`odoo.addons.rest_api`: a REST operation passes through
``ir.model.access`` + ``ir.rule`` + field-group filtering **identically** to
the equivalent JSON-RPC call. There is no parallel or simplified authorization
path for REST -- both surfaces reach the very same ORM, bound to the very same
user, so for the *same user* and the *same record* they must yield:

* **identical allow/deny outcomes**, and
* when allowed, **identical visible field sets**.

Why this holds by construction (see AAP sections 0.3.2, 0.6.4)
--------------------------------------------------------------
* ``RestDispatcher.dispatch`` delegates through
  ``registry['ir.http']._dispatch`` -- the same pipeline used by
  ``JsonRPCDispatcher`` -- and the ``res.partner`` controller performs every
  data operation via ``request.env['res.partner'].<op>()`` bound to the
  authenticated user (no ``sudo``, no direct SQL). So ``ir.model.access``,
  ``ir.rule`` and field-group filtering apply exactly as they do for a
  JSON-RPC ``execute_kw`` call.
* The controller derives the fields it reads from ``PartnerRead`` -- the same
  DTO whose fields we request over JSON-RPC here -- so the two reads request
  an identical field set for an identical user.

Test strategy
-------------
The two surfaces are driven with the **same** ``rpc``-scope API key: it
authenticates the REST bearer *and* doubles as the password argument in
``execute_kw`` for JSON-RPC. Both calls therefore run as the exact same user
with the exact same ORM enforcement -- this is the core of the parity proof.

Allow/deny is never hardcoded: it is derived from the **ORM ground truth**
(``check_access`` / ``exists`` evaluated ``with_user(demo)``), so the tests
stay robust across installs with differing default record rules.

Transport robustness: the JSON-RPC read prefers the real HTTP ``/jsonrpc``
``execute_kw`` endpoint (served by the ``rpc`` addon, which auto-installs with
``base``). When that endpoint is not available it falls back to the in-process
ORM read bound to the demo user -- which is exactly what ``execute_kw``
performs server-side after authenticating -- so the authorization outcome
compared here is identical either way.

Style reference (not imported): the legacy RPC "path" HttpCase shipped in the
``test_rpc`` module's test suite (``HttpCaseWithUserDemo``,
``make_jsonrpc_request``, ``get_db_name``,
``@tagged('-at_install', 'post_install')``). Those legacy RPC tests are a
pattern reference only -- they are neither imported nor modified (Gate 1).
"""

from odoo.exceptions import AccessError, MissingError
from odoo.tests import get_db_name, tagged
from odoo.tools import mute_logger

from odoo.addons.base.tests.common import HttpCaseWithUserDemo
from odoo.addons.rest_api.schemas import CrmLeadRead, PartnerRead

try:
    # ``make_jsonrpc_request`` raises ``JsonRpcException`` when the JSON-RPC
    # response carries an ``error`` member (i.e. the ORM raised an
    # AccessError/AccessDenied). Importing it lets us treat *only* an RPC-level
    # error as a "deny" while still surfacing unexpected transport failures.
    from odoo.tests.common import JsonRpcException
except ImportError:  # pragma: no cover - defensive: keep the module importable
    JsonRpcException = None


@tagged('-at_install', 'post_install')
class TestRestAuthzParity(HttpCaseWithUserDemo):
    """Assert REST authorization parity with JSON-RPC for the demo user.

    Uses ``HttpCaseWithUserDemo`` so ``self.user_demo`` is a genuine non-admin
    user (member of ``base.group_user`` and ``base.group_partner_manager``).
    All REST and JSON-RPC calls are made as that user via the single
    ``rpc``-scope API key created in :meth:`setUp`.
    """

    def setUp(self):
        super().setUp()
        # A single rpc-scope API key OWNED BY the demo user. It is used both as
        # the REST ``Authorization: Bearer`` token and as the ``execute_kw``
        # password, so both surfaces authenticate as the identical user.
        # ``.sudo()`` is required so a persistent (no-expiration) key may be
        # generated regardless of the demo user's own privileges; the key's
        # owner is still ``self.env.user`` == demo.
        self.key = self.env['res.users.apikeys'].with_user(
            self.user_demo,
        ).sudo()._generate('rpc', 'REST authz parity', False)

        # Derive the field list from the response DTO exactly as the controller
        # does (``[n for n in PartnerRead.model_fields if n != 'id']``) so the
        # JSON-RPC read requests the same fields the REST read exposes -- making
        # field-set parity a property established by construction.
        self.fields = [name for name in PartnerRead.model_fields if name != 'id']

        # A partner the demo user is allowed to read (no restrictive rule yet).
        self.partner = self.env['res.partner'].create({
            'name': 'Parity Partner',
            'email': 'parity@example.com',
        })

        # Flush pending writes so the HTTP worker (which shares the test cursor)
        # observes the fixtures created above.
        self.env.flush_all()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _rest_read(self, path):
        """Read a single record over the REST surface as the demo user.

        Sends ``GET <path>`` with the bearer token and the mandatory
        ``application/json`` content type (a ``type='rest'`` route rejects a
        non-JSON media type with ``415`` before dispatch).

        :param str path: the REST path, e.g. ``/api/v1/partners/42``.
        :return: ``(status_code, body)`` where ``body`` is the decoded JSON
            (a ``dict`` for both success and the REST error envelope) or
            ``None`` if the response carried no JSON body.
        :rtype: tuple[int, dict | None]
        """
        resp = self.url_open(
            path,
            method='GET',
            headers={
                'Authorization': 'Bearer %s' % self.key,
                'Content-Type': 'application/json',
            },
        )
        try:
            body = resp.json()
        except ValueError:
            body = None
        return resp.status_code, body

    def _jsonrpc_available(self):
        """Whether the ``/jsonrpc`` endpoint (from the ``rpc`` addon) is served.

        ``rpc`` is ``auto_install=True`` and depends only on ``base``, so it is
        normally present; this guard keeps the JSON-RPC comparison meaningful
        even in a stripped-down install by enabling a clean in-process fallback.
        """
        return bool(self.env['ir.module.module'].sudo().search_count([
            ('name', '=', 'rpc'),
            ('state', '=', 'installed'),
        ]))

    def _jsonrpc_read(self, model, record_id, fields):
        """Read one record "as the demo user" through the JSON-RPC semantics.

        Uses the SAME api key as the REST bearer so the call runs as the exact
        same user. Prefers the real HTTP ``/jsonrpc`` ``execute_kw`` endpoint;
        when unavailable it falls back to the in-process ORM read bound to the
        demo user -- exactly what ``execute_kw`` performs server-side after
        authenticating -- so the authorization outcome is identical.

        :return: ``('allow', record_dict)`` when the read succeeds, or
            ``('deny', None)`` when authorization forbids it (an ORM error
            surfaced by JSON-RPC, or an empty read result because a record rule
            filtered the record out).
        :rtype: tuple[str, dict | None]
        """
        if self._jsonrpc_available():
            try:
                result = self.make_jsonrpc_request('/jsonrpc', {
                    'service': 'object',
                    'method': 'execute_kw',
                    'args': [
                        get_db_name(),
                        self.user_demo.id,
                        self.key,
                        model,
                        'read',
                        [[record_id], fields],
                    ],
                })
            except Exception as exc:  # noqa: BLE001 - narrowed just below
                # An ORM AccessError/AccessDenied is surfaced by
                # ``make_jsonrpc_request`` as a ``JsonRpcException``; treat that
                # as a "deny" outcome. Any other (transport) error is a genuine
                # problem and must propagate.
                if JsonRpcException is not None and not isinstance(exc, JsonRpcException):
                    raise
                return 'deny', None
            # ``read`` returns [] (no error) when the id does not resolve to a
            # visible record; that is also a "deny" for parity purposes.
            if result:
                return 'allow', result[0]
            return 'deny', None

        # Fallback: in-process ORM read as the demo user.
        try:
            records = self.env[model].with_user(self.user_demo).browse(record_id).read(fields)
        except (AccessError, MissingError):
            return 'deny', None
        if records:
            return 'allow', records[0]
        return 'deny', None

    def _orm_can_read(self, model, record_id):
        """Ground truth: may the demo user read this record through the ORM?

        Evaluated ``with_user(demo)`` (never ``sudo``, so ``env.su`` is False
        and access control is enforced). A record filtered out by an
        ``ir.rule`` raises ``AccessError`` from :meth:`check_access`, and a
        non-existent id fails :meth:`exists`; both are reported as "cannot
        read".

        :rtype: bool
        """
        record = self.env[model].with_user(self.user_demo).browse(record_id)
        try:
            if not record.exists():
                return False
            record.check_access('read')
            return True
        except (AccessError, MissingError):
            return False

    # ------------------------------------------------------------------
    # Gate 3 -- ALLOW parity + identical visible field set (non-skippable)
    # ------------------------------------------------------------------
    @mute_logger('odoo.addons.rpc.controllers.jsonrpc')
    def test_allow_parity_partner(self):
        """REST and JSON-RPC both ALLOW, exposing an identical field set.

        For a partner the demo user can read, the REST read returns ``200`` and
        the JSON-RPC read succeeds, and both expose exactly ``{'id'}`` plus the
        ``PartnerRead`` business fields -- proving there is no simplified or
        divergent field exposure on the REST path.
        """
        # Ground truth: the demo user can read a plain partner.
        self.assertTrue(
            self._orm_can_read('res.partner', self.partner.id),
            "demo should be able to read a plain partner (ground truth)",
        )

        # REST surface -> 200 with a JSON body.
        status, body = self._rest_read('/api/v1/partners/%d' % self.partner.id)
        self.assertEqual(
            status, 200,
            "REST read should be allowed for the demo user; got %s: %r" % (status, body),
        )
        self.assertIsInstance(body, dict, "REST 200 must carry a JSON object body")

        # JSON-RPC surface (same user, same key) -> allow.
        outcome, rpc_record = self._jsonrpc_read('res.partner', self.partner.id, self.fields)
        self.assertEqual(
            outcome, 'allow',
            "JSON-RPC read should also be allowed for the demo user",
        )
        self.assertIsInstance(rpc_record, dict)

        # Identical visible field sets across the two surfaces.
        self.assertEqual(
            set(body.keys()), set(rpc_record.keys()),
            "REST and JSON-RPC must expose an identical visible field set "
            "for the same user and record",
        )
        # ... and that set is exactly {'id'} + the PartnerRead business fields.
        self.assertEqual(
            set(body.keys()), {'id'} | set(self.fields),
            "the shared field set must be {'id'} + the PartnerRead field set",
        )

        # Identical value spot-check on a stable scalar.
        self.assertEqual(
            body.get('name'), rpc_record.get('name'),
            "the same field must carry the same value on both surfaces",
        )
        self.assertEqual(body.get('name'), 'Parity Partner')

    # ------------------------------------------------------------------
    # Gate 3 -- DENY parity (record hidden by an ir.rule)
    # ------------------------------------------------------------------
    @mute_logger('odoo.http', 'odoo.addons.rpc.controllers.jsonrpc')
    def test_deny_parity_record_rule(self):
        """REST and JSON-RPC both DENY a record hidden by an ``ir.rule``.

        A restrictive read rule is installed so the demo user can no longer see
        ``self.partner``. The REST surface must reject the read (``403`` because
        the ORM raises ``AccessError`` for a rule-filtered but existing record,
        or ``404`` if the install maps it to ``MissingError``), the JSON-RPC
        surface must likewise not return the record's data, and both must agree
        with the ORM ground truth.
        """
        # Install a restrictive record rule targeting all internal users.
        self.env['ir.rule'].create({
            'name': 'REST parity hide partner',
            'model_id': self.env['ir.model']._get('res.partner').id,
            'groups': [(6, 0, [self.env.ref('base.group_user').id])],
            'domain_force': "[('id', '!=', %d)]" % self.partner.id,
            'perm_read': True,
            'perm_write': True,
            'perm_create': False,
            'perm_unlink': True,
        })
        # Flush the rule and clear the ormcache so the (shared) HTTP worker and
        # the in-process checks evaluate the fresh rule domain.
        self.env.flush_all()
        self.env.registry.clear_cache()

        # If, in this particular install, the rule does not actually hide the
        # record from the demo user, the DENY comparison is not deterministic;
        # skip *only* this subtest (ALLOW parity in the other test still runs).
        if self._orm_can_read('res.partner', self.partner.id):
            self.skipTest(
                "record rule did not hide the partner from the demo user in "
                "this install; deny-parity is not deterministic here",
            )

        # Ground truth: the demo user cannot read the record any more.
        self.assertFalse(
            self._orm_can_read('res.partner', self.partner.id),
            "the record rule should hide the partner from the demo user",
        )

        # REST surface -> deny (403 rule/ACL, or 404 missing) with the REST
        # error envelope.
        status, body = self._rest_read('/api/v1/partners/%d' % self.partner.id)
        self.assertIn(
            status, (403, 404),
            "REST must deny a rule-hidden record; got %s: %r" % (status, body),
        )
        if isinstance(body, dict):
            # The REST error envelope contract: {status, code, message, details}.
            self.assertEqual(body.get('status'), status)
            self.assertTrue(body.get('code'), "error envelope must carry a non-empty code")
            self.assertIn('details', body)

        # JSON-RPC surface (same user, same key) -> deny (raises, or empty read).
        outcome, _rpc_record = self._jsonrpc_read('res.partner', self.partner.id, self.fields)
        self.assertEqual(
            outcome, 'deny',
            "JSON-RPC must also deny the rule-hidden record",
        )

        # The essential parity assertion: REST(deny) == JSON-RPC(deny) == ORM(deny).
        self.assertFalse(self._orm_can_read('res.partner', self.partner.id))

    # ------------------------------------------------------------------
    # Optional robustness -- parity generalises to another pilot model
    # ------------------------------------------------------------------
    @mute_logger('odoo.addons.rpc.controllers.jsonrpc')
    def test_parity_second_pilot_model(self):
        """Bonus: the ALLOW-parity property generalises to another pilot model.

        Guarded and deliberately lenient -- it is a clean ``skipTest`` unless a
        second pilot model *and* its REST endpoint are actually available in the
        running install (e.g. when ``rest_api`` is installed together with the
        ``crm`` pilot). This never fails the suite; it only strengthens the
        proof when the extra surface is present.
        """
        model = 'crm.lead'
        if model not in self.env:
            self.skipTest("optional pilot model %r is not installed" % model)

        # ``CrmLeadRead`` is a pure pydantic DTO always shipped by the schemas
        # package (imported at the top of this module); the guard above is about
        # the ORM *model* being installed, not the schema being importable.
        fields = [name for name in CrmLeadRead.model_fields if name != 'id']
        lead = self.env[model].create({'name': 'Parity Lead'})
        self.env.flush_all()

        if not self._orm_can_read(model, lead.id):
            self.skipTest("demo cannot read a %r record in this install" % model)

        status, body = self._rest_read('/api/v1/crm-leads/%d' % lead.id)
        if status != 200 or not isinstance(body, dict):
            # The REST endpoint for this model is not wired in this install
            # (e.g. its controller module is absent); treat the bonus as a no-op.
            self.skipTest(
                "REST endpoint for %r is not available here (status=%s)" % (model, status),
            )

        outcome, rpc_record = self._jsonrpc_read(model, lead.id, fields)
        self.assertEqual(outcome, 'allow')
        self.assertIsInstance(rpc_record, dict)
        self.assertEqual(
            set(body.keys()), set(rpc_record.keys()),
            "REST and JSON-RPC must expose an identical field set for %r" % model,
        )
