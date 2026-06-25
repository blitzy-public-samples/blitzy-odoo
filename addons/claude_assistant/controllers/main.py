# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

import anthropic
import werkzeug.exceptions

import odoo.release
from odoo import http
from odoo.http import request, route

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Table-driven authorization / role metadata (module-level constants).
#
# These tables are the single source of truth for the controller. They are
# intentionally fixed and exhaustive: the set of valid modes is EXACTLY the 15
# keys of ``MODE_AUTHORIZATION``. No mode, role, group, or field beyond these
# is declared anywhere in this addon's server layer.
# ---------------------------------------------------------------------------

# Mode id -> (required security group external id, Anthropic max_tokens).
# The two non-native group external ids (claude_assistant.group_developer and
# claude_assistant.group_partner) are defined by the sibling
# ``security/claude_assistant_security.xml`` (records ``group_developer`` and
# ``group_partner``). base.group_system and base.group_user are native Odoo
# groups (see odoo/addons/base/security/base_groups.xml).
MODE_AUTHORIZATION = {
    # Admin modes -> base.group_system, 1024
    'modules':         ('base.group_system', 1024),
    'users':           ('base.group_system', 1024),
    'config':          ('base.group_system', 1024),
    'troubleshooting': ('base.group_system', 1024),
    # Business modes -> base.group_user, 1024
    'sales':           ('base.group_user', 1024),
    'accounting':      ('base.group_user', 1024),
    'hr':              ('base.group_user', 1024),
    'operations':      ('base.group_user', 1024),
    # Developer modes -> claude_assistant.group_developer, 2048
    'module_dev':      ('claude_assistant.group_developer', 2048),
    'integration':     ('claude_assistant.group_developer', 2048),
    'debugging':       ('claude_assistant.group_developer', 2048),
    'testing':         ('claude_assistant.group_developer', 2048),
    # Partner modes -> claude_assistant.group_partner, 1024
    'deployment':      ('claude_assistant.group_partner', 1024),
    'customization':   ('claude_assistant.group_partner', 1024),
    'client_support':  ('claude_assistant.group_partner', 1024),
}

# Role category -> verbatim system-prompt role statement. These strings are
# copied character-for-character from the feature specification and MUST NOT be
# paraphrased or re-punctuated.
ROLE_STATEMENTS = {
    'admin':     "You are assisting an Odoo System Administrator responsible for deployment, configuration, user management, and system maintenance.",
    'business':  "You are assisting an Odoo Business User. Provide practical guidance for day-to-day operations, data entry, and reporting. Avoid deep technical implementation details.",
    'developer': "You are assisting an Odoo Developer building custom modules and integrations. Provide technical ORM patterns, module architecture guidance, and implementation examples specific to Odoo 19.0.",
    'partner':   "You are assisting an Odoo Implementation Partner. Provide deployment, customization, and client support guidance aligned with Odoo 19.0 best practices.",
}

# Ordered role definitions (admin, business, developer, partner). Consumed by
# ``/claude_assistant/status`` to drive the panel's role selector and mode tabs,
# and used to derive a mode's role category for the system prompt. Each entry
# carries an authorizing ``group`` (external id), a ``category`` key into
# ``ROLE_STATEMENTS``, and an ordered list of ``modes`` ({id, label}).
ROLES = [
    {
        'id': 'admin',
        'label': 'System Administrators',
        'group': 'base.group_system',
        'category': 'admin',
        'modes': [
            {'id': 'modules', 'label': 'Modules'},
            {'id': 'users', 'label': 'Users & Access'},
            {'id': 'config', 'label': 'System Config'},
            {'id': 'troubleshooting', 'label': 'Troubleshooting'},
        ],
    },
    {
        'id': 'business',
        'label': 'Business Users',
        'group': 'base.group_user',
        'category': 'business',
        'modes': [
            {'id': 'sales', 'label': 'Sales'},
            {'id': 'accounting', 'label': 'Accounting'},
            {'id': 'hr', 'label': 'HR'},
            {'id': 'operations', 'label': 'Operations'},
        ],
    },
    {
        'id': 'developer',
        'label': 'Developers',
        'group': 'claude_assistant.group_developer',
        'category': 'developer',
        'modes': [
            {'id': 'module_dev', 'label': 'Module Dev'},
            {'id': 'integration', 'label': 'Integrations'},
            {'id': 'debugging', 'label': 'Debugging'},
            {'id': 'testing', 'label': 'Testing'},
        ],
    },
    {
        'id': 'partner',
        'label': 'Partners & Integrators',
        'group': 'claude_assistant.group_partner',
        'category': 'partner',
        'modes': [
            {'id': 'deployment', 'label': 'Deployment'},
            {'id': 'customization', 'label': 'Customization'},
            {'id': 'client_support', 'label': 'Client Support'},
        ],
    },
]

