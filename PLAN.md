# Dwellings — architecture & build plan

**Target:** `https://dwellings.rtech.cloud`, served by one Docker image on the rtech.cloud server.
**How to use this file:** it is both the plan and the prompt. Give it, plus the link to the design canvas (Feed, Wall, Mobile, Sign in, Settings), to your coding agent in an empty `dwellings` repo. Tell the agent: *"Build Dwellings exactly as specified in this file, phase by phase. Commit after each phase and don't advance until that phase's checks pass."*

The plan runs top-down, from the system context to the single image.

---

## 0. Principles (the agent must not violate these)

1. **Photos lead.** Every view is image-first. Every listing has a human title of 60 characters or less, in the pattern "Elevator One-Bed by the 7 in Sunnyside". Raw addresses like "51st STREET, Sunnyside, NY 11377" are never used as titles.
2. **Never delete rows.** Gone listings keep `unavailable_date` and all their history, photos and ratings. The agent's `DELETE` means "no longer available". A hard delete is admin-only, needs `?hard=true`, and is audited.
3. **Multi-tenant from day one.** Many users and many **hunts** share one install. For example, "NYC · Couple" (a rental hunt with two raters) and "Texas · Investment" (a purchase hunt with one owner). Every row is scoped to a hunt. A user sees only the hunts they belong to. An agent can touch only its own hunt.
4. **Agents are first-class but never human.** An agent pairs itself with a one-time code. It then gets a scoped token and discovers everything it needs from a manifest. It can post, edit, re-check and mark listings gone, and it can read what the humans liked. It can never sign in to the UI or rate as a person.
5. **Scam safety is visible.** Every listing carries a scam risk: the agent's view merged with server checks. A high risk shows a red "Likely scam" banner, and the listing is hidden from the default feed.
6. **One image, one volume.** API, UI, MCP, background jobs and the database all live in one container. All state lives under `/data`.

---

## 1. System context (L0)

```
 ┌──────────── humans ────────────┐      ┌──────────── agents ────────────┐
 │ Orpheus (phone: Face ID,       │      │ hunt-nyc  (NYC · Couple)       │
 │   laptop: Touch ID, YubiKey)   │      │ hunt-tx   (Texas · Investment) │
 │ Partner (phone passkey)        │      │ …any future agent              │
 │ Other users on other hunts     │      │ REST or MCP, bearer token      │
 └──────────────┬─────────────────┘      └───────────────┬────────────────┘
                │ HTTPS (session cookie, WebAuthn)       │ HTTPS (Bearer dwl_agent_…)
                ▼                                        ▼
        ┌─────────────────── dwellings.rtech.cloud ───────────────────┐
        │ reverse proxy on rtech.cloud (TLS) → container :8080        │
        │ ┌─────────────────── dwellings image ─────────────────────┐ │
        │ │ Uvicorn/FastAPI: /  (SPA)  /api/v1  /mcp  /api/v1/stream │ │
        │ │ in-process job runner (photos, scam checks, learning)   │ │
        │ │ SQLite (WAL) + photo store  ──►  /data volume           │ │
        │ └─────────────────────────────────────────────────────────┘ │
        └─────────────────────────────────────────────────────────────┘
                ▲ agents fetch listing pages themselves; the server only
                  fetches photo URLs the agent hands it (or accepts uploads)
```

The agents run wherever you run them, for example the Deepmind dev server or a cron on EARTH. Dwellings is the system of record and the rating UI. It never scrapes portals itself.

## 2. Containers & processes (L1) — all inside one image

| Piece | Tech | Role |
|---|---|---|
| Web app | SvelteKit (`adapter-static`), TypeScript | Built at image build time, served by FastAPI at `/` |
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic | REST under `/api/v1`, SSE at `/api/v1/stream` |
| MCP | Official Python MCP SDK, streamable HTTP, mounted at `/mcp` | The same service layer as REST, exposed as tools |
| Jobs | In-process asyncio runner over a `jobs` table (no Redis) | Photo fetch/resize, scam checks, nightly learning, stale re-check queue |
| DB | SQLite in WAL mode at `/data/dwellings.db` | `DATABASE_URL` may point at Postgres later without code changes |
| Files | `/data/photos/{hunt}/{listing}/{sha}_{size}.webp` | Served with immutable cache headers, behind the session check |
| Auth | `webauthn` (py_webauthn), `argon2-cffi`, server-side sessions | Passkeys + passwords, per-device sessions |

## 3. Components (L2)

