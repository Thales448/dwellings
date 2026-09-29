from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.passkeys import (
    PasskeyStepUp,
    authentication_options,
    authentication_verify,
    delete_credential,
    list_credentials,
    registration_options,
    registration_verify,
    rename_credential,
)
from app.auth.service import AuthSession, revoke_all_sessions
from app.core.config import get_settings
from app.core.security import clear_session_cookie, client_ip, set_session_cookie

router = APIRouter(prefix="/api/v1")


class VerifyRegistrationIn(BaseModel):
    challenge_id: str
    credential: dict[str, Any]
    nickname: str


class VerifyAuthenticationIn(BaseModel):
    challenge_id: str
    credential: dict[str, Any]


class RenameIn(BaseModel):
    nickname: str


def _token(request: Request) -> str | None:
    return request.cookies.get(get_settings().cookie_name)


def _error(code: str) -> JSONResponse:
    if code == "unauthenticated":
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    if code == "stale":
        return JSONResponse(
            {"detail": "step-up needed", "code": "step_up_needed"},
            status_code=403,
        )
    if code == "missing":
        return JSONResponse({"detail": "passkey not found"}, status_code=404)
    if code == "last":
        return JSONResponse(
            {"detail": "cannot remove the last way to sign in"},
            status_code=409,
        )
    return JSONResponse({"detail": "passkey ceremony failed"}, status_code=400)


@router.post("/auth/passkey/register/options", response_model=None)
def register_options(request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _error("unauthenticated")
    result = registration_options(token, client_ip(request))
    if isinstance(result, str):
        return _error(result)
    return JSONResponse(result)


@router.post("/auth/passkey/register/verify", response_model=None)
def register_verify(body: VerifyRegistrationIn, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _error("unauthenticated")
    result = registration_verify(
        token,
        client_ip(request),
        challenge_id=body.challenge_id,
        credential=body.credential,
        nickname=body.nickname,
    )
    if isinstance(result, str):
        return _error(result)
    return JSONResponse(result, status_code=201)


@router.post("/auth/passkey/options", response_model=None)
def assert_options() -> JSONResponse:
    return JSONResponse(authentication_options())


@router.post("/auth/passkey/verify", response_model=None)
def assert_verify(body: VerifyAuthenticationIn, request: Request) -> JSONResponse:
    result = authentication_verify(
        challenge_id=body.challenge_id,
        credential=body.credential,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        existing_token=_token(request),
    )
    if result == "invalid":
        return _error("invalid")
    if isinstance(result, PasskeyStepUp):
        return JSONResponse({"user": result.user, "step_up": True})
    assert isinstance(result, AuthSession)
    response = JSONResponse(result.user)
    set_session_cookie(response, result.token, result.expires_at)
    return response


@router.get("/auth/credentials", response_model=None)
def credentials(request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _error("unauthenticated")
    rows = list_credentials(token, client_ip(request))
    if rows is None:
        return _error("unauthenticated")
    return JSONResponse({"credentials": rows})


@router.patch("/auth/credentials/{credential_id}", response_model=None)
def rename(credential_id: str, body: RenameIn, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _error("unauthenticated")
    result = rename_credential(token, client_ip(request), credential_id, body.nickname)
    if isinstance(result, str):
        return _error(result)
    return JSONResponse(result)


@router.delete("/auth/credentials/{credential_id}", response_model=None)
def remove(credential_id: str, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _error("unauthenticated")
    result = delete_credential(token, client_ip(request), credential_id)
    if result != "ok":
        return _error(result)
    return JSONResponse({"ok": True})


@router.post("/auth/sessions/revoke-all", response_model=None)
def revoke_all(request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _error("unauthenticated")
    if not revoke_all_sessions(token, client_ip(request)):
        return _error("unauthenticated")
    response = JSONResponse({"ok": True})
    clear_session_cookie(response)
    return response
