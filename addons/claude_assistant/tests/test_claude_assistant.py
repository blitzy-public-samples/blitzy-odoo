# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Automated test suite for the ``claude_assistant`` Odoo 19.0 addon.

This module defines EXACTLY THREE test classes / TEN test methods, all carrying
the ``claude_assistant`` tag so ``--test-tags claude_assistant`` selects the
whole suite:

* :class:`ClaudeAssistantControllerTest` (``HttpCase``, 7 methods) -- exercises
  every branch of ``POST /claude_assistant/chat``.
* :class:`ClaudeAssistantStatusTest` (``HttpCase``, 2 methods) -- exercises
  ``GET /claude_assistant/status``.
* :class:`ClaudeAssistantConfigTest` (``TransactionCase``, 1 method) -- verifies
  the settings API-key field round-trips through ``ir.config_parameter``.

The outbound Anthropic Messages API call is ALWAYS mocked: the tests patch the
``anthropic.Anthropic`` client class (never the module), so the controller's
``except anthropic.<...>Error`` clauses keep matching the SDK's REAL exception
classes while no real network call is ever made. A clearly fake dummy key is
used everywhere -- no real credential is referenced, asserted, or logged -- and
the ``/status`` test additionally guards against the key value leaking into the
response body.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import anthropic

import odoo.release
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged

# An OBVIOUSLY fake test credential -- never a real Anthropic key. It is set as
# the config parameter only inside the in-process test transaction and must
# never appear in any response body (asserted by the /status leak guard).
DUMMY_API_KEY = 'sk-ant-test-DUMMY-DO-NOT-USE'

# The two routes under test.
CHAT_URL = '/claude_assistant/chat'
STATUS_URL = '/claude_assistant/status'

# The ir.config_parameter key bound by models/res_config_settings.py and read by
# the controller. Seeded EMPTY at install, so 503 ("API key not configured") is
# the default /chat outcome until a key is set.
API_KEY_PARAM = 'claude_assistant.api_key'


def _fake_response(text='Hello from Claude'):
    """Build a minimal stand-in for an Anthropic Messages API response.

    The controller reads ``response.content[0].text`` and then serializes the
    result through ``request.make_json_response`` (i.e. ``json.dumps``). Real
    Python strings -- not ``Mock`` attributes -- are therefore required, so we
    use :class:`types.SimpleNamespace` to mirror the ``.content[0].text`` access
    path with a genuine ``str``.
    """
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