```
api/app/
  core/        config, db, security (cookies, CSRF/Origin check, rate limits), audit
  auth/        passwords, webauthn, sessions, invites, recovery
  tenancy/     users, hunts, memberships, permission checks (one dependency: require(hunt, role|scope))
  agents/      pairing, tokens, manifest, heartbeat
  listings/    ingest + normalize, dedupe, presentable rules, status machine, titles
  photos/      fetch, upload, resize, blurhash, sha256 + perceptual hash
  scam/        signal detectors, risk merge, overrides
  ratings/     per-user ratings, tags, comments, pipeline (tour → signed), saved/hidden
  learn/       preference stats, per-hunt model, predicted_rating, agent "learn" payload
  digests/     digest runs and membership (8am / 1pm / 6pm packs)
  events/      event log + SSE fan-out
  importers/   hunt-export CSV + imessage-id-map.json
  mcp/         tool definitions → service layer
  jobs/        runner, schedules
```

Rule: route handlers are thin. **All** permission checks go through `tenancy.require(...)`, and all writes go through services that emit an event.

## 4. Data model (L3)

Multi-tenant core:

- **users** — `id`, `email` (unique, citext), `display_name`, `password_hash` (nullable: passkey-only users allowed), `is_admin`, `require_passkey` (bool), `created_at`, `disabled_at`.
- **webauthn_credentials** — `id` (credential id), `user_id`, `public_key`, `sign_count`, `transports`, `aaguid`, `backup_eligible`, `backup_state`, `nickname` ("iPhone · Face ID"), `created_at`, `last_used_at`.
- **sessions** — `id` (store only the sha256 of the cookie value), `user_id`, `device_label`, `user_agent`, `ip_first`, `ip_last`, `auth_method` (`passkey` | `password`), `created_at`, `last_seen_at`, `expires_at`, `trusted_until`, `revoked_at`.
- **invites** — `token_hash`, `hunt_id` (nullable), `role`, `email` (optional), `expires_at`, `used_by`, `used_at`.
- **hunts** — `id`, `slug`, `name` ("NYC · Couple"), `kind` (`rental` | `purchase`), `schema` (`nyc-rental-v1`, `tx-purchase-v1`, …), `criteria` (JSON: ceilings, bands, unit kinds, geo buckets, commute anchor), `rating_scale` (5 or 10), `rating_weights` (JSON, e.g. `{"orpheus": 0.5, "partner": 0.5}`), `created_by`.
- **hunt_members** — `hunt_id`, `user_id`, `role` (`owner` | `rater` | `viewer`), `rater_label` ("You", "Partner").
- **agents** — `id`, `hunt_id`, `name` ("hunt-nyc"), `token_hash`, `token_prefix` (first 8 chars, shown in UI), `scopes` (`listings:write`, `listings:read`, `ratings:read`, `learn:read`, `digests:write`), `created_by`, `created_at`, `last_seen_at`, `last_ip`, `revoked_at`.
- **pairing_codes** — `code_hash`, `hunt_id`, `scopes`, `created_by`, `expires_at` (10 min), `used_at`, `agent_id`.

Listings (common columns + a validated kind-specific `attrs`):