# Derived lookup: mode id -> role category (key into ROLE_STATEMENTS). Built
# from ROLES so the union of all role modes is, by construction, exactly the
# set of MODE_AUTHORIZATION keys.
MODE_TO_CATEGORY = {m['id']: role['category'] for role in ROLES for m in role['modes']}


# ---------------------------------------------------------------------------
# Response helper.
# ---------------------------------------------------------------------------

def _json_status(body, status):
    """Deliver a REAL HTTP status code + FLAT JSON body from a ``type='json'``
    (jsonrpc) route, bypassing the JSON-RPC envelope.

    ``request.make_json_response`` builds an Odoo ``Response``; the
    odoo/http.py-patched ``werkzeug.exceptions.abort`` accepts that Response,
    unwraps it and raises an ``HTTPException`` whose ``code`` is ``None``.
    ``Application.__call__`` detects ``code is None`` and returns the Response
    VERBATIM (its real status + flat body), bypassing BOTH the JSON-RPC
    envelope and the dispatcher's ``handle_error`` (which would otherwise wrap
    everything into a 200 envelope). This mirrors the framework's own pattern:
    the JSON-RPC dispatcher itself uses ``abort(Response(..., status=400))`` for
    malformed input.

    NOTE: this helper NEVER returns normally -- ``abort`` always raises.
    """
    werkzeug.exceptions.abort(request.make_json_response(body, status=status))


# ---------------------------------------------------------------------------
# Per-mode context builders.
#
# Each builder assembles a small, fast (<500ms target), human-readable context
# string from live ORM reads. Hard rules honored throughout:
#   * Every read uses ``.sudo()`` with an EXPLICIT ``fields=[...]`` list plus a
#     ``limit`` (and ``order`` where meaningful) -- never a full-record read.
#   * OPTIONAL feature-addon models (owned by addons that may not be installed,
#     since this addon depends only on ['base', 'web']) are guarded with
#     ``if '<model>' in request.env:`` and silently omitted when absent.
#   * ``ir.config_parameter`` is read with the ``key`` field ONLY -- NEVER the
#     ``value`` field -- so secrets (e.g. claude_assistant.api_key) cannot leak
#     into the context/system prompt.
#   * The api_key value is never read, returned, logged, or embedded here.
# ---------------------------------------------------------------------------

# Optional feature-addon models that MUST be guarded with ``in request.env``
# before use (documented here for clarity; each builder applies the guard).
# crm.lead, sale.order, account.move, account.payment, hr.employee, hr.leave,
# hr.leave.allocation, stock.picking, purchase.order.

_NO_CONTEXT = "No additional context available."


def _ctx_installed_modules(env, limit=80):
    """Installed modules with a total count (always-present ``ir.module.module``)."""
    total = env['ir.module.module'].sudo().search_count([('state', '=', 'installed')])
    mods = env['ir.module.module'].sudo().search_read(
        [('state', '=', 'installed')], ['name', 'shortdesc'], limit=limit,
    )
    if not mods:
        return "No installed modules found."
    lines = ["Installed modules (total %s, showing %s):" % (total, len(mods))]
    for mod in mods:
        desc = (mod.get('shortdesc') or '').strip()
        name = mod.get('name') or ''
        lines.append("- %s: %s" % (name, desc) if desc else "- %s" % name)
    return "\n".join(lines)


