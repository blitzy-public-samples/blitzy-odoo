# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from werkzeug.datastructures import WWWAuthenticate
from werkzeug.exceptions import Unauthorized

from odoo import models
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
        # identical to the base bearer method. Returns the Odoo user id or None.
        uid = request.env['res.users.apikeys']._check_credentials(scope='rpc', key=token)

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