- **listings** — `id` (uuid), `hunt_id`, `short_id` (int; unique per hunt and stable forever; imported from `imessage-id-map.json`, new ones take max+1), `external_id` (`csv_id`: `cl-…`, RentHop id…, unique per hunt), `url` (normalized, unique per hunt), `source`, `title`, `status` (`new` | `alive` | `watching` | `dead` | `rented` | `scam` | `demoted`), `first_seen`, `last_seen`, `unavailable_date`, `availability_checked_at`, `listing_type` (`couple` | `roommate` | `room`), `unit_kind` (`full_studio` | `full_1br` | `full_2br_plus` | `room` | `multi` | `unknown`), `beds` (float, normalized from 0/0.0/1/1.0/"1BR"), `beds_label`, `baths` (float), `price` (rent, or list price for purchase), `price_per_person`, `address`, `address_precision` (`exact` | `street` | `area`), `neighborhood`, `borough_or_city`, `geo_bucket`, `lat`, `lng`, `hunt_score` (the agent's 0–10), `fit_reasons` (json list ≤ 5), `honesty_flags` (json list of an enum: `bait_pricing`, `title_beds_mismatch`, `short_term`, `sublet`, `furnished`, `rent_stabilized_claim`, `kitchen_unverified`, `provisional_ri`, `soft_address`, `broker_fee_unclear`), `notes` (the honesty blob), `demoted`, `demotion_reason` (enum + free text: `room`, `2br`, `bait`, `dup`, `out_of_geo`, `basement`, `other`), `scam_risk_agent` (`low` | `medium` | `high` | null), `scam_notes`, `scam_risk` (merged, see §6), `is_presentable` (computed, stored, indexed), `source_snapshot` (json: title and price at first sight), `days_on_market`, `attrs` (json, validated against the hunt's schema), `created_by_agent`, `created_at`, `updated_at`.
- `attrs` for **`nyc-rental-v1`**: `subway` (text), `commute_lines[]`, `commute_gct_minutes` (int, estimate), `east_side_access` (`strong` | `ok` | `weak` | `unverified`), `is_roosevelt_island`, `budget_band` (`standard_≤3000` | `ri_stretch_≤4000`), `kitchen_status` (`ok` | `unverified` | `small` | `old` | `unknown`), `amenities[]`, `amenity_flags` {`laundry`: `in_unit` | `building` | `no`, `doorman`, `elevator`, `outdoor`, `gym`: `yes` | `no` | `unknown`}, `building_year`, `newer_building`, `furnished`, `short_term`, `sublet`.
- `attrs` for **`tx-purchase-v1`** (a stub for now, but it must validate): `list_price`, `hoa_monthly`, `tax_annual`, `est_rent`, `cap_rate`, `lot_sqft`, `year_built`, `property_type`, `school_rating`, `flood_zone`.
- **photos** — `id`, `listing_id`, `position`, `origin` (`url` | `upload`), `original_url`, `sha256`, `phash` (64-bit perceptual hash), `width`, `height`, `blurhash`, `caption`, `is_cover`, `shows_kitchen` (nullable; the agent can tag it).

Human layer (per user unless noted):

- **ratings** — `listing_id`, `user_id`, `stars` (1–5, or 1–10 if the hunt says so), `tags[]` (`kitchen`, `light`, `size`, `noise`, `building`, `commute`, `price`, `vibe`), `note`, `updated_at`. Unique on (`listing_id`, `user_id`). `combined_rating` is computed from the hunt's weights, never stored as truth.
- **listing_user_state** — `saved`, `hidden`, `compared`, `last_viewed_at` (per user).
- **pipeline** (per listing, shared by the hunt) — `tour_interest` (`skip` | `maybe` | `tour` | `applied` | `offer` | `signed`), `toured_at`, `application_status`, `updated_by`.
- **comments** — `id`, `listing_id`, `author_user_id` **or** `author_agent_id`, `text`, `created_at`.
- **scam_signals** — `listing_id`, `detector`, `severity` (`info` | `warn` | `high`), `message`, `evidence` (json), `created_at`. **scam_overrides** — `listing_id`, `user_id`, `verdict` (`not_scam` | `confirmed_scam`), `note`.
- **digest_runs** — `id`, `hunt_id`, `slot` (`8am` | `1pm` | `6pm`), `ran_at`; **digest_items** — `digest_run_id`, `listing_id`, `position`.
- **events** — `id`, `hunt_id`, `listing_id`, `type`, `actor_type` (`user` | `agent` | `system`), `actor_id`, `payload`, `at`. This feeds the Trail panel, SSE and the audit log.
- **learned_profiles** — `hunt_id`, `computed_at`, `summary_text`, `stats` (json), `model` (json coefficients), `n_ratings`. **predictions** — `listing_id`, `predicted_rating`, `explanations[]`.
- **jobs** — `id`, `kind`, `payload`, `run_after`, `attempts`, `last_error`, `done_at`.

**Presentable rule** (evaluated from `hunts.criteria`, recomputed on every write). For NYC · Couple, a listing is presentable only if all of these hold:

- status is in {new, alive, watching}
- `listing_type = couple`
- `unit_kind` is in {full_studio, full_1br}
- not demoted
- `scam_risk` ≠ high
- `unavailable_date` is null
- `geo_bucket` is not `out_of_scope`
- price ≤ $3,000, or (Roosevelt Island and price ≤ $4,000)

Hidden items stay reachable through filters.

## 5. API (L4) — `/api/v1`

**Auth for humans** (all under `/auth`):

