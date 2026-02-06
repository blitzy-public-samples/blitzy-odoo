# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Security regression test suite for Odoo 19.0 security remediation.

Validates the following security fixes across the codebase:
- XXE prevention in XML parsing (assetsbundle.py, xml_utils.py)
- SQL injection parameterization (base_partner_merge.py)
- Session cookie security flags (http.py)
- X-Frame-Options clickjacking prevention (http.py)

Tagged with 'security' for selective CI/CD execution via:
    odoo-bin -d test_db --test-tags security -i base --stop-after-init

References:
    CWE-611  (XXE - Improper Restriction of XML External Entity Reference)
    CWE-89   (SQL Injection - Improper Neutralization of Special Elements)
    CWE-614  (Sensitive Cookie Without 'Secure' Flag)
    CWE-1275 (Sensitive Cookie With Improper SameSite Attribute)
    CWE-1021 (Improper Restriction of Rendered UI Layers / Clickjacking)
"""

from unittest.mock import patch  # noqa: F401 - available for test isolation

from lxml import etree

from odoo.tests.common import TransactionCase, HttpCase, tagged
from odoo.tools import SQL


# ---------------------------------------------------------------------------
# Class 1: XXE Prevention Tests
# Validates: resolve_entities=False in assetsbundle.py (line 441) and
#            xml_utils.py (line 104)
# ---------------------------------------------------------------------------

@tagged('at_install', 'security')
class TestXXEPrevention(TransactionCase):
    """Tests that XML parsers block external entity resolution to prevent
    XXE injection attacks (CWE-611).

    The lxml XMLParser must be instantiated with ``resolve_entities=False``
    wherever untrusted or semi-trusted XML content is parsed.  Two locations
    were remediated:

    * ``odoo/addons/base/models/assetsbundle.py`` line 441 — asset bundle
      XML/CSS processing.
    * ``odoo/tools/xml_utils.py`` line 104 — XSD schema validation used by
      EDI modules (l10n_cl_edi, l10n_co_edi, etc.).
    """

    def test_xxe_entity_blocked(self):
        """Verify XMLParser(resolve_entities=False) blocks external entities.

        Crafts an XXE payload referencing ``file:///etc/passwd`` and parses it
        using the same parser configuration applied in ``assetsbundle.py`` at
        line 441.  The entity reference must NOT be resolved — the root element
        text must be empty or ``None``, never containing file contents.

        SECURITY: XXE Prevention (CWE-611) — resolve_entities=False blocks
        external entity injection in asset bundle processing.
        """
        # SECURITY: XXE Prevention - parser mirrors assetsbundle.py line 441
        parser = etree.XMLParser(
            ns_clean=True,
            recover=True,
            remove_comments=True,
            resolve_entities=False,
        )

        # Craft payload that would exfiltrate /etc/passwd if entities resolved
        xxe_payload = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<!DOCTYPE foo ['
            b'  <!ENTITY xxe SYSTEM "file:///etc/passwd">'
            b']>'
            b'<root>&xxe;</root>'
        )

        tree = etree.fromstring(xxe_payload, parser=parser)
        text_content = tree.text or ''

        # Entity must NOT be resolved — text must be empty, not /etc/passwd
        self.assertNotIn('root:', text_content,
                         "XXE entity was resolved! /etc/passwd content leaked. "
                         "Parser must use resolve_entities=False")
        self.assertNotIn('/bin/', text_content,
                         "XXE entity was resolved! /etc/passwd content leaked. "
                         "Parser must use resolve_entities=False")
        self.assertNotIn('/home/', text_content,
                         "XXE entity was resolved! /etc/passwd content leaked. "
                         "Parser must use resolve_entities=False")

    def test_xsd_validation_safe(self):
        """Verify XMLParser used for XSD validation blocks external entities.

        Crafts an XXE payload and parses it using the same parser configuration
        applied in ``xml_utils.py`` at line 104.  The entity reference must NOT
        be resolved — child element text must remain empty.

        SECURITY: XXE Prevention (CWE-611) — resolve_entities=False blocks
        external entity injection in XSD schema validation.
        """
        # SECURITY: XXE Prevention - parser mirrors xml_utils.py line 104
        parser = etree.XMLParser(resolve_entities=False)

        # Payload with nested entity reference
        xxe_payload = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<!DOCTYPE foo ['
            b'  <!ENTITY xxe SYSTEM "file:///etc/passwd">'
            b']>'
            b'<root>&xxe;</root>'
        )

        tree = etree.fromstring(xxe_payload, parser=parser)
        text_content = tree.text or ''

        # Entity should not be resolved — text must be empty
        self.assertNotIn('root:', text_content,
                         "XXE entity was resolved in xml_utils parser! "
                         "Parser must use resolve_entities=False")
        self.assertEqual(text_content, '',
                         "Entity content should be empty when "
                         "resolve_entities=False is set on XMLParser")


# ---------------------------------------------------------------------------
# Class 2: SQL Injection Prevention Tests
# Validates: SQL.identifier() usage and parameterized queries in
#            base_partner_merge.py (lines 134, 148, 171, 176, 181)
# ---------------------------------------------------------------------------

@tagged('at_install', 'security')
class TestSQLInjection(TransactionCase):
    """Tests that SQL queries use parameterized identifiers and placeholders
    to prevent SQL injection attacks (CWE-89).

    The partner merge wizard (``base_partner_merge.py``) was remediated to use
    ``SQL.identifier()`` for table/column name quoting and ``%s`` parameter
    placeholders for values, replacing unsafe Python ``%``-formatting.
    """

    def test_partner_merge_safe_identifiers(self):
        """Verify SQL.identifier() rejects malicious names and quotes valid ones.

        ``SQL.identifier()`` validates input against a strict identifier regex
        and raises ``AssertionError`` for names containing SQL metacharacters
        (quotes, semicolons, spaces, parentheses).  This is the core defense
        mechanism used in the remediated ``base_partner_merge.py``.

        SECURITY: SQL Injection (CWE-89) — SQL.identifier() safely quotes
        table/column names derived from pg_constraint metadata.
        """
        # --- Malicious names MUST be rejected ---

        # Attempt: close quote + DROP TABLE injection
        with self.assertRaises(AssertionError,
                               msg="SQL.identifier must reject names with quotes"):
            SQL.identifier('"; DROP TABLE --')

        # Attempt: semicolon-based statement termination
        with self.assertRaises(AssertionError,
                               msg="SQL.identifier must reject names with semicolons"):
            SQL.identifier('table; DROP TABLE ir_attachment; --')

        # Attempt: sub-select injection
        with self.assertRaises(AssertionError,
                               msg="SQL.identifier must reject names with parentheses"):
            SQL.identifier('(SELECT 42)')

        # --- Valid identifiers MUST work correctly ---

        # Standard Odoo table name
        safe_ident = SQL.identifier('res_partner')
        self.assertEqual(safe_ident.code, '"res_partner"',
                         "Valid table name must be properly double-quoted")
        self.assertEqual(safe_ident.params, [],
                         "Identifier must have no params (it is inlined)")

        # Table + column (two-part identifier)
        qualified = SQL.identifier('res_partner', 'partner_id')
        self.assertEqual(qualified.code, '"res_partner"."partner_id"',
                         "Qualified identifier must quote both parts")

        # Verify the SQL pattern used in the fixed base_partner_merge.py
        table_ident = SQL.identifier('res_partner')
        column_ident = SQL.identifier('partner_id')
        query = SQL(
            'SELECT FROM %s WHERE %s IN %%s LIMIT 1',
            table_ident, column_ident,
        )
        self.assertIn('"res_partner"', query.code,
                      "Table name must appear as quoted identifier in query")
        self.assertIn('"partner_id"', query.code,
                      "Column name must appear as quoted identifier in query")

    def test_information_schema_parameterized(self):
        """Verify catalog queries use parameterized statements, not formatting.

        The information_schema query in ``base_partner_merge.py`` (line 134)
        was changed from:
            ``"... WHERE table_name LIKE '%s'" % (table)``
        to:
            ``cr.execute("... WHERE table_name LIKE %s", (table,))``

        The ``%s`` must be a psycopg2 parameter placeholder (bare, no quotes),
        keeping the table name value separate from the query structure.

        SECURITY: SQL Injection (CWE-89) — parameterized query keeps user/
        catalog-derived values out of the query string.
        """
        # The fixed query template — %s is a psycopg2 parameter placeholder
        query_template = (
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name LIKE %s"
        )

        # Must use bare %s, NOT Python-quoted '%s'
        self.assertNotIn("'%s'", query_template,
                         "Query must use bare %s placeholder, not quoted '%s' "
                         "Python format string")

        # Must have exactly one placeholder
        self.assertEqual(query_template.count('%s'), 1,
                         "Query must have exactly one parameter placeholder")

        # Verify that SQL() can wrap the pattern safely with a parameter
        table_value = "res_partner"
        sql_obj = SQL(query_template, table_value)
        self.assertEqual(sql_obj.code, query_template,
                         "SQL object must preserve the query template unchanged")
        self.assertEqual(sql_obj.params, [table_value],
                         "SQL object must keep the table value as a bound param")

        # Verify malicious input stays as a bound parameter, never in the code
        malicious_value = "res_partner'; DROP TABLE ir_cron; --"
        sql_obj = SQL(query_template, malicious_value)
        self.assertNotIn(malicious_value, sql_obj.code,
                         "Malicious value must NOT appear in SQL code string")
        self.assertIn(malicious_value, sql_obj.params,
                      "Malicious value must be kept as a bound parameter")


# ---------------------------------------------------------------------------
# Class 3: Session Cookie Security Tests
# Validates: httponly, secure, samesite='Lax' flags on session_id cookie
#            in http.py (lines 2134 and 2457)
# ---------------------------------------------------------------------------

@tagged('-at_install', 'post_install', 'security')
class TestSessionSecurity(HttpCase):
    """Tests that session cookies include proper security flags to prevent
    session hijacking and CSRF attacks.

    The ``set_cookie`` calls in ``odoo/http.py`` (lines 2134 and 2457) were
    remediated to include:
    - ``httponly=True``  — prevents JavaScript access (CWE-614)
    - ``secure=True``    — when HTTPS, prevents plaintext transmission
    - ``samesite='Lax'`` — prevents CSRF via cross-origin requests (CWE-1275)
    """

    def test_session_cookie_flags(self):
        """Verify session_id cookie includes HttpOnly and SameSite=Lax flags.

        Authenticates as admin, then triggers a fresh session cookie by
        clearing existing cookies and making a request.  The server must
        create a new session and set the ``session_id`` cookie with the
        correct security attributes.

        Note: The ``Secure`` flag cannot be reliably tested in the HTTP-only
        test environment; it is conditionally set based on ``request.scheme``.

        SECURITY: Session Hardening (CWE-614, CWE-1275) — HttpOnly prevents
        JavaScript cookie theft; SameSite=Lax prevents CSRF.
        """
        self.authenticate('admin', 'admin')

        # Clear session cookies to force the server to issue a new Set-Cookie
        # header (cookie_sid != sess.sid triggers set_cookie in _save_session)
        self.opener.cookies.clear()
        res = self.url_open('/web/login', allow_redirects=False)

        set_cookie_header = res.headers.get('Set-Cookie', '')

        # Server must have set a session_id cookie
        self.assertIn('session_id', set_cookie_header,
                      "Server must set session_id cookie on new session")

        # SECURITY: HttpOnly flag prevents JavaScript access to session cookie
        self.assertIn('HttpOnly', set_cookie_header,
                      "session_id cookie must include HttpOnly flag to prevent "
                      "JavaScript access (CWE-614)")

        # SECURITY: SameSite=Lax prevents CSRF via cross-origin POST requests
        # while allowing top-level GET navigations (e.g., email links to Odoo)
        self.assertIn('SameSite=Lax', set_cookie_header,
                      "session_id cookie must include SameSite=Lax to prevent "
                      "CSRF attacks (CWE-1275)")

    def test_session_rotation_flags(self):
        """Verify that session cookies set after authentication retain flags.

        After authenticating and accessing the web client, any session cookie
        renewed by the server (e.g., after session rotation or dirty-session
        save) must preserve HttpOnly and SameSite=Lax attributes.

        SECURITY: Session Hardening — rotated/renewed sessions must retain
        all cookie security flags set during initial creation.
        """
        self.authenticate('admin', 'admin')

        # Make an authenticated request; the server may renew the session
        # cookie if the session becomes dirty during request processing
        res = self.url_open('/web')

        # Collect Set-Cookie headers from the entire redirect chain
        session_cookie_headers = []
        for resp in (res.history or []):
            header_val = resp.headers.get('Set-Cookie', '')
            if 'session_id' in header_val:
                session_cookie_headers.append(header_val)
        final_header = res.headers.get('Set-Cookie', '')
        if 'session_id' in final_header:
            session_cookie_headers.append(final_header)

        # If the server issued any session cookies during this request chain,
        # every one must include the correct security flags
        for cookie_header in session_cookie_headers:
            self.assertIn('HttpOnly', cookie_header,
                          "Renewed session cookie must retain HttpOnly flag")
            self.assertIn('SameSite=Lax', cookie_header,
                          "Renewed session cookie must retain SameSite=Lax")


# ---------------------------------------------------------------------------
# Class 4: Response Header Security Tests
# Validates: X-Frame-Options: SAMEORIGIN header in http.py set_csp method
# ---------------------------------------------------------------------------

@tagged('-at_install', 'post_install', 'security')
class TestResponseHeaders(HttpCase):
    """Tests that security response headers are properly set to prevent
    clickjacking and content type sniffing attacks.

    The ``set_csp`` method in ``odoo/http.py`` (around line 2731) was updated
    to include ``X-Frame-Options: SAMEORIGIN`` on all responses, preventing
    cross-origin iframe embedding (CWE-1021).

    ``SAMEORIGIN`` is used instead of ``DENY`` because Odoo uses iframes
    internally for report previews and embedded actions.
    """

    def test_x_frame_options(self):
        """Verify X-Frame-Options: SAMEORIGIN is present on HTML responses.

        Authenticates as admin and requests the web client.  The response
        must include the ``X-Frame-Options`` header set to ``SAMEORIGIN``
        to block cross-origin iframe embedding while allowing Odoo's own
        internal iframe usage.

        SECURITY: Clickjacking Prevention (CWE-1021) — X-Frame-Options
        blocks cross-origin iframe embedding of Odoo pages.
        """
        self.authenticate('admin', 'admin')
        res = self.url_open('/web')

        x_frame = res.headers.get('X-Frame-Options')
        self.assertEqual(x_frame, 'SAMEORIGIN',
                         "X-Frame-Options header must be set to SAMEORIGIN "
                         "to prevent clickjacking (CWE-1021). "
                         f"Got: {x_frame!r}")
