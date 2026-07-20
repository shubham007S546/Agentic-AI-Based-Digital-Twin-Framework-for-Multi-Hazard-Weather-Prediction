"""
app/middleware/security_headers.py
───────────────────────────────────
Security headers middleware — equivalent to Helmet.js for Node.js backends.

Design decisions:
  • All OWASP-recommended security headers are applied on every response.
  • Content-Security-Policy is intentionally restrictive by default; individual
    routes can override via response headers if needed.
  • HSTS is only applied in non-development environments to avoid issues with
    local HTTP development.
  • X-Content-Type-Options prevents MIME-sniffing attacks where a browser might
    interpret a JSON response as JavaScript.
  • Referrer-Policy is set to 'strict-origin-when-cross-origin' — leaks enough
    referrer for analytics without exposing full URL paths.

References:
  - OWASP Secure Headers Project
  - NIST SP 800-44 (Guidelines on Securing Public Web Servers)
  - Mozilla Observatory A+ requirements
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Applies HTTP security headers to every response.

    Order: Register LAST in the middleware chain so headers are always
    applied regardless of which handler generates the response.
    """

    def __init__(self, app: ASGIApp, *, is_production: bool = False) -> None:
        super().__init__(app)
        self.is_production = is_production

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        self._apply_security_headers(response)
        return response

    def _apply_security_headers(self, response: Response) -> None:
        headers = response.headers

        # ── Prevent MIME-type sniffing ─────────────────────────────────────────
        # Without this, Chrome may execute a JSON file as JavaScript if linked
        # from an <img> tag (content sniffing attack).
        headers["X-Content-Type-Options"] = "nosniff"

        # ── Clickjacking protection ────────────────────────────────────────────
        # Prevents our pages from being embedded in an <iframe> on a hostile site.
        headers["X-Frame-Options"] = "DENY"

        # ── Legacy XSS filter (deprecated but harmless) ────────────────────────
        headers["X-XSS-Protection"] = "1; mode=block"

        # ── Referrer Policy ────────────────────────────────────────────────────
        # Full URL is sent to same-origin, only scheme+origin to cross-origin.
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # ── Permissions Policy ─────────────────────────────────────────────────
        # Restrict access to sensitive browser features.
        # A disaster management API doesn't need camera, microphone, or geolocation.
        headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=(), payment=(), usb=()"
        )

        # ── Content Security Policy ────────────────────────────────────────────
        # This applies to the API's own Swagger/ReDoc UI.
        # API clients (Next.js) apply their own CSP.
        headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net fonts.googleapis.com; "
            "font-src 'self' fonts.gstatic.com data:; "
            "img-src 'self' data: validator.swagger.io; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )

        # ── HSTS (HTTP Strict Transport Security) ──────────────────────────────
        # Only set in production — HSTS on localhost causes browser issues.
        # max-age=31536000 = 1 year (Google Safe Browsing minimum).
        # includeSubDomains and preload included for maximum security.
        if self.is_production:
            headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # ── Cross-Origin Policies ──────────────────────────────────────────────
        # COEP + COOP enable SharedArrayBuffer for potential WebAssembly/ML features.
        headers["Cross-Origin-Opener-Policy"] = "same-origin"
        headers["Cross-Origin-Resource-Policy"] = "same-site"

        # ── Server identity suppression ────────────────────────────────────────
        # Remove 'server' header — no need to advertise server version.
        # uvicorn sets this; we override it.
        headers["Server"] = "weather-twin"

        # ── Cache Control ──────────────────────────────────────────────────────
        # API responses should not be cached by default (sensitive data).
        # Individual endpoints can override with explicit Cache-Control headers.
        if "Cache-Control" not in headers:
            headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
