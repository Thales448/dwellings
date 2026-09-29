# Agents

An agent is not a person. It pairs with a one-time code, keeps a scoped token, and learns the hunt from `GET /api/v1/agent/manifest`. It can post and update listings. It cannot sign in to the UI or rate.

## Pair

An owner creates a code that lasts 10 minutes and works once:

`POST /api/v1/hunts/{hunt_id}/pairing-codes`

The code looks like `DWL-XXXX-XXXX`. The agent exchanges it, with no session cookie:

`POST /api/v1/agents/pair` with `{ "code", "name" }`

The response includes the token once (`dwl_agent_<id>_<secret>`), the hunt, the scopes, `mcp_url`, and `manifest_url`. Only the HMAC-SHA256 of the token is stored, keyed with `TOKEN_PEPPER`. A wrong or reused code counts toward 5 attempts, then the caller is locked out. Sending the token to a cookie route such as `/api/v1/me` does nothing.

## What to send

Title guide: 60 characters maximum, a human title, never a raw address. Example: `Elevator one-bed by the 7 in Sunnyside`.

Never delete a listing. `DELETE /api/v1/listings/{id}` sets status `dead` and keeps the row. A hard delete is admin-only with `?hard=true`.

Scopes are `listings:write`, `listings:read`, `ratings:read`, `learn:read`, and `digests:write`. A token is not a session.

## MCP

Streamable HTTP is at `/mcp`. This phase's tools are `get_manifest`, `post_listing`, `post_listings_bulk`, `update_listing`, `set_status`, `mark_checked`, `list_listings`, `get_listing`, and `add_comment`. Each description repeats the title guide and the never-delete rule. Photo, digest, and learn tools come later.

## Example

```bash
DWELLINGS_BASE_URL=http://127.0.0.1:8080 DWELLINGS_PAIR_CODE=DWL-... \
  python scripts/agent_example.py
```

The script pairs, reads the manifest, posts a listing, sends a heartbeat, marks it checked, marks it dead, and prints the row that is still present. It then posts another listing with an MCP client.
