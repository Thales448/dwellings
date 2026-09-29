from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.core.security import client_ip
from app.listings.service import (
    add_comment,
    bulk_listings,
    delete_listing,
    get_listing,
    list_listings,
    mark_checked,
    member_hunt_ids,
    patch_listing,
    set_status,
    stream_events,
    upsert_listing,
)

router = APIRouter(prefix="/api/v1")


class ListingIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    hunt_id: str
    url: str
    title: str
    price: float


class ListingPatch(BaseModel):
    model_config = ConfigDict(extra="allow")


class BulkIn(BaseModel):
    hunt_id: str
    listings: list[dict[str, Any]]


class StatusIn(BaseModel):
    status: str
    reason: str | None = None
    demotion_reason: str | None = None


class CommentIn(BaseModel):
    text: str


def _token(request: Request) -> str | None:
    return request.cookies.get(get_settings().cookie_name)


def _access(result: str) -> JSONResponse:
    if result == "unauthenticated":
        return JSONResponse({"detail": "sign in required"}, status_code=401)
    if result == "forbidden":
        return JSONResponse({"detail": "not allowed"}, status_code=403)
    if result == "conflict":
        return JSONResponse({"detail": "listing conflict"}, status_code=409)
    if result == "invalid":
        return JSONResponse({"detail": "invalid listing"}, status_code=400)
    return JSONResponse({"detail": "listing not found"}, status_code=404)


@router.post("/listings", response_model=None)
def create_listing(body: ListingIn, request: Request) -> JSONResponse:
    token = _token(request)
    result = upsert_listing(token, client_ip(request), body.model_dump())
    if isinstance(result, str):
        return _access(result)
    code = 201 if result["created"] else 200
    return JSONResponse(result, status_code=code)


@router.post("/listings/bulk", response_model=None)
def create_bulk(body: BulkIn, request: Request) -> JSONResponse:
    token = _token(request)
    result = bulk_listings(token, client_ip(request), body.model_dump())
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)


@router.get("/listings", response_model=None)
def index(request: Request) -> JSONResponse:
    token = _token(request)
    query = {key: value for key, value in request.query_params.multi_items()}
    result = list_listings(token, client_ip(request), query)
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)


@router.get("/listings/{listing_ref}", response_model=None)
def read_listing(listing_ref: str, request: Request, hunt_id: str | None = None) -> JSONResponse:
    token = _token(request)
    result = get_listing(token, client_ip(request), listing_ref, hunt_id)
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)


@router.patch("/listings/{listing_id}", response_model=None)
def update_listing(listing_id: str, body: ListingPatch, request: Request) -> JSONResponse:
    token = _token(request)
    result = patch_listing(
        token, client_ip(request), listing_id, body.model_dump(exclude_unset=True)
    )
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)


@router.post("/listings/{listing_id}/status", response_model=None)
def status(listing_id: str, body: StatusIn, request: Request) -> JSONResponse:
    token = _token(request)
    reason = body.demotion_reason or body.reason
    result = set_status(token, client_ip(request), listing_id, body.status, reason)
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)


@router.post("/listings/{listing_id}/checked", response_model=None)
def checked(listing_id: str, request: Request) -> JSONResponse:
    token = _token(request)
    result = mark_checked(token, client_ip(request), listing_id)
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)


@router.post("/listings/{listing_id}/comments", response_model=None)
def comment(listing_id: str, body: CommentIn, request: Request) -> JSONResponse:
    result = add_comment(_token(request), client_ip(request), listing_id, body.text)
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result, status_code=201)


@router.delete("/listings/{listing_id}", response_model=None)
def remove(listing_id: str, request: Request, hard: bool = False) -> JSONResponse:
    token = _token(request)
    result = delete_listing(token, client_ip(request), listing_id, hard=hard)
    if isinstance(result, str):
        return _access(result)
    return JSONResponse(result)


@router.get("/stream", response_model=None)
def stream(request: Request) -> StreamingResponse | JSONResponse:
    allowed = member_hunt_ids(_token(request), client_ip(request))
    if allowed is None:
        return _access("unauthenticated")
    return StreamingResponse(stream_events(allowed), media_type="text/event-stream")