def _ctx_recent_logs(env, limit=10):
    """Most recent server log entries (always-present ``ir.logging``)."""
    logs = env['ir.logging'].sudo().search_read(
        [], ['name', 'message', 'path', 'line', 'level', 'create_date'],
        order='create_date desc', limit=limit,
    )
    if not logs:
        return "No recent log entries found."
    lines = ["Recent log entries (most recent first):"]
    for log in logs:
        message = (log.get('message') or '').strip()
        first_line = message.splitlines()[0][:200] if message else ''
        lines.append("- [%s] %s %s (%s:%s): %s" % (
            log.get('level') or '',
            log.get('create_date') or '',
            log.get('name') or '',
            log.get('path') or '',
            log.get('line') or '',
            first_line,
        ))
    return "\n".join(lines)


def _ctx_config_keys(env, limit=80):
    """System configuration parameter KEYS only (always-present ``ir.config_parameter``).

    SECURITY: this reads the ``key`` field exclusively. The ``value`` field is
    NEVER read here -- doing so would surface secrets such as
    ``claude_assistant.api_key`` into the assistant context.
    """
    params = env['ir.config_parameter'].sudo().search_read([], ['key'], limit=limit)
    keys = [p['key'] for p in params if p.get('key')]
    if not keys:
        return "No system configuration parameters found."
    return ("System configuration parameter keys (values intentionally omitted):\n"
            + "\n".join("- %s" % key for key in keys))


# --- Admin modes -----------------------------------------------------------

def _build_modules(env):
    return _ctx_installed_modules(env, limit=80)


def _build_users(env):
    user_count = env['res.users'].sudo().search_count([])
    group_count = env['res.groups'].sudo().search_count([])
    users = env['res.users'].sudo().search_read([], ['login', 'name'], limit=20)
    lines = [
        "Total users: %s" % user_count,
        "Total security groups: %s" % group_count,
        "Sample users:",
    ]
    for user in users:
        lines.append("- %s <%s>" % (user.get('name') or '', user.get('login') or ''))
    return "\n".join(lines)


def _build_config(env):
    return _ctx_config_keys(env, limit=80)


def _build_troubleshooting(env):
    return _ctx_recent_logs(env, limit=10)


# --- Business modes (optional feature-addon models -> guarded) --------------

def _build_sales(env):
    blocks = []
    if 'sale.order' in env:
        order_count = env['sale.order'].sudo().search_count([])
        orders = env['sale.order'].sudo().search_read(
            [], ['name', 'amount_total', 'state'], limit=10, order='create_date desc',
        )
        block = ["Sales orders (total %s, latest %s):" % (order_count, len(orders))]
        for order in orders:
            block.append("- %s: total=%s state=%s" % (
                order.get('name') or '', order.get('amount_total'), order.get('state') or '',
            ))
        blocks.append("\n".join(block))
    if 'crm.lead' in env:
        lead_count = env['crm.lead'].sudo().search_count([])
        blocks.append("CRM leads/opportunities: %s" % lead_count)
    if not blocks:
        return "No sales data available (sale/crm modules not installed)."
    return "\n\n".join(blocks)


def _build_accounting(env):
    blocks = []
    if 'account.move' in env:
        moves = env['account.move'].sudo().search_read(
            [], ['name', 'move_type', 'amount_total', 'state'], limit=10, order='create_date desc',
        )
        block = ["Recent journal entries (%s):" % len(moves)]
        for move in moves:
            block.append("- %s: type=%s total=%s state=%s" % (
                move.get('name') or '', move.get('move_type') or '',
                move.get('amount_total'), move.get('state') or '',
            ))
        blocks.append("\n".join(block))
    if 'account.payment' in env:
        payment_count = env['account.payment'].sudo().search_count([])
        blocks.append("Payments recorded: %s" % payment_count)
    if not blocks:
        return "No accounting data available (account module not installed)."
    return "\n\n".join(blocks)


def _build_hr(env):
    blocks = []
    if 'hr.employee' in env:
        employee_count = env['hr.employee'].sudo().search_count([])
        employees = env['hr.employee'].sudo().search_read([], ['name'], limit=10)
        block = ["Employees (total %s, sample %s):" % (employee_count, len(employees))]
        for employee in employees:
            block.append("- %s" % (employee.get('name') or ''))
        blocks.append("\n".join(block))
    if 'hr.leave' in env:
        leave_count = env['hr.leave'].sudo().search_count([])
        blocks.append("Time-off requests: %s" % leave_count)
    if 'hr.leave.allocation' in env:
        allocation_count = env['hr.leave.allocation'].sudo().search_count([])
        blocks.append("Leave allocations: %s" % allocation_count)
    if not blocks:
        return "No HR data available (hr modules not installed)."
    return "\n\n".join(blocks)


