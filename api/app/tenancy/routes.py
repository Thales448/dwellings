from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.core.security import client_ip
from app.tenancy.service import (
    create_hunt,
    get_hunt,
    invite_member,
    list_members,
    list_my_hunts,
    me,
    remove_member,
    update_hunt,
)

router = APIRouter(prefix="/api/v1")


class HuntIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    slug: str
    kind: str
    schema_name: str = Field(alias="schema")
    criteria: dict[str, Any] = {}
    rating_scale: int = 5
    rating_weights: dict[str, Any] = {}

    def payload(self) -> dict[str, Any]:
        data = self.model_dump()
        data["schema"] = data.pop("schema_name")
        return data


class HuntPatch(BaseModel):
    name: str | None = None
    criteria: dict[str, Any] | None = None
    rating_weights: dict[str, Any] | None = None


class InviteIn(BaseModel):
    role: str = "rater"
    email: str | None = None


def _token(request: Request) -> str | None:
    return request.cookies.get(get_settings().cookie_name)


def _access(result: str) -> JSONResponse:
    if result == "unauthenticated":
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    if result == "forbidden":
        return JSONResponse({"detail": "not allowed in this hunt"}, status_code=403)
    if result == "conflict":
        return JSONResponse({"detail": "slug already used"}, status_code=409)
    if result == "stale":
        return JSONResponse(
            {"detail": "step-up needed", "code": "step_up_needed"},
            status_code=403,
        )
    if result == "invalid":
        return JSONResponse({"detail": "invalid hunt request"}, status_code=400)
    return JSONResponse({"detail": "hunt not found"}, status_code=404)


@router.get("/me", response_model=None)
def current_user(request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _access("unauthenticated")
    result = me(token, client_ip(request))
    if result is None:
        return _access("unauthenticated")
    return JSONResponse(result)


@router.get("/hunts", response_model=None)
def hunts(request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _access("unauthenticated")
    result = list_my_hunts(token, client_ip(request))
    if result is None:
        return _access("unauthenticated")
    return JSONResponse({"hunts": result})


@router.post("/hunts", response_model=None)
def create(body: HuntIn, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _access("unauthenticated")
    result = create_hunt(token, client_ip(request), body.payload())
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result, status_code=201)


@router.get("/hunts/{hunt_id}", response_model=None)
def read_hunt(hunt_id: str, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _access("unauthenticated")
    result = get_hunt(token, client_ip(request), hunt_id)
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)


@router.patch("/hunts/{hunt_id}", response_model=None)
def patch_hunt(hunt_id: str, body: HuntPatch, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _access("unauthenticated")
    payload = body.model_dump(exclude_unset=True)
    result = update_hunt(token, client_ip(request), hunt_id, payload)
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)


@router.get("/hunts/{hunt_id}/members", response_model=None)
def members(hunt_id: str, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _access("unauthenticated")
    result = list_members(token, client_ip(request), hunt_id)
    if isinstance(result, str):
        return _access(result)
    return JSONResponse({"members": result})


@router.delete("/hunts/{hunt_id}/members/{user_id}", response_model=None)
def delete_member(hunt_id: str, user_id: str, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _access("unauthenticated")
    result = remove_member(token, client_ip(request), hunt_id, user_id)
    if result != "ok":
        return _access(result)
    return JSONResponse({"ok": True})


@router.post("/hunts/{hunt_id}/invites", response_model=None)
def invites(hunt_id: str, body: InviteIn, request: Request) -> JSONResponse:
    token = _token(request)
    if not token:
        return _access("unauthenticated")
    result = invite_member(
        token,
        client_ip(request),
        hunt_id,
        role=body.role,
        email=body.email,
    )
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result, status_code=201)
