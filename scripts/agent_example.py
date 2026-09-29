"""Pair an agent, post a listing, and prove a dead row is still there.

Also posts a second listing through the MCP streamable HTTP client.
"""

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request


def _request(method: str, url: str, body: dict[str, object] | None, token: str | None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise SystemExit(f"{method} {url} failed: {exc.code} {detail}") from exc
    return json.loads(raw) if raw else {}


def _listing(hunt_id: str, external_id: str, url: str) -> dict[str, object]:
    return {
        "hunt_id": hunt_id,
        "external_id": external_id,
        "url": url,
        "title": "Elevator one-bed by the 7",
        "listing_type": "couple",
        "unit_kind": "full_1br",
        "beds": 1,
        "price": 2800,
        "neighborhood": "Sunnyside",
        "geo_bucket": "sunnyside",
        "scam_risk_agent": "low",
        "source": "example",
    }


async def _mcp_post(base: str, token: str, hunt_id: str) -> str:
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx2.AsyncClient(headers=headers) as http:
        transport = streamable_http_client(f"{base}/mcp", http_client=http)
        async with Client(transport) as client:
            result = await client.call_tool(
                "post_listing",
                {
                    "listing": _listing(
                        hunt_id, "mcp-1", "https://example.com/dwellings/mcp-1"
                    )
                },
            )
    if result.is_error:
        raise SystemExit(f"mcp post failed: {result}")
    payload = result.structured_content
    if not isinstance(payload, dict) or payload.get("error"):
        raise SystemExit(f"mcp post failed: {payload}")
    listing = payload.get("listing")
    if not isinstance(listing, dict) or "id" not in listing:
        raise SystemExit(f"mcp post failed: {payload}")
    return str(listing["id"])


def main() -> None:
    base = os.environ["DWELLINGS_BASE_URL"].rstrip("/")
    code = os.environ["DWELLINGS_PAIR_CODE"]
    paired = _request(
        "POST",
        f"{base}/api/v1/agents/pair",
        {"code": code, "name": "hunt-nyc"},
        None,
    )
    token = str(paired["token"])
    hunt_id = str(paired["hunt"]["id"])
    guide = _request("GET", f"{base}/api/v1/agent/manifest", None, token)
    if guide["title_guide"]["max_characters"] != 60:
        raise SystemExit("manifest missing the title guide")
    if "never" not in guide["rules"]["never_delete"].lower():
        raise SystemExit("manifest missing the never-delete rule")
    created = _request(
        "POST",
        f"{base}/api/v1/listings",
        _listing(hunt_id, "example-1", "https://example.com/dwellings/example-1"),
        token,
    )
    listing_id = str(created["listing"]["id"])
    _request(
        "POST",
        f"{base}/api/v1/agent/heartbeat",
        {"status": "ok", "version": "example"},
        token,
    )
    _request("POST", f"{base}/api/v1/listings/{listing_id}/checked", {}, token)
    _request(
        "POST",
        f"{base}/api/v1/listings/{listing_id}/status",
        {"status": "dead", "reason": "gone"},
        token,
    )
    kept = _request("GET", f"{base}/api/v1/listings/{listing_id}", None, token)
    if kept.get("status") != "dead" or kept.get("id") != listing_id:
        raise SystemExit(f"dead listing was not kept: {kept}")
    print(f"still present {listing_id}")
    mcp_id = asyncio.run(_mcp_post(base, token, hunt_id))
    print(f"mcp posted {mcp_id}")


if __name__ == "__main__":
    try:
        main()
    except KeyError as exc:
        sys.exit(f"missing {exc}")