def _build_operations(env):
    blocks = []
    if 'stock.picking' in env:
        pickings = env['stock.picking'].sudo().search_read(
            [], ['name', 'state'], limit=10, order='create_date desc',
        )
        block = ["Recent stock transfers (%s):" % len(pickings)]
        for picking in pickings:
            block.append("- %s: state=%s" % (picking.get('name') or '', picking.get('state') or ''))
        blocks.append("\n".join(block))
    if 'purchase.order' in env:
        purchases = env['purchase.order'].sudo().search_read(
            [], ['name', 'state'], limit=10, order='create_date desc',
        )
        block = ["Recent purchase orders (%s):" % len(purchases)]
        for purchase in purchases:
            block.append("- %s: state=%s" % (purchase.get('name') or '', purchase.get('state') or ''))
        blocks.append("\n".join(block))
    if not blocks:
        return "No operations data available (stock/purchase modules not installed)."
    return "\n\n".join(blocks)


# --- Developer modes -------------------------------------------------------

def _build_module_dev(env):
    return _ctx_installed_modules(env, limit=80)


def _build_integration(env):
    # Installed modules plus configuration parameter KEYS (never values).
    return "%s\n\n%s" % (_ctx_installed_modules(env, limit=80), _ctx_config_keys(env, limit=80))


def _build_debugging(env):
    return _ctx_recent_logs(env, limit=10)


def _build_testing(env):
    return _ctx_installed_modules(env, limit=80)


# --- Partner modes ---------------------------------------------------------

def _build_deployment(env):
    base_url = env['ir.config_parameter'].sudo().get_param('web.base.url')
    installed = env['ir.module.module'].sudo().search_count([('state', '=', 'installed')])
    return (
        "Odoo version: %s\n"
        "Instance URL: %s\n"
        "Installed modules: %s" % (odoo.release.version, base_url or '(not set)', installed)
    )


def _build_customization(env):
    return _ctx_installed_modules(env, limit=60)


def _build_client_support(env):
    partner_count = env['res.partner'].sudo().search_count([])
    partners = env['res.partner'].sudo().search_read([], ['name'], limit=20)
    lines = ["Contacts/partners (total %s, sample %s):" % (partner_count, len(partners))]
    for partner in partners:
        lines.append("- %s" % (partner.get('name') or ''))
    return "\n".join(lines)


# Mode id -> context builder. Keys MUST cover exactly the MODE_AUTHORIZATION
# modes (asserted in tests).
CONTEXT_BUILDERS = {
    'modules':         _build_modules,
    'users':           _build_users,
    'config':          _build_config,
    'troubleshooting': _build_troubleshooting,
    'sales':           _build_sales,
    'accounting':      _build_accounting,
    'hr':              _build_hr,
    'operations':      _build_operations,
    'module_dev':      _build_module_dev,
    'integration':     _build_integration,
    'debugging':       _build_debugging,
    'testing':         _build_testing,
    'deployment':      _build_deployment,
    'customization':   _build_customization,
    'client_support':  _build_client_support,
}


def _build_mode_context(mode, env):
    """Dispatch to the per-mode builder and return a non-empty context string.

    Context assembly is best-effort: a read failure (e.g. a transient ORM
    error) must NEVER abort the chat request, so any exception degrades to a
    safe non-empty fallback. This ``except`` is intentionally broad but cannot
    swallow the ``/chat`` HTTP-status mechanism, because builders never call
    ``_json_status`` and run BEFORE the Anthropic call. No api_key value or user
    message content is ever read or logged here.
    """
    builder = CONTEXT_BUILDERS.get(mode)
    if builder is None:
        return _NO_CONTEXT
    try:
        context = builder(env)
    except Exception:  # noqa: BLE001 - context is best-effort; never fail the request
        _logger.debug("claude_assistant: context builder failed for mode %s", mode, exc_info=True)
        return _NO_CONTEXT
    return context or _NO_CONTEXT


