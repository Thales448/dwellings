from typing import Any
from urllib.parse import urlparse

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from app.agents.service import manifest as manifest_for
from app.core.request_ctx import set_authorization
from app.listings.service import (
    add_comment,
    bulk_listings,
    get_listing,
    list_listings,
    mark_checked,
    patch_listing,
    set_status,
    upsert_listing,
)

GUIDE = (
    "Title guide: 60 characters maximum, a human title, never a raw address. "
    "Never delete a listing: set status to dead and keep the row."
)

server = MCPServer("dwellings")


def _bind(ctx: Context) -> str:
    headers = {str(key).lower(): str(value) for key, value in (ctx.headers or {}).items()}
    set_authorization(headers.get("authorization"))
    forwarded = headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or "mcp"


def _result(value: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(value, str):
        return {"error": value}
    return value


@server.tool(description=f"Read the hunt manifest. {GUIDE}")
def get_manifest(ctx: Context) -> dict[str, Any]:
    return _result(manifest_for(_bind(ctx)))


@server.tool(description=f"Upsert one listing for this hunt. {GUIDE}")
def post_listing(ctx: Context, listing: dict[str, Any]) -> dict[str, Any]:
    return _result(upsert_listing(None, _bind(ctx), listing))


@server.tool(description=f"Upsert up to 200 listings. Per-row results. {GUIDE}")
def post_listings_bulk(
    ctx: Context, hunt_id: str, listings: list[dict[str, Any]]
) -> dict[str, Any]:
    body = {"hunt_id": hunt_id, "listings": listings}
    return _result(bulk_listings(None, _bind(ctx), body))


@server.tool(description=f"Partially update a listing. {GUIDE}")
def update_listing(ctx: Context, listing_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    return _result(patch_listing(None, _bind(ctx), listing_id, patch))


@server.tool(
    name="set_status",
    description=f"Change listing status. dead and rented keep the row. {GUIDE}",
)
def set_status_tool(
    ctx: Context, listing_id: str, status: str, reason: str | None = None
) -> dict[str, Any]:
    return _result(set_status(None, _bind(ctx), listing_id, status, reason))


@server.tool(name="mark_checked", description=f"Mark a listing checked and still listed. {GUIDE}")
def mark_checked_tool(ctx: Context, listing_id: str) -> dict[str, Any]:
    return _result(mark_checked(None, _bind(ctx), listing_id))


@server.tool(name="list_listings", description=f"List listings for this hunt. {GUIDE}")
def list_listings_tool(
    ctx: Context,
    hunt_id: str | None = None,
    presentable: str = "true",
    limit: int = 50,
) -> dict[str, Any]:
    query = {"presentable": presentable, "limit": str(limit)}
    if hunt_id:
        query["hunt_id"] = hunt_id
    return _result(list_listings(None, _bind(ctx), query))


@server.tool(name="get_listing", description=f"Fetch one listing by id or #short_id. {GUIDE}")
def get_listing_tool(
    ctx: Context, listing_ref: str, hunt_id: str | None = None
) -> dict[str, Any]:
    return _result(get_listing(None, _bind(ctx), listing_ref, hunt_id))


@server.tool(
    name="add_comment",
    description=f"Add a comment. Agent comments stay labelled as the agent. {GUIDE}",
)
def add_comment_tool(ctx: Context, listing_id: str, text: str) -> dict[str, Any]:
    return _result(add_comment(None, _bind(ctx), listing_id, text))


def http_app(public_url: str) -> Starlette:
    host = urlparse(public_url).hostname or "localhost"
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", host, f"{host}:*"],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", public_url.rstrip("/")],
    )
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=security,
        host="0.0.0.0",
    )
