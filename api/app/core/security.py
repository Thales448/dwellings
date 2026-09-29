import hmac
import secrets
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.clock import as_utc, utcnow
from app.core.config import get_settings

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    trusted = {item.strip() for item in get_settings().trusted_proxies.split(",") if item.strip()}
    if peer in trusted:
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return peer


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_ok(request: Request) -> bool:
    settings = get_settings()
    origin = request.headers.get("origin")
    expected = settings.public_url.rstrip("/")
    if origin is None or not hmac.compare_digest(origin, expected):
        return False
    cookie = request.cookies.get(settings.csrf_cookie_name)
    header = request.headers.get("x-csrf-token")
    if not cookie or not header:
        return False
    return hmac.compare_digest(cookie, header)


def needs_csrf(request: Request) -> bool:
    if request.method not in UNSAFE or not request.url.path.startswith("/api/"):
        return False
    settings = get_settings()
    authorization = request.headers.get("authorization", "")
    has_session = settings.cookie_name in request.cookies
    if authorization.lower().startswith("bearer ") and not has_session:
        return False
    return True


def apply_security_headers(response: Response) -> None:
    settings = get_settings()
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "style-src-attr 'unsafe-inline'; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    if settings.cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


def set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    settings = get_settings()
    max_age = max(0, int((as_utc(expires_at) - utcnow()).total_seconds()))
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def set_csrf_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.csrf_cookie_name,
        token,
        max_age=60 * 60 * 12,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if needs_csrf(request) and not csrf_ok(request):
            return JSONResponse({"detail": "csrf check failed"}, status_code=403)
        response = await call_next(request)
        apply_security_headers(response)
        return response