# ---------------------------------------------------------------------------
# Controller.
# ---------------------------------------------------------------------------

class ClaudeAssistantController(http.Controller):
    """HTTP/server layer for the Claude Assistant addon.

    Exposes EXACTLY TWO authenticated (``auth='user'``) JSON-RPC routes:

    * ``POST /claude_assistant/chat`` -- validates the requested assistant
      *mode* against the fixed 15-value allow-list, enforces the per-mode
      security group, reads the Anthropic API key from ``ir.config_parameter``
      (server-side, via ``sudo``), assembles a per-mode live-ORM context,
      composes the Claude system prompt, and relays the (last 10) conversation
      messages to the Anthropic Messages API. EVERY outcome -- success or error
      -- is delivered with an explicit HTTP status code and a flat JSON body
      (see :func:`_json_status`), so HTTP callers branch on ``status_code``.

    * ``GET /claude_assistant/status`` -- reports whether the API key is
      configured (boolean ONLY -- never the value), the Odoo version, and the
      ordered list of assistant roles the current user is authorized for.
      Returns a plain dict (standard JSON-RPC envelope) which the OWL panel
      consumes via ``rpc()``.

    Credential model: the key lives in ``ir.config_parameter`` under
    ``claude_assistant.api_key`` (bound by ``models/res_config_settings.py``)
    and is read with ``sudo``. It is NEVER returned in a response body, written
    to a log, or embedded in the system prompt/context.

    NOTE (Odoo 19.0): ``@route(type='json')`` is a deprecated alias that the
    framework auto-rewrites to ``type='jsonrpc'`` (see odoo/http.py). We keep
    ``type='json'`` verbatim per the feature specification.
    """

    @route('/claude_assistant/chat', type='json', auth='user', methods=['POST'], csrf=True)
    def chat(self, mode=None, messages=None, **kwargs):
        """Relay a conversation turn to the Anthropic Messages API.

        Implements the fixed nine-step sequence. JSON-RPC ``params`` (``mode``,
        ``messages``) arrive by-name; any client-sent role is ignored -- the
        required group, ``max_tokens`` and role statement are derived solely
        from the constant tables.

        :param str mode: one of the 15 ``MODE_AUTHORIZATION`` keys.
        :param list messages: ``[{'role': 'user'|'assistant', 'content': str}]``.
        :returns: never returns normally; every path delivers a flat JSON body
            with an explicit HTTP status via :func:`_json_status`.
        """
        # ---- Step 1: validate mode against the fixed 15-value allow-list. ----
        # Covers None, unknown strings, and any disallowed value. The
        # ``isinstance(mode, str)`` guard runs FIRST so a non-string, unhashable
        # payload (e.g. a JSON array -> list, or object -> dict sent by an
        # authenticated direct JSON-RPC client) is rejected as an invalid mode
        # instead of raising ``TypeError: unhashable type`` at the dict-
        # membership test below. Without it that TypeError would surface BEFORE
        # this route's flat-body/real-HTTP-status contract and be swallowed into
        # Odoo's JSON-RPC error envelope (HTTP 200 + a debug traceback under
        # --dev), violating AAP chat Step 1 (every invalid mode -> clean 400).
        if not isinstance(mode, str) or mode not in MODE_AUTHORIZATION:
            return _json_status({'error': 'Invalid mode'}, 400)

        # ---- Step 2: per-mode group check, IMMEDIATELY after validation. ----
        required_group, max_tokens = MODE_AUTHORIZATION[mode]
        if not request.env.user.has_group(required_group):
            # AAP specifies werkzeug.exceptions.Forbidden() (403). A bare raise
            # on a type='json'/jsonrpc route is swallowed into a 200 envelope by
            # the dispatcher's handle_error, so we emit a REAL HTTP 403 via
            # abort + make_json_response to honor the explicit HTTP 403.
            return _json_status({'error': 'Forbidden'}, 403)

        # ---- Step 3: read the API key (server-side, sudo). ----
        api_key = request.env['ir.config_parameter'].sudo().get_param('claude_assistant.api_key')
        if not api_key:
            return _json_status({'response': None, 'error': 'API key not configured'}, 503)

        # ---- Step 4: build the per-mode live-ORM context string. ----
        context = _build_mode_context(mode, request.env)

        # ---- Step 5: compose the system prompt (version + base url + role + context). ----
        odoo_version = odoo.release.version
        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        role_statement = ROLE_STATEMENTS[MODE_TO_CATEGORY[mode]]
        system_prompt = (
            f"You are Claude, embedded in an Odoo {odoo_version} instance at {base_url}.\n"
            f"{role_statement}\n\n"
            f"Current Odoo context for the '{mode}' assistant mode:\n{context}"
        )

        # ---- Step 6: truncate history to the last 10 messages. ----
        # Forwarded as-is to the SDK; content is NEVER mutated, parsed, or eval'd.
        # Defensive normalization: an authenticated client may send a malformed
        # `messages` that is not a list (e.g. an object, string, or integer).
        # Coerce any non-list to [] BEFORE slicing, so a bare `[-10:]` on a
        # non-list can never raise TypeError. Such an exception would occur
        # before the Anthropic exception mapping below and be swallowed by
        # Odoo's JSON-RPC error machinery, bypassing this route's flat-body /
        # real-HTTP-status response contract.
        if not isinstance(messages, list):
            messages = []
        messages = messages[-10:]

        # ---- Steps 7 + 8: call Anthropic (28s transport timeout); map errors. ----
        try:
            client = anthropic.Anthropic(api_key=api_key, timeout=28)
            response = client.messages.create(
                model='claude-sonnet-4-6',
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
            )
        # Exception ORDER matters: every Anthropic error subclasses
        # anthropic.APIError. AuthenticationError / RateLimitError ->
        # APIStatusError -> APIError; APITimeoutError -> APIConnectionError ->
        # APIError. The catch-all (APIError) MUST be LAST, otherwise it would
        # swallow the more specific cases above. Error strings are short and
        # non-sensitive; the api_key and raw exception args are never echoed.
        except anthropic.AuthenticationError:
            return _json_status({'response': None, 'error': 'Authentication failed'}, 401)
        except anthropic.RateLimitError:
            return _json_status({'response': None, 'error': 'Rate limit exceeded'}, 429)
        except anthropic.APIConnectionError:
            # Connection/timeout family (includes anthropic.APITimeoutError).
            return _json_status({'response': None, 'error': 'Upstream timeout'}, 504)
        except anthropic.APIError:
            return _json_status({'response': None, 'error': 'Upstream API error'}, 502)

        # ---- Step 9: success. ----
        return _json_status({'response': response.content[0].text, 'error': None}, 200)

    @route('/claude_assistant/status', type='json', auth='user')
    def status(self, **kwargs):
        """Report assistant availability and the current user's authorized roles.

        Returns a plain dict (standard JSON-RPC envelope, HTTP 200) consumed by
        the OWL panel via ``rpc()``:

        * ``api_key_configured`` (bool) -- whether the key is set; NEVER the value.
        * ``odoo_version`` (str) -- ``odoo.release.version``.
        * ``user_roles`` (list) -- ordered ``{id, label, modes}`` for each role
          the user holds. Because ``base.group_system`` natively implies
          ``base.group_user``, an administrator yields BOTH the ``admin`` and
          ``business`` roles -- this is correct and intended.
        """
        api_key = request.env['ir.config_parameter'].sudo().get_param('claude_assistant.api_key')
        api_key_configured = bool(api_key)  # boolean ONLY -- never the key value
        odoo_version = odoo.release.version

        user = request.env.user
        user_roles = []
        for role in ROLES:
            if user.has_group(role['group']):
                # Expose only id/label/modes; omit internal group/category keys.
                # Copy the mode dicts so the module-level constant is never shared
                # or mutated through the response.
                user_roles.append({
                    'id': role['id'],
                    'label': role['label'],
                    'modes': [dict(m) for m in role['modes']],
                })

        return {
            'api_key_configured': api_key_configured,
            'odoo_version': odoo_version,
            'user_roles': user_roles,
        }
