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

from odoo.fields import Command
from odoo.tests import common
from odoo.tools import mute_logger


@common.tagged('post_install', '-at_install')
class TestRestCrud(common.HttpCase):
    """End-to-end verb -> ORM-operation mapping tests for the REST surface.

    ``res.partner`` (always available through ``base``) carries a non-skippable
    full-lifecycle proof of all five mappings. Each remaining pilot --
    ``sale.order`` / ``account.move`` / ``stock.picking`` / ``crm.lead`` -- has
    its own dedicated, STRICT lifecycle test that, in the expected install
    profile (the pilot addon installed alongside ``rest_api``), runs end to end
    and fails on any REST error; a test skips only when its addon is genuinely
    absent, so the suite still passes under a bare ``-i rest_api`` install. The
    three pilots exposing an x2many write DTO additionally prove the
    ``Command.set`` full-list REPLACE and empty-list CLEAR semantics their
    controllers must apply.
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
    # Phase C -- per-pilot full CRUD lifecycles (the four remaining pilots).
    #
    # Each pilot gets its own dedicated, STRICT lifecycle test. In the
    # *expected install profile* (the pilot addon installed alongside
    # ``rest_api``) every test runs end to end and FAILS on any REST error --
    # there is no tolerated create/write failure. A test ``skipTest``s only when
    # its addon is genuinely absent from the registry, so the suite still passes
    # under a bare ``-i rest_api`` install. Because a bare pilot install ships no
    # demo products, every relational fixture is built self-containedly through
    # the ORM.
    #
    # For the three pilots whose write DTOs expose an x2many relation
    # (``sale.order.order_line``, ``account.move.invoice_line_ids`` and
    # ``stock.picking.move_ids``) the lifecycle additionally proves the
    # ``Command.set`` full-list semantics the controllers must apply: a PATCH
    # carrying a *subset* id list REPLACES the relation down to that subset, and
    # a PATCH carrying an EMPTY list CLEARS it. The empty-list clear is the
    # decisive assertion -- a controller that forwarded the bare list straight to
    # the ORM (the defect these tests guard) would leave the lines untouched,
    # because a bare empty list is a silent no-op on ``write``.
    # ==================================================================

    def _a_product(self):
        """Create and return a self-contained consumable product.

        A bare pilot-addon install ships no demo products, so the relational
        fixtures below (sale lines, invoice lines, stock moves) mint their own.

        :return: a ``product.product`` singleton.
        """
        return self.env['product.product'].create({
            'name': 'CRUD Product',
            'type': 'consu',
        })

    def _a_partner(self):
        """Create and return a throwaway partner for relational fixtures.

        :return: a ``res.partner`` singleton.
        """
        return self.env['res.partner'].create({'name': 'CRUD Rel Partner'})

    def _assert_xmany_replace_and_clear(self, base, record, field, child_ids):
        """Prove ``Command.set`` REPLACE + CLEAR semantics through REST PATCH.

        Given a ``record`` already carrying at least two related ``child_ids`` on
        its x2many ``field``, this asserts the two behaviours that distinguish a
        correct ``[Command.set(ids)]`` conversion from the bare-list defect:

        #. **Replace to a subset** -- ``PATCH {field: [child_ids[0]]}`` must
           reduce the relation to *exactly* that one id (proving the whole list
           is replaced, not merely extended/linked), verified both in the PATCH
           Read body and against ORM ground truth.
        #. **Clear with an empty list** -- ``PATCH {field: []}`` must empty the
           relation. This is the decisive assertion: with the unfixed controller
           the empty list reaches ``write`` verbatim and is a no-op, leaving the
           lines in place; only the ``[Command.set([])]`` conversion clears them.

        :param str base: the resource collection path
            (e.g. ``/api/v1/sale-orders``).
        :param record: the parent recordset (a singleton).
        :param str field: the x2many field name under test.
        :param list child_ids: the currently-related ids (``len >= 2``).
        """
        self.assertGreaterEqual(
            len(child_ids), 2, "fixture must seed >=2 children to prove replace",
        )
        keep = child_ids[0]

        # -- REPLACE the full relation down to a strict subset --------------
        resp = self._patch('%s/%d' % (base, record.id), {field: [keep]})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(
            resp.json().get(field), [keep],
            "PATCH %s=[one id] must REPLACE the relation to exactly that id"
            % field,
        )
        # ORM ground truth (the worker wrote through the shared cursor).
        self.env.invalidate_all()
        self.assertEqual(
            record[field].ids, [keep],
            "ORM: %s must be replaced down to the single kept id" % field,
        )

        # -- CLEAR the relation with an empty list (decisive) ---------------
        resp = self._patch('%s/%d' % (base, record.id), {field: []})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(
            resp.json().get(field), [],
            "PATCH %s=[] must CLEAR the relation via Command.set([])" % field,
        )
        self.env.invalidate_all()
        self.assertEqual(
            record[field].ids, [],
            "ORM: %s=[] must clear every line "
            "(a bare-list no-op would leave them in place)" % field,
        )

    # ------------------------------------------------------------------
    # sale.order -- full lifecycle + order_line x2many replace/clear.
    # ------------------------------------------------------------------
    def test_sale_order_full_crud_lifecycle(self):
        """POST -> GET(id) -> GET(collection) -> PATCH -> x2many -> DELETE.

        Strict in the expected install profile: skips only if ``sale`` is not
        installed. Proves every verb -> ORM mapping for ``sale.order`` and the
        ``order_line`` full-list replace/clear semantics.
        """
        if 'sale.order' not in self.env:
            self.skipTest("sale addon not installed in this profile")
        Order = self.env['sale.order']
        partner = self._a_partner()
        product = self._a_product()
        self.env.flush_all()

        # -- POST (create) -> ORM create, HTTP 200 with the Read body -------
        resp = self._post('/api/v1/sale-orders', {'partner_id': partner.id})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn('id', body)
        oid = body['id']
        self.env.invalidate_all()
        order = Order.browse(oid)
        self.assertTrue(order.exists(), "POST must have created the sale.order")
        self.assertEqual(order.partner_id.id, partner.id)

        # -- GET item (read) ------------------------------------------------
        resp = self._get('/api/v1/sale-orders/%d' % oid)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()['id'], oid)

        # -- GET collection (search_read + search_count) --------------------
        resp = self._get(
            '/api/v1/sale-orders',
            params={'domain': json.dumps([['id', '=', oid]])},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self._assert_collection_body(resp.json(), oid)

        # -- PATCH (write) a scalar field -----------------------------------
        resp = self._patch(
            '/api/v1/sale-orders/%d' % oid, {'client_order_ref': 'REF-1'},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json().get('client_order_ref'), 'REF-1')

        # -- x2many replace/clear on order_line -----------------------------
        # Seed two lines through the ORM (products make them real lines), then
        # flush so the HTTP worker observes them before the PATCHes.
        order.write({'order_line': [
            Command.create({'product_id': product.id, 'product_uom_qty': 1}),
            Command.create({'product_id': product.id, 'product_uom_qty': 2}),
        ]})
        self.env.flush_all()
        self.assertEqual(len(order.order_line), 2)
        self._assert_xmany_replace_and_clear(
            '/api/v1/sale-orders', order, 'order_line', order.order_line.ids,
        )

        # -- DELETE (unlink) -> HTTP 204, empty body ------------------------
        resp = self._delete('/api/v1/sale-orders/%d' % oid)
        self.assertEqual(resp.status_code, 204, resp.text)
        self.assertEqual(resp.text, '')
        self.env.invalidate_all()
        self.assertFalse(
            Order.browse(oid).exists(),
            "DELETE must have unlinked the sale.order",
        )

    # ------------------------------------------------------------------
    # account.move -- full lifecycle + invoice_line_ids x2many replace/clear.
    # ------------------------------------------------------------------
    def test_account_move_full_crud_lifecycle(self):
        """POST -> GET(id) -> GET(collection) -> PATCH -> x2many -> DELETE.

        Strict in the expected install profile: skips only if ``account`` is not
        installed. Proves every verb -> ORM mapping for ``account.move`` and the
        ``invoice_line_ids`` full-list replace/clear semantics on a draft
        customer invoice.
        """
        if 'account.move' not in self.env:
            self.skipTest("account addon not installed in this profile")
        Move = self.env['account.move']
        partner = self._a_partner()
        product = self._a_product()
        self.env.flush_all()

        # -- POST (create) a draft customer invoice -------------------------
        resp = self._post(
            '/api/v1/account-moves',
            {'move_type': 'out_invoice', 'partner_id': partner.id},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn('id', body)
        mid = body['id']
        self.env.invalidate_all()
        move = Move.browse(mid)
        self.assertTrue(move.exists(), "POST must have created the account.move")
        self.assertEqual(move.move_type, 'out_invoice')

        # -- GET item -------------------------------------------------------
        resp = self._get('/api/v1/account-moves/%d' % mid)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()['id'], mid)

        # -- GET collection -------------------------------------------------
        resp = self._get(
            '/api/v1/account-moves',
            params={'domain': json.dumps([['id', '=', mid]])},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self._assert_collection_body(resp.json(), mid)

        # -- PATCH a scalar field -------------------------------------------
        resp = self._patch('/api/v1/account-moves/%d' % mid, {'ref': 'CRUD-REF'})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json().get('ref'), 'CRUD-REF')

        # -- x2many replace/clear on invoice_line_ids -----------------------
        move.write({'invoice_line_ids': [
            Command.create(
                {'product_id': product.id, 'quantity': 1, 'price_unit': 100},
            ),
            Command.create(
                {'product_id': product.id, 'quantity': 2, 'price_unit': 50},
            ),
        ]})
        self.env.flush_all()
        self.assertEqual(len(move.invoice_line_ids), 2)
        self._assert_xmany_replace_and_clear(
            '/api/v1/account-moves', move, 'invoice_line_ids',
            move.invoice_line_ids.ids,
        )

        # -- DELETE ---------------------------------------------------------
        resp = self._delete('/api/v1/account-moves/%d' % mid)
        self.assertEqual(resp.status_code, 204, resp.text)
        self.assertEqual(resp.text, '')
        self.env.invalidate_all()
        self.assertFalse(
            Move.browse(mid).exists(),
            "DELETE must have unlinked the account.move",
        )

    # ------------------------------------------------------------------
    # stock.picking -- full lifecycle + move_ids x2many replace/clear.
    # ------------------------------------------------------------------
    def test_stock_picking_full_crud_lifecycle(self):
        """POST -> GET(id) -> GET(collection) -> PATCH -> x2many -> DELETE.

        Strict in the expected install profile: skips only if ``stock`` is not
        installed. Proves every verb -> ORM mapping for ``stock.picking`` and the
        ``move_ids`` full-list replace/clear semantics on a draft transfer.
        """
        if 'stock.picking' not in self.env:
            self.skipTest("stock addon not installed in this profile")
        Picking = self.env['stock.picking']
        picking_type = self.env['stock.picking.type'].search([], limit=1)
        self.assertTrue(picking_type, "a stock.picking.type is required")
        product = self._a_product()
        self.env.flush_all()

        # -- POST (create) --------------------------------------------------
        resp = self._post(
            '/api/v1/stock-pickings', {'picking_type_id': picking_type.id},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn('id', body)
        pkid = body['id']
        self.env.invalidate_all()
        picking = Picking.browse(pkid)
        self.assertTrue(
            picking.exists(), "POST must have created the stock.picking",
        )

        # -- GET item -------------------------------------------------------
        resp = self._get('/api/v1/stock-pickings/%d' % pkid)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()['id'], pkid)

        # -- GET collection -------------------------------------------------
        resp = self._get(
            '/api/v1/stock-pickings',
            params={'domain': json.dumps([['id', '=', pkid]])},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self._assert_collection_body(resp.json(), pkid)

        # -- PATCH a scalar field -------------------------------------------
        resp = self._patch(
            '/api/v1/stock-pickings/%d' % pkid, {'origin': 'CRUD-ORIGIN'},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json().get('origin'), 'CRUD-ORIGIN')

        # -- x2many replace/clear on move_ids -------------------------------
        # ``stock.move`` has no ``name`` field in Odoo 19
        # (``_rec_name='reference'``); the locations come from the picking.
        picking.write({'move_ids': [
            Command.create({
                'product_id': product.id, 'product_uom_qty': 1,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
            }),
            Command.create({
                'product_id': product.id, 'product_uom_qty': 2,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
            }),
        ]})
        self.env.flush_all()
        self.assertEqual(len(picking.move_ids), 2)
        self._assert_xmany_replace_and_clear(
            '/api/v1/stock-pickings', picking, 'move_ids', picking.move_ids.ids,
        )

        # -- DELETE ---------------------------------------------------------
        resp = self._delete('/api/v1/stock-pickings/%d' % pkid)
        self.assertEqual(resp.status_code, 204, resp.text)
        self.assertEqual(resp.text, '')
        self.env.invalidate_all()
        self.assertFalse(
            Picking.browse(pkid).exists(),
            "DELETE must have unlinked the stock.picking",
        )

    # ------------------------------------------------------------------
    # crm.lead -- full lifecycle (no x2many write DTO field).
    # ------------------------------------------------------------------
    def test_crm_lead_full_crud_lifecycle(self):
        """POST -> GET(id) -> GET(collection) -> PATCH -> DELETE.

        Strict in the expected install profile: skips only if ``crm`` is not
        installed. ``crm.lead`` exposes no x2many write field, so this proves the
        scalar verb -> ORM mappings only.
        """
        if 'crm.lead' not in self.env:
            self.skipTest("crm addon not installed in this profile")
        Lead = self.env['crm.lead']

        # -- POST (create) --------------------------------------------------
        resp = self._post(
            '/api/v1/crm-leads', {'name': 'CRUD Lead', 'type': 'lead'},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn('id', body)
        self.assertEqual(body['name'], 'CRUD Lead')
        lid = body['id']
        self.env.invalidate_all()
        lead = Lead.browse(lid)
        self.assertTrue(lead.exists(), "POST must have created the crm.lead")
        self.assertEqual(lead.name, 'CRUD Lead')

        # -- GET item -------------------------------------------------------
        resp = self._get('/api/v1/crm-leads/%d' % lid)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()['id'], lid)

        # -- GET collection -------------------------------------------------
        resp = self._get(
            '/api/v1/crm-leads',
            params={'domain': json.dumps([['id', '=', lid]])},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self._assert_collection_body(resp.json(), lid)

        # -- PATCH (write) --------------------------------------------------
        resp = self._patch('/api/v1/crm-leads/%d' % lid, {'name': 'CRUD Lead v2'})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json().get('name'), 'CRUD Lead v2')

        # -- DELETE (unlink) ------------------------------------------------
        resp = self._delete('/api/v1/crm-leads/%d' % lid)
        self.assertEqual(resp.status_code, 204, resp.text)
        self.assertEqual(resp.text, '')
        self.env.invalidate_all()
        self.assertFalse(
            Lead.browse(lid).exists(), "DELETE must have unlinked the crm.lead",
        )