@tagged('post_install', '-at_install', 'claude_assistant')
class ClaudeAssistantControllerTest(HttpCase):
    """Behavioral tests for ``POST /claude_assistant/chat``.

    Every outcome of the controller's fixed nine-step sequence is asserted
    against its REAL HTTP status code and FLAT JSON body. Because the route is
    declared ``type='json'`` (the Odoo 19 jsonrpc alias) and delivers each
    outcome via ``abort(make_json_response(..., status=<code>))``, the body is
    parsed directly from ``response.json()`` and the code from
    ``response.status_code`` (NOT from a JSON-RPC envelope).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Handle for setting/clearing the API key parameter inside the test txn.
        cls.ICP = cls.env['ir.config_parameter']
        # A plain internal user (base.group_user) who LACKS base.group_system --
        # used to prove the 403 authorization branch for an admin-only mode.
        cls.business_user = new_test_user(
            cls.env, login='claude_biz', password='claude_biz_pw',
            groups='base.group_user',
        )
        # A developer: internal user PLUS the addon's developer group, used to
        # prove developer-mode authorization and the 2048 max_tokens path.
        cls.dev_user = new_test_user(
            cls.env, login='claude_dev', password='claude_dev_pw',
            groups='base.group_user,claude_assistant.group_developer',
        )

    def _post_chat(self, params):
        """POST ``params`` to /chat as a jsonrpc body.

        ``type='json'`` routes require ``Content-Type: application/json`` and
        read named arguments from the request body's ``params`` object, so the
        payload is wrapped as ``{'params': {...}}``. No csrf_token is needed:
        jsonrpc routes do not validate it.
        """
        return self.url_open(
            CHAT_URL,
            headers={'Content-Type': 'application/json'},
            data=json.dumps({'params': params}),
        )

    def test_chat_invalid_mode_returns_400(self):
        """Invalid ``mode`` short-circuits at step 1 with a clean HTTP 400.

        Exercises every invalid shape: an unknown string, an omitted mode
        (defaults to ``None``), and the two NON-STRING, UNHASHABLE payloads a
        direct JSON-RPC client can send -- a JSON array (``list``) and a JSON
        object (``dict``). The list/dict cases are the regression guard for the
        ``isinstance(mode, str)`` check: before it, ``mode not in
        MODE_AUTHORIZATION`` raised ``TypeError: unhashable type`` and Odoo
        wrapped it into a 200 JSON-RPC server-error envelope (with a debug
        traceback under --dev) instead of the required flat 400. Every case
        MUST return HTTP 400 with the flat body ``{'error': 'Invalid mode'}``
        and the Anthropic SDK MUST never be constructed (return precedes step 7).
        """
        self.authenticate('admin', 'admin')
        # Patch the client purely to assert the SDK is never constructed -- an
        # invalid mode must return before step 7.
        with patch('anthropic.Anthropic') as MockAnthropic:
            responses = [
                self._post_chat({'mode': 'not_a_real_mode', 'messages': []}),
                # ``mode`` omitted entirely -> defaults to None -> still invalid.
                self._post_chat({'messages': []}),
                # Non-string unhashable payloads: must NOT raise TypeError, must
                # be rejected cleanly as an invalid mode (HTTP 400).
                self._post_chat({'mode': [], 'messages': []}),
                self._post_chat({'mode': {}, 'messages': []}),
            ]
        for resp in responses:
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(resp.json(), {'error': 'Invalid mode'})
        MockAnthropic.assert_not_called()

    def test_chat_unauthorized_mode_returns_403(self):
        """A user lacking the mode's group is rejected at step 2 with HTTP 403."""
        self.authenticate('claude_biz', 'claude_biz_pw')
        # Set the key FIRST so the only possible failure is the group check
        # (step 2 precedes the key read at step 3): this proves 403, not 503.
        self.ICP.sudo().set_param(API_KEY_PARAM, DUMMY_API_KEY)
        with patch('anthropic.Anthropic') as MockAnthropic:
            resp = self._post_chat(
                {'mode': 'modules', 'messages': [{'role': 'user', 'content': 'hi'}]}
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json(), {'error': 'Forbidden'})
        MockAnthropic.assert_not_called()

    def test_chat_api_key_not_configured_returns_503(self):
        """An empty key short-circuits at step 3 with HTTP 503 (no SDK call)."""
        self.authenticate('admin', 'admin')
        # Force the parameter empty -> get_param() returns False -> 503.
        self.ICP.sudo().set_param(API_KEY_PARAM, '')
        with patch('anthropic.Anthropic') as MockAnthropic:
            resp = self._post_chat(
                {'mode': 'modules', 'messages': [{'role': 'user', 'content': 'hi'}]}
            )
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json(), {'response': None, 'error': 'API key not configured'})
        MockAnthropic.return_value.messages.create.assert_not_called()

    def test_chat_happy_path_returns_200(self):
        """A fully authorized, configured request relays to the SDK and returns 200."""
        self.authenticate('admin', 'admin')
        self.ICP.sudo().set_param(API_KEY_PARAM, DUMMY_API_KEY)
        with patch('anthropic.Anthropic') as MockAnthropic:
            client = MockAnthropic.return_value
            client.messages.create.return_value = _fake_response('Hello from Claude')
            resp = self._post_chat({
                'mode': 'modules',
                'messages': [{'role': 'user', 'content': 'How do I install a module?'}],
            })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'response': 'Hello from Claude', 'error': None})
        # The client is constructed exactly once, with the 28-second transport
        # timeout, and the Messages API is called once with the pinned model.
        MockAnthropic.assert_called_once()
        self.assertEqual(MockAnthropic.call_args.kwargs.get('timeout'), 28)
        client.messages.create.assert_called_once()
        self.assertEqual(client.messages.create.call_args.kwargs['model'], 'claude-sonnet-4-6')

    def test_chat_truncates_history_to_last_10(self):
        """Conversation history is truncated to the LAST 10 messages (step 6)."""
        self.authenticate('admin', 'admin')
        self.ICP.sudo().set_param(API_KEY_PARAM, DUMMY_API_KEY)
        # 15 ordered messages; only msg5..msg14 (the last 10) must be forwarded.
        msgs = [{'role': 'user', 'content': 'msg%d' % i} for i in range(15)]
        with patch('anthropic.Anthropic') as MockAnthropic:
            client = MockAnthropic.return_value
            client.messages.create.return_value = _fake_response()
            # 'sales' is a base.group_user mode; admin holds base.group_user.
            resp = self._post_chat({'mode': 'sales', 'messages': msgs})
        self.assertEqual(resp.status_code, 200)
        sent = client.messages.create.call_args.kwargs['messages']
        self.assertEqual(len(sent), 10)
        self.assertEqual(sent[0]['content'], 'msg5')
        self.assertEqual(sent[-1]['content'], 'msg14')

    def test_chat_maps_sdk_exceptions(self):
        """Each SDK exception type maps to its prescribed HTTP status (step 8).

        Every Anthropic error subclasses ``anthropic.APIError``; the controller
        orders its ``except`` clauses specific->generic (Authentication, Rate,
        Connection, then APIError). Hence ``APITimeoutError`` (a subclass of
        ``APIConnectionError``) maps to 504 and a generic ``APIError`` falls
        through to 502. Typed instances are raised via ``__new__`` to avoid
        constructing the SDK's httpx request/response arguments -- the instance
        is still catchable by type.
        """
        self.authenticate('admin', 'admin')
        self.ICP.sudo().set_param(API_KEY_PARAM, DUMMY_API_KEY)
        cases = [
            (anthropic.AuthenticationError, 401),
            (anthropic.RateLimitError, 429),
            (anthropic.APITimeoutError, 504),  # subclass of APIConnectionError
            (anthropic.APIError, 502),         # generic catch-all
        ]
        for exc_class, expected_status in cases:
            with self.subTest(exc=exc_class.__name__):
                with patch('anthropic.Anthropic') as MockAnthropic:
                    MockAnthropic.return_value.messages.create.side_effect = \
                        exc_class.__new__(exc_class)
                    resp = self._post_chat(
                        {'mode': 'sales', 'messages': [{'role': 'user', 'content': 'hi'}]}
                    )
                self.assertEqual(resp.status_code, expected_status)
                body = resp.json()
                self.assertIsNone(body['response'])
                # A non-empty, non-sensitive error string is surfaced.
                self.assertTrue(body['error'])
                self.assertNotIn(DUMMY_API_KEY, resp.text)

    def test_chat_developer_mode_uses_max_tokens_2048(self):
        """Developer modes use max_tokens=2048; the developer group authorizes them."""
        self.authenticate('claude_dev', 'claude_dev_pw')
        self.ICP.sudo().set_param(API_KEY_PARAM, DUMMY_API_KEY)
        with patch('anthropic.Anthropic') as MockAnthropic:
            client = MockAnthropic.return_value
            client.messages.create.return_value = _fake_response()
            resp = self._post_chat({
                'mode': 'module_dev',
                'messages': [{'role': 'user', 'content': 'scaffold a model'}],
            })
        self.assertEqual(resp.status_code, 200)
        # Developer modes raise the token budget to 2048 (all others use 1024).
        # Reaching 200 also confirms the module_dev context builder (reading the
        # always-present ir.module.module while optional crm/sale/etc. models are
        # absent and silently skipped) does not error.
        self.assertEqual(client.messages.create.call_args.kwargs['max_tokens'], 2048)


