from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.passwords import PasswordRejected
from app.auth.service import (
    AuthSession,
    LoginDenied,
    accept_invite,
    change_password,
    create_invite,
    list_sessions,
    login_with_password,
    recover_password,
    revoke_other_sessions,
    revoke_session,
    setup_admin,
)
from app.auth.service import (
    session_id as session_id_for,
)
from app.core.config import get_settings
from app.core.security import (
    clear_session_cookie,
    client_ip,
    new_csrf_token,
    set_csrf_cookie,
    set_session_cookie,
)

router = APIRouter(prefix="/api/v1")


class SetupIn(BaseModel):
    token: str
    email: str
    password: str
    display_name: str


class LoginIn(BaseModel):
    email: str
    password: str
    trust_device: bool = False
    device_label: str | None = None


class PasswordIn(BaseModel):
    password: str
    current_password: str | None = None


class InviteIn(BaseModel):
    role: str = "rater"
    email: str | None = None
    hunt_id: str | None = None


class AcceptInviteIn(BaseModel):
    token: str
    email: str
    password: str
    display_name: str


class RecoverIn(BaseModel):
    token: str
    password: str


def _session_response(result: AuthSession) -> JSONResponse:
    response = JSONResponse(result.user)
    set_session_cookie(response, result.token, result.expires_at)
    return response


def _token(request: Request) -> str | None:
    return request.cookies.get(get_settings().cookie_name)


@router.get("/csrf")
def issue_csrf() -> JSONResponse:
    token = new_csrf_token()
    response = JSONResponse({"token": token})
    set_csrf_cookie(response, token)
    return response


@router.post("/setup", response_model=None)
def setup(body: SetupIn, request: Request) -> JSONResponse:
    result = setup_admin(
        token=body.token,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    if isinstance(result, PasswordRejected):
        return JSONResponse({"detail": str(result)}, status_code=400)
    if result == "closed":
        return JSONResponse({"detail": "setup is closed"}, status_code=404)
    if result == "invalid":
        return JSONResponse({"detail": "invalid setup token"}, status_code=400)
    if result == "rejected":
        return JSONResponse({"detail": "display name is required"}, status_code=400)
    return _session_response(result)


@router.post("/auth/password/login", response_model=None)
def password_login(body: LoginIn, request: Request) -> JSONResponse:
    result = login_with_password(
        email=body.email,
        password=body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        trust_device=body.trust_device,
        device_label=body.device_label,
    )
    if isinstance(result, LoginDenied):
        if result.code == "locked":
            return JSONResponse({"detail": "too many attempts", "code": "locked"}, status_code=429)
        if result.code == "step_up":
            return JSONResponse(
                {"detail": "step-up needed", "code": "step_up_needed"},
                status_code=401,
            )
        return JSONResponse({"detail": "invalid credentials"}, status_code=401)
    return _session_response(result)


@router.get("/auth/sessions", response_model=None)
def sessions(request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    rows = list_sessions(token, client_ip(request))
    if rows is None:
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    return JSONResponse({"sessions": rows})


@router.delete("/auth/sessions/{session_id}", response_model=None)
def delete_session(session_id: str, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    result = revoke_session(token, client_ip(request), session_id)
    if result == "unauthenticated":
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    if result == "missing":
        return JSONResponse({"detail": "session not found"}, status_code=404)
    response = JSONResponse({"ok": True})
    if session_id == session_id_for(token):
        clear_session_cookie(response)
    return response


@router.post("/auth/sessions/revoke-others", response_model=None)
def revoke_others(request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    if not revoke_other_sessions(token, client_ip(request)):
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    return JSONResponse({"ok": True})


@router.post("/auth/password", response_model=None)
def set_password(body: PasswordIn, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    result = change_password(
        token,
        client_ip(request),
        password=body.password,
        current_password=body.current_password,
    )
    if isinstance(result, PasswordRejected):
        return JSONResponse({"detail": str(result)}, status_code=400)
    if result == "unauthenticated":
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    if result == "stale":
        return JSONResponse(
            {"detail": "step-up needed", "code": "step_up_needed"},
            status_code=403,
        )
    if result == "invalid_current":
        return JSONResponse({"detail": "current password is wrong"}, status_code=400)
    return JSONResponse({"ok": True})


@router.post("/auth/invites", response_model=None)
def invites(body: InviteIn, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    result = create_invite(
        token,
        client_ip(request),
        role=body.role,
        email=body.email,
        hunt_id=body.hunt_id,
    )
    if result == "unauthenticated":
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    if result == "forbidden":
        return JSONResponse({"detail": "admin required"}, status_code=403)
    if result == "stale":
        return JSONResponse(
            {"detail": "step-up needed", "code": "step_up_needed"},
            status_code=403,
        )
    if result == "invalid":
        return JSONResponse({"detail": "invalid invite"}, status_code=400)
    return JSONResponse(result, status_code=201)


@router.post("/auth/invite/accept", response_model=None)
def invite_accept(body: AcceptInviteIn, request: Request) -> JSONResponse:
    result = accept_invite(
        token=body.token,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    if isinstance(result, PasswordRejected):
        return JSONResponse({"detail": str(result)}, status_code=400)
    if result == "rejected":
        return JSONResponse({"detail": "email and display name are required"}, status_code=400)
    if result == "invalid":
        return JSONResponse({"detail": "invite is not valid"}, status_code=400)
    return _session_response(result)


@router.post("/auth/recovery", response_model=None)
def recovery(body: RecoverIn) -> JSONResponse:
    result = recover_password(body.token, body.password)
    if isinstance(result, PasswordRejected):
        return JSONResponse({"detail": str(result)}, status_code=400)
    if result == "invalid":
        return JSONResponse({"detail": "recovery link is not valid"}, status_code=400)
    return JSONResponse({"ok": True})