- `POST /auth/password/login` → session. Rate-limited by IP and account; failures cost the same time whether or not the account exists. If `require_passkey` is set, a password alone yields a "step-up needed" response.
- `POST /auth/passkey/options` → `POST /auth/passkey/verify`. Uses discoverable credentials (username-less), `userVerification: required`, `rpId: dwellings.rtech.cloud`, and `origin: https://dwellings.rtech.cloud`.
- `POST /auth/passkey/register/options` → `…/register/verify`. Requires an existing session younger than 10 minutes. Nicknamed per device.
- `GET /auth/sessions`, `DELETE /auth/sessions/{id}`, `POST /auth/sessions/revoke-others`.
- `GET /auth/credentials`, `PATCH` (rename), `DELETE` (not allowed if it's the last way to sign in).
- `POST /auth/password` (set or change; requires a recent session).
- `POST /auth/invite/accept` (create an account from an invite; the user sets a password and/or registers a passkey).
- Recovery: `dwellings admin reset-link <email>` (CLI inside the container) prints a one-time 30-minute link. No email dependency.

**Tenancy:** `GET /me`, `GET /hunts`, `POST /hunts`, `PATCH /hunts/{id}` (criteria, weights), `POST /hunts/{id}/invites`, `GET/DELETE /hunts/{id}/members/{user}`.

**Agent lifecycle:**

- `POST /hunts/{id}/pairing-codes` (owner) → `{ code: "DWL-7KQ4-M2XP", expires_at }`.
- `POST /agents/pair` (no auth; rate-limited hard) with `{ code, name }` → `{ agent_id, token, hunt, scopes, mcp_url, manifest_url }`. The token is shown once and stored only as a hash.
- `GET /agent/manifest` (agent) → the hunt name and kind, the `criteria`, the attrs JSON Schema, the enums, the title guide with examples, the rules ("never delete", presentable rule), rate limits, and endpoint and tool lists. **This is how the agent learns to use the site on its own.**
- `POST /agent/heartbeat` → `{ status, version, next_run_at }` (drives the pulse in the top bar).
- `POST /agent/rotate-token`; owners can `DELETE /hunts/{id}/agents/{agent}` (revoke).

**Listings:**

| Method & path | Who | Does |
|---|---|---|
| `POST /listings` | agent | Upsert by (`hunt`, `external_id`), then by normalized `url`. Normalizes beds, validates `attrs`, and sets `short_id` if new. Accepts `photos: [{url, caption, shows_kitchen}]`. Returns `201`, or `200` with `duplicate: true`. Queues photo and scam jobs. |
| `POST /listings/bulk` | agent | Up to 200 listings; per-row results. For digest runs and imports. |
| `PATCH /listings/{id}` | agent, owner | Partial update. Price changes append to history and trigger a bait-drift check. |
| `POST /listings/{id}/photos` | agent, owner | Multipart upload, for portals that return 403 on hotlinks. |
| `POST /listings/{id}/status` | agent, owner | `{status, reason}`. `dead`/`rented` set `unavailable_date`. `demoted` requires `demotion_reason`. |
| `DELETE /listings/{id}` | agent | Sets status `dead` with reason "deleted by agent". Keeps everything. |
| `DELETE /listings/{id}?hard=true` | admin | Real delete, audited. |
| `POST /listings/{id}/checked` | agent | Still live: bumps `last_seen` and `availability_checked_at`. |
| `GET /listings` | member, agent | Filters `presentable` (default true), `status`, `unrated_by=me`, `tour_interest`, `scam_risk`, `geo_bucket`, `unit_kind`, `min/max_price`, `flag`, `q`. Sorts: `hunt_score` \| `predicted` \| `combined` \| `newest` \| `price`. Cursor-paginated. |
| `GET /listings/{id or #short_id}` | member, agent | Full record: photos, everyone's ratings, pipeline, comments, scam signals, events. |
| `PUT /listings/{id}/rating` | member | `{stars, tags, note}` — "post likes". Agents get `403`. |
| `PUT /listings/{id}/pipeline` | member | Tour interest and application status. |
| `PUT /listings/{id}/state` | member | Saved, hidden, compared. |
| `POST /listings/{id}/comments` | member, agent | An agent comment is labelled as the agent's in the UI. |
| `POST /listings/{id}/scam-override` | member | `not_scam` or `confirmed_scam`. |
| `POST /digests` | agent | `{slot, listing_ids[]}` records which pack included what. |
| `GET /agent/learn` | agent | See §7. |
| `GET /agent/recheck?older_than=24h` | agent | Presentable listings not re-verified recently. |
| `GET /stream` | member | SSE: `listing.created`, `listing.updated`, `listing.status`, `rating.updated`, `agent.heartbeat`. |
| `GET /health` | public | DB, disk, job lag. |

**MCP tools** (the same services, the same scopes): `get_manifest`, `post_listing`, `post_listings_bulk`, `update_listing`, `attach_photos`, `set_status`, `mark_checked`, `list_listings`, `get_listing`, `add_comment`, `record_digest`, `get_learning`, `get_recheck_queue`. Each tool's description embeds the title guide and the never-delete rule.

**Importer:** `dwellings import --hunt nyc-couple --csv hunt-export.csv --id-map imessage-id-map.json [--dry-run]` maps every column in the export:

- `score` → `hunt_score`
- `rent` → `price`
- `borough` → `borough_or_city`
- kitchen, demotion, RI provisional and furnished/short-term/sublet notes are parsed out of `notes` into the structured fields where the patterns are unambiguous, and left in `notes` otherwise

Idempotent. Prints a diff summary.

## 6. Scam check

`scam_risk` is the maximum of the agent's `scam_risk_agent` and the server detectors. A user override then applies: `not_scam` caps the risk at `low`, and `confirmed_scam` forces `high` and sets status `scam`. Detectors run on create, on price or text change, and on photo arrival. Each one writes a `scam_signals` row with human-readable evidence.

| Detector | Fires when | Severity |
|---|---|---|
| `price_outlier` | Price is more than 35% below the hunt's 90-day median for the same `geo_bucket` + `unit_kind`, with at least 8 comparables. Otherwise it falls back to a per-hunt static floor from `criteria`. | high if >45%, warn if 35–45% |
| `photo_reuse` | The same `sha256`, or a pHash Hamming distance ≤ 6, matches a photo on a different listing (any hunt), especially a different address or an older post | high |
| `payment_before_viewing` | Text contains patterns like: deposit/hold + Zelle/Venmo/CashApp/wire/gift card/crypto before viewing; "keys by mail"; "I'm overseas/out of the country"; "WhatsApp only" | high |
| `bait_drift` | The price rose more than 10%, or beds dropped, compared with `source_snapshot` | warn |
| `title_beds_mismatch` | Title/text says 1BR but the agent's `unit_kind` or beds say studio/room (and vice versa) | warn |
| `contact_mismatch` | The claimed broker or management domain doesn't match the contact | warn |
| `too_good_bundle` | Three or more of: under market + in-unit laundry + doorman + renovated + no fee | warn |
| `agent_flag` | The agent sent `scam_risk_agent` and `scam_notes` | as sent |

In the UI, the Feed's right column shows a **Scam check** card: a Low risk / Check / Likely scam pill, then each detector as a check or a warning with its one-line evidence. On high risk there is a red banner across the photo: "Likely scam — don't send money or documents before an in-person viewing." The Wall shows a red footer strip on the card and a **Flagged** filter chip. Two buttons, "Not a scam" and "Confirm scam", write overrides, and those overrides are fed to learning.

## 7. Learning loop

A nightly job, plus one triggered after every 10 new ratings, computes this per hunt:

1. **Stats:** mean combined rating overall and per member. For every boolean/enum attribute, amenity, honesty flag and rating tag: count, mean rating with vs without, and lift. It also computes preferred ranges (the 25th–75th percentile of price and `commute_gct_minutes` among listings rated 4 or higher), the most common demotion reasons, and the scam overrides.
2. **Model:** ridge regression, numpy only, over one-hot and scaled features → `predicted_rating` and the top three contributing features for each unrated listing. It isn't trained until at least 15 ratings exist; until then the prediction is null.
3. **Summary text:** a short template-built sentence, shown in Settings and sent to the agent (e.g. "You both rate confirmed kitchens and sub-15-minute Grand Central commutes highest; walk-ups and unverified kitchens drag scores down").

`GET /agent/learn` returns:

- `summary_text`
- `stats`
- `model_features` (weights)
- `examples`: the 5 highest- and 5 lowest-rated listings, with attributes, tags, notes and member comments, as few-shot examples
- `recent_comments`
- `scam_overrides`
- `do_more_of` and `do_less_of` lists

The agent is expected to call this before every run.

The UI shows "You'd likely rate 4.2" on unrated cards once the model exists, and **Sort · Predicted** becomes available.

## 8. UI (L5) — match the design canvas exactly

**Tokens:**

- Ground `#0F0E0C`, surface `#191815`, raised `#221F1B`, line `#2A2824`
- Text `#F3EFE7`, muted `#A39E93`
- Love/rating `#E8845C`, available/OK `#8FB996`, warn `#E0B45A`, danger `#E5484D` (danger text on dark `#F07D80`)
- Fonts: Fraunces (titles, wordmark in italic), Instrument Sans (UI), JetBrains Mono (numbers, IDs)
- Icons are 1.8px stroke SVG. No emoji. Touch targets are at least 44px.

**Screens:**

- **Sign in:** a split layout with a photo on the left. On the right, a primary **Sign in with a passkey** button that triggers the browser's conditional mediation (autofill UI) on load, a password form, and a "Trust this device for 30 days" checkbox. After a password sign-in, a sheet offers "Add a passkey for this device".
- **Feed (`/h/{hunt}`):**
  - Top bar: wordmark, **Hunt switcher**, Feed/Wall/Tours/Gone tabs, the agent pulse (name, last digest slot, time since the last heartbeat), the unrated count, and an avatar that links to Settings.
  - Left rail: presentable queue with the `#short_id` on each thumb, rent, neighborhood and a tag (New / You 4/5 / Likely scam / Gone · kept), plus a footnote listing what's hidden by default.
  - Center column: a photo stage with `#id`, hunt score and photo-count chips and amenity chips over the photo. Below it, the neighborhood, subway and first-seen line, then a 42px title.
  - Stat strip: Rent, Unit, To GCT, Kitchen (colored by status) and Budget (amber for RI stretch).
  - Rating row: your stars, "Partner · Combined", the Skip/Maybe/Tour/Applied segmented control and prev/next.
  - "Tag why" chips under the rating row.
  - Right column: the Scam check card, "Why it fits", Honesty flags with the notes blob, the Trail (first seen with digest slot, last checked, status) and an "Open on {source}" link.
- **Wall:** a headline that reflects state; chips for Presentable / Unrated / Tour / Flagged / Gone / Sort; a four-column masonry grid of cards. Each card has a photo, a hunt-score chip, a love badge, a red "Likely scam" strip or a "No longer available" stamp, then `#id · neighborhood`, the title, and "price · unit · commute".
- **Mobile:** a full-bleed photo with story-style progress bars and a bottom sheet (title, chips, pitch, and Pass · stars · Love). Swipe left to skip, right to love, up for details.
- **Settings:**
  - Hunts list and a "+ New hunt" option.
  - Criteria chips.
  - An **Agents** card: status dot, scopes, post count, last seen, Revoke, and **Connect an agent**, which shows the pairing code, its countdown and the `curl` snippet.
  - **Members** (invite by link) and a "What the agent has learned" summary.
  - **Devices & passkeys:** a card per credential and per session (this device, trusted-until), "Add a passkey", "Sign out all sessions", and a Password card.
  - Admin (for `is_admin` only): users and a disable/enable toggle.

**Keyboard shortcuts:**

| Key | Action |
|---|---|
| J/K or ↓/↑ | Next / previous listing |
| ←/→ | Photos |
| 1–5 | Stars |
| T | Cycle tour interest |
| S | Save |
| H | Hide |
| G | Mark gone (confirm) |
| `#` then digits | Jump to a short ID |
| / | Search |

Ratings are optimistic and roll back on error. New-drop toasts arrive over SSE.

## 9. Security (L6)

- **Passkeys:** WebAuthn with the RP ID `dwellings.rtech.cloud` (passkeys are bound to that name; changing the domain means re-enrolling). Resident keys are preferred, user verification is required, and sign counts are checked. Several credentials per user are allowed, one per device plus a hardware key as backup.
- **Passwords:** Argon2id (`m=64MiB, t=3, p=1`), minimum 12 characters, checked against a bundled top-100k breached list. Lockout uses exponential backoff per account and per IP.
- **Sessions:** an opaque 256-bit token in `__Host-dwl` (Secure, HttpOnly, SameSite=Lax, Path=/). Only its hash is stored. The idle timeout is 12h, or 30 days if the device is trusted. There's a listing of sessions per device and the ability to revoke them. Re-auth (step-up) is required for security changes if the session is older than 10 minutes.
- **CSRF:** every state-changing cookie request checks `Origin` against `PUBLIC_URL` and a double-submit token header.
- **Agents:** tokens look like `dwl_agent_<id>_<43 chars>` and are stored as HMAC-SHA256 with a server pepper. They're scoped to one hunt and their scopes, rate-limited (for example 120 writes a minute), and never accepted on cookie routes. Pairing codes are single-use, last 10 minutes, have 5 attempts, and are stored hashed.
- **Tenancy:** every query is filtered by `hunt_id`. Tests assert that user A can't read hunt B and that agent NYC can't write to hunt TX.
- **Photo fetch hardening:** SSRF protection (resolve and block private, link-local and loopback ranges, allow only http/https, 15 MB and 20s caps, content-type sniffing). EXIF data is stripped.
- **Headers:** strict CSP (self only, plus Google Fonts), HSTS, `frame-ancestors 'none'`, `Referrer-Policy: same-origin`.
- **Bootstrap:** on first start with an empty DB, `ADMIN_EMAIL` + `ADMIN_BOOTSTRAP_TOKEN` enable a one-time `/setup` page. After that, sign-up is by invite only.
- **Audit:** every auth event, agent pairing, revoke, hard delete and status change is recorded in `events`.

## 10. Repository layout

```
dwellings/
├── PLAN.md                      # this file
├── AGENTS.md                    # how an agent pairs, reads the manifest, posts, learns (generated from the manifest + examples)
├── README.md                    # run, configure, back up, upgrade
├── Dockerfile
├── compose.yaml                 # optional: the same image with a volume and env
├── .env.example
├── Makefile                     # dev, test, lint, build, run, import, backup
├── api/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   ├── app/ (core, auth, tenancy, agents, listings, photos, scam, ratings, learn, digests, events, importers, mcp, jobs, main.py, cli.py)
│   └── tests/ (auth, webauthn (virtual authenticator), tenancy isolation, agents & pairing, listings upsert/status/never-delete, scam detectors, learning, importer, SSRF)
├── web/
│   ├── package.json, svelte.config.js, vite.config.ts
│   └── src/
│       ├── app.css (tokens), app.html
│       ├── lib/ (api.ts, auth.ts [WebAuthn helpers], stores.ts, sse.ts, keys.ts, components/…)
│       └── routes/ (login, setup, invite/[token], h/[hunt] (feed), h/[hunt]/wall, h/[hunt]/l/[short_id], settings/…)
├── scripts/
│   ├── seed.py                  # NYC · Couple with 8 listings (one gone, one likely scam) + an empty Texas hunt
│   └── agent_example.py         # pair → manifest → post → attach photos → checked → learn → mark dead
└── data/                        # gitignored
```

## 11. Build phases

Each phase is one PR-sized chunk and must pass its checks before the next begins.

1. **Skeleton.** The repo, FastAPI app, SvelteKit shell with tokens, Dockerfile, `/health` and CI (`ruff`, `mypy`, `pytest`, `svelte-check`, `vitest`). *Check:* `docker build` succeeds and `/health` returns 200.
2. **Identity.** Users, password auth, sessions, CSRF, bootstrap `/setup`, invites, and the Sign-in screen. *Check:* sign in, sign out, and session list/revoke work, and the lockout test passes.
3. **Passkeys.** Register and authenticate, conditional UI, device cards, step-up, and the "last credential" guard. *Check:* py_webauthn tests pass with a virtual authenticator, and it works in a browser with Face ID/Touch ID over HTTPS.
4. **Tenancy.** Hunts, members, roles, the hunt switcher, and an isolation test suite. *Check:* cross-hunt reads and writes return 404/403.
5. **Listings core.** Schema, `attrs` validation per hunt schema, normalization, upsert/dedupe, the status machine with never-delete, the presentable rule, short IDs, events, and SSE. *Check:* the upsert, status and presentable tests pass.
6. **Agents.** Pairing codes, the pair endpoint, tokens and scopes, manifest, heartbeat, MCP mount, and `AGENTS.md`. *Check:* `agent_example.py` pairs and posts end to end, and so does an MCP client.
7. **Photos.** Fetch and upload, SSRF guard, WebP sizes, blurhash, sha256 + pHash, and cover selection. *Check:* a mocked fetch works, SSRF tests pass, and duplicate images are detected.
8. **Feed, Wall and Mobile UI** pixel-matched to the canvas, with keyboard shortcuts, optimistic ratings, pipeline, tags, comments and toasts. *Check:* manual review against the canvas; Lighthouse accessibility and performance are both 90 or higher.
9. **Scam check.** All detectors, merge and overrides, the banner, card, Wall strip and Flagged filter. *Check:* each detector has a positive and a negative fixture.
10. **Learning.** Stats, the ridge model, predictions, `/agent/learn`, the Settings summary and predicted sort. *Check:* on synthetic ratings, the model ranks the planted preference first.
11. **Importer + digests.** CSV and ID-map import, bulk upsert, and digest runs. *Check:* importing the real export twice produces no diff the second time.
12. **Ops.** Backups, the admin CLI, structured logs, `/metrics` (Prometheus text), and README. *Check:* a restore from backup to a fresh container works.

## 12. The single image (L7)

**Dockerfile** (multi-stage):

```dockerfile
# 1 — build the web app
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ .
RUN npm run build            # → /web/build

# 2 — build Python wheels
FROM python:3.12-slim AS py
WORKDIR /api
RUN pip install --no-cache-dir uv
COPY api/pyproject.toml api/uv.lock ./
RUN uv export --frozen --no-dev > req.txt && pip wheel --no-cache-dir -r req.txt -w /wheels

# 3 — runtime
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libwebp7 tini sqlite3 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -r -u 10001 -d /data dwellings
COPY --from=py /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
WORKDIR /app
COPY api/ /app/
COPY --from=web /web/build /app/static
ENV DATA_DIR=/data DATABASE_URL=sqlite:////data/dwellings.db PORT=8080 PYTHONUNBUFFERED=1
VOLUME ["/data"]
USER dwellings
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health').status==200 else 1)"
ENTRYPOINT ["tini","--"]
CMD ["sh","-c","python -m app.cli migrate && exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips='*' --workers 1"]
```

Why one worker: SQLite has a single writer, and the job runner and SSE fan-out live in-process. Scale vertically; move to Postgres (just change `DATABASE_URL`) before running more than one replica.

**Run on the rtech.cloud server:**

```bash
docker volume create dwellings-data
docker run -d --name dwellings --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -v dwellings-data:/data \
  --env-file /etc/dwellings.env \
  ghcr.io/<you>/dwellings:latest
```

`/etc/dwellings.env`:

```
PUBLIC_URL=https://dwellings.rtech.cloud
WEBAUTHN_RP_ID=dwellings.rtech.cloud
WEBAUTHN_RP_NAME=Dwellings
SECRET_KEY=<64 random bytes, base64>
TOKEN_PEPPER=<64 random bytes, base64>
ADMIN_EMAIL=you@example.com
ADMIN_BOOTSTRAP_TOKEN=<random, used once>
PHOTO_MAX_PER_LISTING=40
PHOTO_FETCH_TIMEOUT=20
TRUSTED_PROXIES=127.0.0.1
```

**TLS and proxy:** point `dwellings.rtech.cloud` at the server and terminate TLS in whatever already fronts rtech.cloud. The proxy must pass `X-Forwarded-Proto`/`X-Forwarded-For` and must not buffer `/api/v1/stream` (SSE). A Caddy example:

```
dwellings.rtech.cloud {
  reverse_proxy 127.0.0.1:8080 {
    flush_interval -1
  }
}
```

WebAuthn **only works over HTTPS on that exact hostname**, so test passkeys there, not on a LAN IP.

**Backups:** `docker exec dwellings python -m app.cli backup /data/backups/$(date +%F).db` runs SQLite `.backup` and writes a photos manifest. Rsync `/data` (or the volume) nightly to the NAS. Optionally add Litestream to an S3-compatible bucket later; it's the same image plus one env var.

**Upgrades:** `docker pull` then `docker rm -f dwellings && docker run …`. Migrations run on start and are backward-compatible for one release.

**First boot:**

1. Open `/setup?token=…` and create the admin with a password.
2. Add a passkey on your phone and one on your laptop.
3. Create the hunt "NYC · Couple" (schema `nyc-rental-v1`, criteria as §4).
4. Invite your partner.
5. Run `dwellings import …` with your current export and ID map.
6. Generate a pairing code, have hunt-nyc call `POST /api/v1/agents/pair`, and save its token.
7. Repeat steps 3 and 6 for "Texas · Investment" with its own agent.

## 13. Definition of done

- [ ] Every check in §11 passes, and `docker build` produces one image under 350 MB.
- [ ] A fresh container on rtech.cloud: set up the admin, then sign in with Face ID on the phone and a security key on the laptop; a password sign-in on a third device works.
- [ ] Two hunts with two agents; each agent can only touch its own hunt; a user in one hunt can't see the other.
- [ ] Importing the real export produces the right `#short_id`s; hidden-by-default rules match the export's notes.
- [ ] An agent posts, attaches photos, is re-checked, marks a listing dead — and the listing is still visible under Gone with its ratings.
- [ ] A planted scam fixture (cheap, reused photo, "Zelle deposit to hold") shows "Likely scam" and is out of the default feed.
- [ ] After 20 ratings, `/agent/learn` reflects the planted preference and the Feed shows predicted ratings.