@tagged('post_install', '-at_install', 'claude_assistant')
class ClaudeAssistantStatusTest(HttpCase):
    """Behavioral tests for ``GET /claude_assistant/status``.

    Unlike /chat, /status returns a PLAIN dict, so the jsonrpc dispatcher wraps
    it in the standard ``{'jsonrpc': '2.0', 'id': ..., 'result': {...}}``
    envelope at HTTP 200. The actual status payload is therefore read from
    ``response.json()['result']``.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP = cls.env['ir.config_parameter']
        # A plain internal user is needed to assert that a non-admin sees only
        # the Business role.
        cls.business_user = new_test_user(
            cls.env, login='claude_biz', password='claude_biz_pw',
            groups='base.group_user',
        )

    def _get_status(self):
        """Invoke /status as a jsonrpc call and return the raw HTTP response."""
        return self.url_open(
            STATUS_URL,
            headers={'Content-Type': 'application/json'},
            data=json.dumps({'params': {}}),
        )

    def test_status_reports_api_key_and_version(self):
        """``api_key_configured`` reflects the key; ``odoo_version`` matches the
        framework; and the key value never leaks into the body."""
        self.authenticate('admin', 'admin')

        # (a) Key absent -> api_key_configured is False; version is the live one.
        self.ICP.sudo().set_param(API_KEY_PARAM, '')
        resp = self._get_status()
        self.assertEqual(resp.status_code, 200)
        result = resp.json()['result']  # unwrap the jsonrpc envelope
        self.assertIs(result['api_key_configured'], False)
        # Compare to the framework's own value rather than hardcoding '19.0'.
        self.assertEqual(result['odoo_version'], odoo.release.version)

        # (b) Key set -> api_key_configured is True, but the value must NOT leak.
        self.ICP.sudo().set_param(API_KEY_PARAM, DUMMY_API_KEY)
        resp2 = self._get_status()
        result2 = resp2.json()['result']
        self.assertIs(result2['api_key_configured'], True)
        # Leak guard: the key value must NEVER appear in the /status body.
        self.assertNotIn(DUMMY_API_KEY, resp2.text)

    def test_status_user_roles_reflect_groups(self):
        """``user_roles`` lists exactly the roles the user is authorized for, in
        the canonical order, exposing only id/label/modes."""
        # (a) Admin holds base.group_system, which natively implies
        # base.group_user, so the admin is authorized for BOTH the Admin and
        # Business roles -- and NOT developer/partner (those have no members).
        self.authenticate('admin', 'admin')
        result = self._get_status().json()['result']
        role_ids = [r['id'] for r in result['user_roles']]
        self.assertEqual(role_ids, ['admin', 'business'])
        for role in result['user_roles']:
            # Only the public shape is exposed; internal keys are withheld.
            self.assertEqual(set(role.keys()), {'id', 'label', 'modes'})
            self.assertNotIn('group', role)
            self.assertNotIn('category', role)
            self.assertIsInstance(role['modes'], list)
            for mode in role['modes']:
                self.assertEqual(set(mode.keys()), {'id', 'label'})

        # (b) A plain internal user sees only the Business role.
        self.authenticate('claude_biz', 'claude_biz_pw')
        result_b = self._get_status().json()['result']
        self.assertEqual([r['id'] for r in result_b['user_roles']], ['business'])


@tagged('post_install', '-at_install', 'claude_assistant')
class ClaudeAssistantConfigTest(TransactionCase):
    """Verifies the ``res.config.settings`` field round-trips through the
    ``ir.config_parameter`` store. No HTTP layer and no fixture users needed."""

    def test_api_key_config_parameter_roundtrip(self):
        """Writing the bound field persists the parameter and reads back."""
        ICP = self.env['ir.config_parameter'].sudo()
        # Writing through the settings model + set_values() persists the
        # config_parameter-bound field to ir.config_parameter.
        settings = self.env['res.config.settings'].create({
            'claude_assistant_api_key': DUMMY_API_KEY,
        })
        settings.set_values()
        self.assertEqual(ICP.get_param(API_KEY_PARAM), DUMMY_API_KEY)
        # A fresh settings record reads the stored parameter back via default_get.
        reread = self.env['res.config.settings'].create({})
        self.assertEqual(reread.claude_assistant_api_key, DUMMY_API_KEY)
