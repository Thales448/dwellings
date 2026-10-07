from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.admin.service import create_person, list_feeds, list_people, replace_access
from app.auth.passwords import PasswordRejected
from app.core.config import get_settings
from app.core.security import client_ip

router = APIRouter(prefix="/api/v1/admin")


class GrantIn(BaseModel):
    hunt_id: str
    role: str = "viewer"
    agent_ids: list[str] | None = None


class PersonIn(BaseModel):
    email: str
    display_name: str
    password: str
    grants: list[GrantIn] = []


class AccessIn(BaseModel):
    grants: list[GrantIn]


def _token(request: Request) -> str | None:
    return request.cookies.get(get_settings().cookie_name)


def _error(result: str) -> JSONResponse:
    if result == "unauthenticated":
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    if result == "forbidden":
        return JSONResponse({"detail": "admin only"}, status_code=403)
    if result == "stale":
        return JSONResponse(
            {"detail": "sign in again to change access", "code": "step_up_needed"},
            status_code=403,
        )
    if result == "conflict":
        return JSONResponse({"detail": "that email already has an account"}, status_code=409)
    if result == "missing":
        return JSONResponse({"detail": "person not found"}, status_code=404)
    return JSONResponse({"detail": "check the feeds and agents"}, status_code=400)


def _grants(body: list[GrantIn]) -> list[dict[str, Any]]:
    return [grant.model_dump() for grant in body]


@router.get("/feeds", response_model=None)
def feeds(request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _error("unauthenticated")
    result = list_feeds(token, client_ip(request))
    if isinstance(result, str):
        return _error(result)
    return JSONResponse(result)


@router.get("/users", response_model=None)
def users(request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _error("unauthenticated")
    result = list_people(token, client_ip(request))
    if isinstance(result, str):
        return _error(result)
    return JSONResponse(result)


@router.post("/users", response_model=None)
def users_create(body: PersonIn, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _error("unauthenticated")
    result = create_person(
        token,
        client_ip(request),
        email=body.email,
        display_name=body.display_name,
        password=body.password,
        grants=_grants(body.grants),
    )
    if isinstance(result, PasswordRejected):
        return JSONResponse({"detail": str(result)}, status_code=400)
    if isinstance(result, str):
        return _error(result)
    return JSONResponse(result, status_code=201)


@router.put("/users/{user_id}/access", response_model=None)
def users_access(user_id: str, body: AccessIn, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _error("unauthenticated")
    result = replace_access(token, client_ip(request), user_id, _grants(body.grants))
    if isinstance(result, str):
        return _error(result)
    return JSONResponse(result)
