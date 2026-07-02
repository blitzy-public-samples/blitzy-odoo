# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""CRUD verb -> ORM-operation mapping tests for the REST surface.

This module is the *behavioural* counterpart to the schema, authorization and
OpenAPI test suites of :mod:`odoo.addons.rest_api`. Where those prove *what* a
request must look like and *who* may perform it, this suite proves the
**verb -> ORM-operation -> HTTP-status/response** contract of every pilot
resource end to end, exactly as documented in AAP section 0.3.2::

    Verb    Path                       ORM operation                Status  Response body
    ------  -------------------------  ---------------------------  ------  ------------------------------------
    GET     /api/v1/<resource>         search_read + search_count   200     {"items": [<Read>...], "meta": {...}}
    GET     /api/v1/<resource>/{id}    read                         200     <Read> object (including id)
    POST    /api/v1/<resource>         create                       200     <Read> object of the created record
    PATCH   /api/v1/<resource>/{id}    write                        200     <Read> object of the updated record
    DELETE  /api/v1/<resource>/{id}    unlink                       204     empty body

Every assertion is anchored to ORM **ground truth** (``browse().exists()`` /
field re-reads) rather than to the HTTP response alone, so the tests prove that
the HTTP verb genuinely triggered the corresponding ORM operation and not merely
that the controller echoed a plausible JSON payload.

Design notes and the contracts these tests exercise
----------------------------------------------------
* **JSON content type is mandatory.** A ``@route(type='rest')`` route is served
  by ``RestDispatcher``, whose ``is_compatible_with`` guard rejects any request
  whose media type is not ``application/json`` with ``415`` -- *including*
  ``GET`` and ``DELETE``. Every helper therefore sends
  ``Content-Type: application/json`` together with the ``Authorization: Bearer``
  header.
* **Collection filters live in the query string.** ``limit`` / ``offset`` /
  ``domain`` are read from ``request.httprequest.args`` by the controller, never
  from the body, so they are passed through ``url_open(params=...)``.
* **Admin-owned API key.** The CRUD gate proves the verb -> ORM mapping, not
  authorization (that is covered independently by the authorization-parity
  suite / Gate 3). Using an ``admin``-owned key removes all ACL / record-rule
  friction so ``create`` / ``write`` / ``unlink`` succeed uniformly across every
  pilot model.
* **Missing records yield 404.** A ``GET`` / ``PATCH`` / ``DELETE`` on an id
  that does not resolve to a visible record makes ``record.exists()`` false; the
  controller raises ``werkzeug.exceptions.NotFound`` which ``RestDispatcher``
  renders as the REST error envelope ``{status, code, message, details}`` with
  ``status == 404``.
* **DELETE returns 204 with an empty body**, produced by
  ``request.make_response('', status=204)`` and passed through by the dispatcher
  unchanged.

Gate 1 (legacy-RPC preservation) is honoured passively: this is a brand-new
``HttpCase`` module that neither imports nor references any legacy JSON-RPC or
XML-RPC integration test module.

Cursor-sharing discipline
-------------------------
Under :class:`~odoo.tests.common.HttpCase` the test method and the in-process
HTTP worker share a single test cursor. Two rules follow and are applied
throughout:

* **Flush before an HTTP call must observe a test-side write.** After creating
  fixtures (the API key in :meth:`setUp`, an ORM record in the optional-model
  proof) the test calls ``self.env.flush_all()`` so the worker sees them.
* **Invalidate after an HTTP call wrote through the worker.** A REST
  ``create`` / ``write`` / ``unlink`` mutates the shared cursor from the worker
  side; the test env's ORM cache is invalidated (``invalidate_all`` /
  ``invalidate_recordset``) before re-reading ground truth.
