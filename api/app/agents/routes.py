from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.agents.service import (
    create_pairing_code,
    heartbeat,
    list_agents,
    manifest,
    pair_agent,
    revoke_agent,
    rotate_token,
)
from app.core.config import get_settings
from app.core.security import client_ip

router = APIRouter(prefix="/api/v1")


class PairIn(BaseModel):
    code: str
    name: str


class PairingIn(BaseModel):
    scopes: list[str] | None = None


class HeartbeatIn(BaseModel):
    status: str | None = None
    version: str | None = None
    next_run_at: str | None = None


def _token(request: Request) -> str | None:
    return request.cookies.get(get_settings().cookie_name)


def _access(result: str) -> JSONResponse:
    if result == "unauthenticated":
        return JSONResponse({"detail": "agent token required"}, status_code=401)
    if result == "forbidden":
        return JSONResponse({"detail": "not allowed"}, status_code=403)
    if result == "limited":
        return JSONResponse({"detail": "too many pairing attempts"}, status_code=429)
    if result == "invalid":
        return JSONResponse({"detail": "invalid pairing code"}, status_code=400)
    return JSONResponse({"detail": "not found"}, status_code=404)


@router.post("/hunts/{hunt_id}/pairing-codes", response_model=None)
def issue_code(hunt_id: str, body: PairingIn, request: Request) -> JSONResponse:
    result = create_pairing_code(_token(request), client_ip(request), hunt_id, body.scopes)
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result, status_code=201)


@router.post("/agents/pair", response_model=None)
def pair(body: PairIn, request: Request) -> JSONResponse:
    result = pair_agent(client_ip(request), body.code, body.name)
    if isinstance(result, str):
        code = 429 if result == "limited" else 400
        detail = "too many pairing attempts" if result == "limited" else "invalid pairing code"
        return JSONResponse({"detail": detail}, status_code=code)
    return JSONResponse(result, status_code=201)


@router.get("/agent/manifest", response_model=None)
def read_manifest(request: Request) -> JSONResponse:
    result = manifest(client_ip(request))
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)


@router.post("/agent/heartbeat", response_model=None)
def pulse(body: HeartbeatIn, request: Request) -> JSONResponse:
    result = heartbeat(client_ip(request), body.model_dump())
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)


@router.post("/agent/rotate-token", response_model=None)
def rotate(request: Request) -> JSONResponse:
    result = rotate_token(client_ip(request))
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)


@router.get("/hunts/{hunt_id}/agents", response_model=None)
def agents(hunt_id: str, request: Request) -> JSONResponse:
    result = list_agents(_token(request), client_ip(request), hunt_id)
    if isinstance(result, str):
        return _access(result)
    return JSONResponse({"agents": result})


@router.delete("/hunts/{hunt_id}/agents/{agent_id}", response_model=None)
def revoke(hunt_id: str, agent_id: str, request: Request) -> JSONResponse:
    result = revoke_agent(_token(request), client_ip(request), hunt_id, agent_id)
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)
