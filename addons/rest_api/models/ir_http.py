# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from werkzeug.datastructures import WWWAuthenticate
from werkzeug.exceptions import Unauthorized

from odoo import api, models, tools
from odoo.exceptions import AccessDenied
from odoo.http import request

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    """Additive ``ir.http`` extension for the REST API surface.

    This inheritance contributes a single authentication strategy,
    :meth:`_auth_method_rest_bearer`, consumed by REST routes declared with
    ``@route(type='rest', auth='rest_bearer')``. It reuses Odoo's existing
    credential primitives (API keys and OAuth 2.0 bearer validation) without
    reimplementing them, and — unlike the base ``_auth_method_bearer`` — it
    never falls back to interactive session-cookie authentication. The REST
    surface is therefore strictly bearer-only and stateless.
    """
    _inherit = 'ir.http'

    @api.model
    @tools.ormcache('scope', 'key')
    def _rest_bearer_apikey_uid(self, scope, key):
        """Resolve an API key to its owning user id, caching successful lookups.

        This is a thin, cached wrapper around
        :meth:`res.users.apikeys._check_credentials` — it *reuses* that
        primitive verbatim (no key material is re-hashed or re-implemented here)
        and simply memoises the ``(scope, key) -> uid`` resolution so that
        repeated REST requests bearing the *same* API key do not re-run the
        expensive PBKDF2-SHA512 verification (``KEY_CRYPT_CONTEXT.verify``,
        ~4 ms) on every call.

        Rationale (performance parity, AAP Gate 5)
        ------------------------------------------
        The JSON-RPC path already amortises this cost: ``execute_kw`` verifies
        credentials through :meth:`res.users._check_uid_passwd`, which is
        decorated ``@tools.ormcache('uid', 'passwd')`` — so PBKDF2 runs once per
        ``(uid, passwd)`` per worker and every subsequent same-credential call
        skips it entirely. Without an equivalent cache, the REST bearer path
        re-ran PBKDF2 on *every* request, adding a fixed ~4 ms tax that made the
        cheapest reads (single-record fetch-by-id) exceed the Gate 5 "within
        10% of JSON-RPC" latency threshold. This method restores parity by
        mirroring ``_check_uid_passwd``'s caching strategy exactly, including
        its cache-invalidation semantics: the default ``ormcache`` is flushed by
        ``registry.clear_cache()`` on ``res.users`` write/unlink/deactivation
        (see ``res_users.py``), so user-level revocation invalidates cached
        resolutions identically for both surfaces.

        Negative results are deliberately **not** cached. On a non-match the
        wrapped call returns a falsy value and this method raises
        :class:`~odoo.exceptions.AccessDenied`; because ``ormcache`` only stores
        a value when the wrapped call *returns* (it never caches when the call
        raises), an unknown/expired/revoked key is never memoised as a miss and
        can therefore never be locked out. This mirrors ``_check_uid_passwd``,
        which likewise raises rather than caching a failure. The single caller,
        :meth:`_auth_method_rest_bearer`, catches this ``AccessDenied`` and
        treats it as "not an API key" so it can fall through to the OAuth path.

        :param str scope: the API-key scope to match (always ``'rpc'`` for the
            REST surface — selects global, NULL-scope keys, honouring
            ``expiration_date``), identical to the base ``_auth_method_bearer``.
        :param str key: the raw bearer token presented by the client.
        :returns: the Odoo ``res.users`` id that owns the verified key.
        :rtype: int
        :raises odoo.exceptions.AccessDenied: if the token is not a valid API
            key (so the failure is not cached and the caller can try OAuth).
        """
        uid = self.env['res.users.apikeys']._check_credentials(scope=scope, key=key)
        if not uid:
            # Raise (do not return a falsy value) so ormcache does not memoise
            # this miss — a key created/renewed later must not be locked out,
            # and revoked keys must not be resurrected. Mirrors _check_uid_passwd.
            raise AccessDenied()
        return uid

    @classmethod
    def _auth_method_rest_bearer(cls):
        """Authenticate a REST request from an ``Authorization: Bearer`` token.

        The token is accepted if it resolves to *either* a valid global Odoo
        API key *or* a valid OAuth 2.0 access token linked to an existing user.
        On success the request environment is rebound to the authenticated user
        and the session is marked stateless (``can_save = False``).

        This method deliberately diverges from :meth:`_auth_method_bearer`:
        there is **no** session fallback and **no** Sec-header interactive path.
        A request without a bearer token — even one carrying a valid session
        cookie — is rejected with HTTP ``401``. This guarantees that a browser
        session can never authenticate against the REST surface.

        :raises werkzeug.exceptions.Unauthorized: if no bearer token is present,
            or the token matches neither a valid API key nor a linked OAuth
            access token. The ``WWW-Authenticate: bearer`` challenge is attached
            so clients receive a standards-compliant ``401`` response.
        """
        # --- Step 1: extract the bearer token (mirrors _auth_method_bearer) ---
        # Case-insensitive so "Bearer", "bearer" and "BEARER" all parse, matching
        # the base method's get_http_authorization_bearer_token helper exactly.
        headers = request.httprequest.headers
        header = headers.get("Authorization")
        token = None
        if header and (m := re.match(r"^bearer\s+(.+)$", header, re.IGNORECASE)):
            token = m.group(1)

        # --- Step 2: no token -> 401 immediately (critical divergence) ---
        # The REST surface accepts ONLY a bearer token. We never consult
        # request.session.uid / request.env.uid here, so a session cookie can
        # never authenticate a REST request.
        if not token:
            e = "Authentication required: provide a Bearer token (API key or OAuth access token)."
            raise Unauthorized(e, www_authenticate=WWWAuthenticate('bearer'))

        # --- Step 3: try the token as a global Odoo API key first ---
        # 'rpc' scope selects global (NULL-scope) keys and honours expiration,
        # identical to the base bearer method. This goes through the cached
        # resolver _rest_bearer_apikey_uid so that repeated same-key requests
        # skip the ~4 ms PBKDF2-SHA512 verification — restoring latency parity
        # with the JSON-RPC path (which caches via res.users._check_uid_passwd).
        # A non-match raises AccessDenied (so the miss is not cached); we catch
        # it here, leave uid falsy, and fall through to the OAuth attempt — this
        # preserves the exact pre-cache control flow (API key first, then OAuth,
        # else 401).
        uid = None
        try:
            uid = request.env['ir.http']._rest_bearer_apikey_uid('rpc', token)
        except AccessDenied:
            uid = None

        # --- Step 4: otherwise try the token as an OAuth 2.0 access token ---
        # _auth_oauth_validate performs a network round-trip and raises on any
        # invalid/expired token, so each provider attempt is guarded and a
        # failure degrades cleanly to the next provider (never a 500).
        if not uid:
            providers = request.env['auth.oauth.provider'].sudo().search([('enabled', '=', True)])
            for provider in providers:
                try:
                    validation = request.env['res.users'].sudo()._auth_oauth_validate(provider.id, token)
                except Exception:  # noqa: BLE001 - any validation/network error just means "try next provider"
                    _logger.debug(
                        "REST bearer: OAuth validation failed for provider %s",
                        provider.id, exc_info=True,
                    )
                    continue
                # validation['user_id'] is the OAuth SUBJECT (external uid), not an
                # Odoo user id; resolve the linked Odoo user exactly as
                # _auth_oauth_signin does. We only match EXISTING linked users —
                # this is API authentication, not interactive sign-up.
                subject = validation.get('user_id')
                if not subject:
                    continue
                oauth_user = request.env['res.users'].sudo().search([
                    ('oauth_uid', '=', subject),
                    ('oauth_provider_id', '=', provider.id),
                ], limit=1)
                if oauth_user:
                    uid = oauth_user.id
                    break

        # --- Step 5: neither mechanism authenticated -> 401 ---
        if not uid:
            e = "Invalid bearer token: not a valid API key or OAuth access token."
            raise Unauthorized(e, www_authenticate=WWWAuthenticate('bearer'))

        # --- Step 6: bind the authenticated user; stay stateless ---
        # Mirrors the base method's success path minus the cls._auth_method_user()
        # session fallback. can_save = False ensures no session is persisted.
        request.update_env(user=uid)
        request.session.can_save = False  # stateless - do not persist a session