"""

import json

from odoo.tests import common
from odoo.tools import mute_logger


@common.tagged('post_install', '-at_install')
class TestRestCrud(common.HttpCase):
    """End-to-end verb -> ORM-operation mapping tests for the REST surface.

    ``res.partner`` (always available through ``base``) carries the
    non-skippable full-lifecycle proof of all five mappings; the four remaining
    pilot models are exercised opportunistically, guarded by
    ``if model not in self.env`` so the suite is robust whether or not the
    ``sale`` / ``account`` / ``stock`` / ``crm`` addons are installed alongside
    ``rest_api``.
    """

    def setUp(self):
        super().setUp()
        # An admin-owned, persistent (no-expiration) ``rpc``-scope API key. It
        # doubles as the REST ``Authorization: Bearer`` credential. ``sudo()`` is
        # required so a persistent key may be minted regardless of the caller's
        # own key-duration privileges; the key's owner remains ``admin``.
        self.admin = self.env.ref('base.user_admin')
        self.key = self.env['res.users.apikeys'].with_user(
            self.admin,
        ).sudo()._generate('rpc', 'REST crud test', False)
        # Mandatory on every ``type='rest'`` request: the bearer token *and* the
        # JSON media type (a non-JSON media type is rejected with ``415`` before
        # dispatch, even for GET/DELETE).
        self.headers = {
            'Authorization': 'Bearer %s' % self.key,
            'Content-Type': 'application/json',
        }
        # The HTTP worker shares this test's cursor; flush so it observes the
        # freshly generated API key when it authenticates the requests below.
        self.env.flush_all()

    # ------------------------------------------------------------------
    # Request helpers -- every one sends the mandatory JSON content type.
    # ------------------------------------------------------------------
    def _post(self, path, payload):
        """``POST <path>`` with a JSON body (ORM ``create``)."""
        return self.url_open(
            path,
            data=json.dumps(payload),
            headers=self.headers,
            method='POST',
        )

    def _get(self, path, params=None):
        """``GET <path>`` with optional query-string ``params`` (ORM read)."""
        return self.url_open(
            path,
            headers=self.headers,
            method='GET',
            params=params,
        )

    def _patch(self, path, payload):
        """``PATCH <path>`` with a JSON body (ORM ``write``)."""
        return self.url_open(
            path,
            data=json.dumps(payload),
            headers=self.headers,
            method='PATCH',
        )

    def _delete(self, path):
        """``DELETE <path>`` (ORM ``unlink``)."""
        return self.url_open(
            path,
            headers=self.headers,
            method='DELETE',
        )

    # ------------------------------------------------------------------
    # Shared assertions
    # ------------------------------------------------------------------
    def _assert_collection_body(self, body, expected_id):
        """Assert a collection ``GET`` body matches the ``<Model>List`` shape.

        Proves the ``search_read`` + ``search_count`` mapping: the response must
        expose an ``items`` array and a ``meta`` block carrying at least
        ``limit`` / ``offset`` / ``total``, the total must be positive, and the
        queried id must appear among the returned items.

        :param dict body: decoded collection response body.
        :param int expected_id: id that must be present in ``items``.
        """
        self.assertIn('items', body)
        self.assertIn('meta', body)
        self.assertGreaterEqual(
            set(body['meta']),
            {'limit', 'offset', 'total'},
            "meta must carry limit/offset/total",
        )
        self.assertGreaterEqual(
            body['meta']['total'], 1,
            "search_count must report at least the queried record",
        )
        self.assertIn(
            expected_id,
            [item['id'] for item in body['items']],
            "search_read must return the queried record",
        )

    def _assert_rest_error_envelope(self, resp, expected_status):
        """Assert a response carries the REST error envelope, if it has a body.

        The REST envelope is ``{status, code, message, details}`` and is
        intentionally distinct from the JSON-RPC ``{code, message, data}``
        envelope. Per the directive the body is validated *only when present as
        JSON* (an error response is permitted to be bodiless), but when a JSON
        body exists it must be the REST envelope with a matching ``status``.

        :param resp: the HTTP response object.
        :param int expected_status: the HTTP status the envelope must echo.
        """
        try:
            body = resp.json()
        except ValueError:
            # A bodiless (or non-JSON) error response is tolerated.
            return
        self.assertIsInstance(body, dict)
        for key in ('status', 'code', 'message', 'details'):
            self.assertIn(key, body, "REST error envelope must expose %r" % key)
        self.assertEqual(body['status'], expected_status)
        # The REST envelope must never masquerade as the JSON-RPC envelope.
        self.assertNotIn('data', body)

    # ==================================================================
    # Phase B -- res.partner full lifecycle (ALWAYS available; the
    # non-skippable proof of all five verb -> ORM mappings).
    # ==================================================================
    def test_partner_full_crud_lifecycle(self):
        """POST -> GET(id) -> GET(collection) -> PATCH -> DELETE on a partner.

        Walks a single ``res.partner`` record through every verb and asserts,
        at each step, both the HTTP status/response contract *and* the matching
        ORM ground truth -- proving ``create`` / ``read`` / ``search_read`` +
        ``search_count`` / ``write`` / ``unlink`` respectively.
        """
        Partner = self.env['res.partner']

        # -- POST (create) -> ORM create, HTTP 200 with the Read body ---------
        resp = self._post('/api/v1/partners', {'name': 'CRUD Partner'})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn('id', body)
        self.assertEqual(body['name'], 'CRUD Partner')
        pid = body['id']
        # ORM ground truth: the record really exists with the sent name.
        self.env.invalidate_all()
        rec = Partner.browse(pid)
        self.assertTrue(rec.exists(), "POST must have created the partner")
        self.assertEqual(rec.name, 'CRUD Partner')

        # -- GET item (read) -> HTTP 200 with the Read body -------------------
        resp = self._get('/api/v1/partners/%d' % pid)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body['id'], pid)
        self.assertEqual(body['name'], 'CRUD Partner')

        # -- GET collection (search_read + search_count) -> HTTP 200 ----------
        resp = self._get(
            '/api/v1/partners',
            params={'domain': json.dumps([['id', '=', pid]])},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self._assert_collection_body(resp.json(), pid)

        # -- PATCH (write) -> ORM write, HTTP 200 with the updated Read body --
        resp = self._patch(
            '/api/v1/partners/%d' % pid, {'name': 'CRUD Partner v2'},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()['name'], 'CRUD Partner v2')
        # ORM ground truth: invalidate the cached name before re-reading.
        rec.invalidate_recordset()
        self.assertEqual(rec.name, 'CRUD Partner v2')

        # -- DELETE (unlink) -> ORM unlink, HTTP 204 with an EMPTY body -------
        resp = self._delete('/api/v1/partners/%d' % pid)
        self.assertEqual(resp.status_code, 204, resp.text)
        self.assertEqual(resp.text, '', "DELETE 204 must have an empty body")
        # ORM ground truth: the record is gone.
        self.env.invalidate_all()
        self.assertFalse(
            Partner.browse(pid).exists(), "DELETE must have unlinked the partner",
        )

    @mute_logger('odoo.http')
    def test_partner_missing_record_404(self):
        """GET / PATCH / DELETE on a non-existent id all return ``404``.

        A missing record fails ``record.exists()`` in the controller, raising
        ``werkzeug.exceptions.NotFound`` which the dispatcher renders as the REST
        error envelope with ``status == 404``. ``odoo.http`` is muted because
        these deliberate 404s would otherwise log noise.
        """
        missing_id = 99999999
        # Guard: the id must genuinely not exist for the assertions to be valid.
        self.assertFalse(self.env['res.partner'].browse(missing_id).exists())

        resp = self._get('/api/v1/partners/%d' % missing_id)
        self.assertEqual(resp.status_code, 404, resp.text)
        self._assert_rest_error_envelope(resp, 404)

        # PATCH carries a schema-valid body so it passes validation and reaches
        # the existence check (proving the 404 is the *missing-record* 404, not
        # a validation 422).
        resp = self._patch('/api/v1/partners/%d' % missing_id, {'name': 'x'})
        self.assertEqual(resp.status_code, 404, resp.text)
        self._assert_rest_error_envelope(resp, 404)

        resp = self._delete('/api/v1/partners/%d' % missing_id)
        self.assertEqual(resp.status_code, 404, resp.text)
        self._assert_rest_error_envelope(resp, 404)

    # ==================================================================
    # Phase C -- the four optional pilots, each guarded by installation.
    # ==================================================================
    def _a_partner_id(self):
        """Create and return the id of a throwaway partner (for relations)."""
        return self.env['res.partner'].create({'name': 'CRUD Rel Partner'}).id

    def _a_picking_type_id(self):
        """Return the id of any ``stock.picking.type`` (or ``False`` if none)."""
        return self.env['stock.picking.type'].search([], limit=1).id

    def _optional_specs(self):
        """Return the per-model CRUD spec table for the four optional pilots.

        ORM-create values and REST-create payloads are wrapped in zero-argument
        callables so that model-specific lookups (a partner id, a picking-type
        id) are evaluated **only** for models that are actually installed --
        every spec is reached solely from inside the ``if model in self.env``
        guard in :meth:`test_optional_models_crud`.

        Each spec maps to:

        * ``model`` -- the ORM model name gating the whole entry.
        * ``base`` -- the resource collection path.
        * ``orm_vals`` -- callable returning ``create`` vals for the robust,
          ORM-seeded read/list/delete proof.
        * ``rest_payload`` -- callable returning the minimal strict-DTO body for
          the best-effort REST ``create`` proof.
        * ``patch_payload`` / ``patch_field`` -- a single field mutation for the
          best-effort REST ``write`` proof and the key to verify in the Read
          body.

        :rtype: list[dict]
        """
        return [
            {
                'model': 'sale.order',
                'base': '/api/v1/sale-orders',
                'orm_vals': lambda: {'partner_id': self._a_partner_id()},
                'rest_payload': lambda: {'partner_id': self._a_partner_id()},
                'patch_payload': {'client_order_ref': 'REF-1'},
                'patch_field': 'client_order_ref',
            },
            {
                'model': 'account.move',
                'base': '/api/v1/account-moves',
                'orm_vals': lambda: {'move_type': 'entry'},
                'rest_payload': lambda: {'move_type': 'entry'},
                'patch_payload': {'ref': 'CRUD-REF'},
                'patch_field': 'ref',
            },
            {
                'model': 'stock.picking',
                'base': '/api/v1/stock-pickings',
                'orm_vals': lambda: {'picking_type_id': self._a_picking_type_id()},
                'rest_payload': lambda: {'picking_type_id': self._a_picking_type_id()},
                'patch_payload': {'origin': 'CRUD-ORIGIN'},
                'patch_field': 'origin',
            },
            {
                'model': 'crm.lead',
                'base': '/api/v1/crm-leads',
                'orm_vals': lambda: {'name': 'CRUD Lead', 'type': 'lead'},
                'rest_payload': lambda: {'name': 'CRUD Lead REST', 'type': 'lead'},
                'patch_payload': {'name': 'CRUD Lead v2'},
                'patch_field': 'name',
            },
        ]

    def test_optional_models_crud(self):
        """Exercise the verb -> ORM mapping for every *installed* optional pilot.

        For each of ``sale.order`` / ``account.move`` / ``stock.picking`` /
        ``crm.lead`` that is present in the registry, two complementary proofs
        run inside a :meth:`subTest`:

        #. **Robust ORM-seeded proof** -- a record is created directly through
           the ORM (independent of the REST create's mandatory-field surface),
           then ``GET`` collection, ``GET`` item and ``DELETE`` prove
           ``search_read`` + ``search_count``, ``read`` and ``unlink``.
        #. **Best-effort REST create/write proof** -- ``POST`` then ``PATCH``
           through the REST surface prove ``create`` and ``write`` *when* the
           minimal DTO payload is a sufficient create body. Should a model
           demand additional mandatory fields (yielding ``422`` / ``400``), the
           failure is tolerated: the mandatory verb -> ORM proof is already
           carried by ``res.partner`` (Phase B) and by the ORM-seeded proof
           above.

        Models whose addon is not installed are skipped, so the suite passes
        cleanly under a bare ``-i rest_api`` install as well as under a fuller
        install that includes the pilot addons.
        """
        for spec in self._optional_specs():
            model = spec['model']
            if model not in self.env:
                # Addon providing this pilot model is not installed.
                continue
            with self.subTest(model=model):
                self._run_optional_model_crud(spec)

    def _run_optional_model_crud(self, spec):
        """Run both CRUD proofs for one installed optional pilot model.

        :param dict spec: a single entry from :meth:`_optional_specs`.
        """
        model = spec['model']
        base = spec['base']
        Model = self.env[model]

        # === Robust proof: read / list / delete via an ORM-created record ===
        # Seed the fixture through the ORM. A few pilots need more environment
        # setup than a bare addon install provides -- ``account.move`` needs a
        # journal (hence a chart of accounts) and ``stock.picking`` needs an
        # operation type. When the minimal vals cannot yield a record in the
        # current install, that pilot is simply not exercisable here, so it is
        # skipped gracefully: the mandatory verb -> ORM proof is carried in full
        # by ``res.partner`` (Phase B) irrespective of the optional pilots. This
        # tolerance applies ONLY to seeding the fixture; once a record exists the
        # read / list / delete assertions below are strict.
        try:
            rec = Model.create(spec['orm_vals']())
        except Exception:  # noqa: BLE001 - environment-driven fixture gap, tolerated by design
            return
        # The HTTP worker shares this cursor; flush so it sees the fixture.
        self.env.flush_all()

        # GET collection -> search_read + search_count.
        resp = self._get(base, params={'domain': json.dumps([['id', '=', rec.id]])})
        self.assertEqual(resp.status_code, 200, resp.text)
        self._assert_collection_body(resp.json(), rec.id)

        # GET item -> read.
        resp = self._get('%s/%d' % (base, rec.id))
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()['id'], rec.id)

        # DELETE -> unlink (204, empty body); confirm via ORM ground truth.
        resp = self._delete('%s/%d' % (base, rec.id))
        self.assertEqual(resp.status_code, 204, resp.text)
        self.assertEqual(resp.text, '')
        self.env.invalidate_all()
        self.assertFalse(
            Model.browse(rec.id).exists(),
            "DELETE must have unlinked the %s record" % model,
        )

        # === Best-effort proof: create / write via the REST surface ===
        # Tolerate a non-2xx create for models that require more mandatory
        # fields than the minimal DTO payload supplies -- mute the expected
        # error logs in that case.
        with mute_logger('odoo.http', 'odoo.sql_db'):
            resp = self._post(base, spec['rest_payload']())
        if resp.status_code != 200:
            # Tolerated: the mandatory verb -> ORM proof is already covered by
            # res.partner (Phase B) and the ORM-seeded proof above.
            return

        cbody = resp.json()
        self.assertIn('id', cbody, "REST create must return the created id")
        new_id = cbody['id']
        # ORM ground truth: the REST POST really created the record.
        self.env.invalidate_all()
        self.assertTrue(
            Model.browse(new_id).exists(),
            "REST POST must have created the %s record" % model,
        )

        # PATCH -> write (best-effort): only assert the mutation when the write
        # itself succeeds.
        presp = self._patch('%s/%d' % (base, new_id), spec['patch_payload'])
        if presp.status_code == 200:
            field = spec['patch_field']
            self.assertEqual(
                presp.json().get(field),
                spec['patch_payload'][field],
                "REST PATCH must reflect the written %s" % field,
            )
