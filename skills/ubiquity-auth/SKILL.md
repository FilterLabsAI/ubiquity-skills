---
name: ubiquity-auth
description: Use for Ubiquity/FilterLabs login & OAuth token management.
---

# Ubiquity: login and token management

Ubiquity (ubiquity.filterlabs.ai) and its backend services (Scout search, the
pipeline/locations API, the orchestrator, the understand/Ubi-chat layer) are
all secured by one Keycloak instance:

- Auth server: `auth.filterlabs.ai`
- Realm: `filter-labs-web`
- Public client: `web-app` (Direct Access Grants / Resource Owner Password
  Credentials is enabled, so a single call gets both tokens -- no
  browser/PKCE flow required)

All other `ubiquity-*` skills (pipeline-creation, entity-review,
discovery-jobs, understand-layer, metric-generators, pipeline-routing,
ubi-chat) depend on this skill for a valid Bearer token. Read this skill
first if you don't already have one.

## Setup (per user/machine, once)
Scripts live in `scripts/` of this skill and are self-contained (Python 3
stdlib only, no deps):

```
python3 scripts/filterlabs_auth.py --login "email@example.com" "password"
```

Stores tokens at `~/.hermes/secrets/filterlabs_tokens.json` (chmod 600).
Never persists the raw password. All later calls (CLI or library) use this
file automatically.

IMPORTANT for agents: do NOT try to drive the login UI through a headless
browser -- the browser tool's Chrome is typically headless with no visible
window for a human to type into. Never type a password into the page
yourself and never ask for one in chat. Options, in order of preference:
  1. Prefer this ROPC CLI flow (`--login`) when the user is comfortable
     giving credentials to a script they can inspect (same trust level as
     any CLI login) -- ask the user for email+password via `clarify` and run
     `--login` with them.
  2. If driving the actual web UI is required (e.g. to explore features not
     yet wrapped by a skill), do NOT type the password into the page. See
     "Browser SPA session bootstrap" below -- a valid access token dropped
     into `localStorage` logs the SPA in without touching the login form at
     all.
  3. `browser_vault_fill`/`browser_vault_save_login` also work on the real
     login form if the vault has (or the user agrees to save) a credential
     for this origin.

## Token lifecycle
- `access_token`: ~30 min TTL
- `refresh_token`: ~8 hr TTL, rotates on every refresh (old one becomes invalid)
- `get_access_token()` (or `python3 filterlabs_auth.py` with no args) always
  returns a currently-valid access token, silently refreshing via the
  refresh_token grant if <120s remain on the current one.
- If the refresh_token has ALSO expired (>8h since last login/refresh), it
  raises `RuntimeError` -- re-run `--login` with fresh credentials.

CLI:
```
python3 scripts/filterlabs_auth.py                # prints a valid access token
python3 scripts/filterlabs_auth.py --status        # prints expiry countdowns
python3 scripts/filterlabs_auth.py --login E P     # first-time / re-login
```

Library usage (from Python, including inside other skills' scripts):
```python
import sys, os
sys.path.insert(0, SKILL_DIR + "/scripts")
from filterlabs_auth import get_access_token
token = get_access_token()
```

## REST API base and conventions
All Ubiquity backend calls are reverse-proxied through the frontend's own
origin as `https://ubiquity.filterlabs.ai/api/<service>/<path>`. Services
seen so far: `locations` (pipelines, feeds, saved-searches, jobs, entities,
permissions, organizations), `orchestrator` (search parsing, job
creation/async-status, behavioral datasets), `understand` (Ubi chat
sessions, artifacts). Every call needs:
```
Authorization: Bearer <access_token>
Content-Type: application/json   (for POST/PUT/PATCH)
```
Scout search (separate skill, see `filterlabs-scout`/`scout-staging` if
present in this profile) uses the SAME token against
`scout.ubiquity.filterlabs.ai/api/v1/search`.

401 errors usually mean the refresh_token itself expired (>8h idle) --
re-run `--login` with fresh credentials.

### Getting your Keycloak user UUID (needed by some endpoints)
Some endpoints (e.g. entity voting in `ubiquity-entity-review`) want your
Keycloak **user UUID**, not your email, even though response bodies
elsewhere label the same logical field `keycloak_user_id` with the email as
its value. Decode the access token's JWT payload to get the UUID from the
standard `sub` claim:
```python
import base64, json
token = get_access_token()
payload_b64 = token.split(".")[1]
payload_b64 += "=" * (-len(payload_b64) % 4)  # pad for base64
payload = json.loads(base64.urlsafe_b64decode(payload_b64))
user_uuid = payload["sub"]       # e.g. "<USER_UUID>"
email = payload["email"]
```

## Browser SPA session bootstrap (for live UI exploration only)
If you need to drive the actual ubiquity.filterlabs.ai web UI (e.g. with the
`browser_exec` tool) rather than calling the REST API directly, you do NOT
need to fill in the login form. The Angular SPA reads its session from
`localStorage`. With a valid access token already obtained via this skill:

```python
import json
tok = json.load(open("/Users/<you>/.hermes/secrets/filterlabs_tokens.json"))
access_token = tok["access_token"]
# in the browser_exec context:
goto_url("https://ubiquity.filterlabs.ai")
wait_for_load()
js(f"localStorage.setItem('access_token', {json.dumps(access_token)})")
goto_url("https://ubiquity.filterlabs.ai")   # reload to pick it up
wait_for_load()
```
The SPA will now show the logged-in app (Pipelines, Create Pipeline, etc.)
without ever touching the sign-in form. Tokens expire in ~30 min same as
above -- re-set `access_token` after calling `get_access_token()` again if a
long browser session goes stale (symptom: API calls start 401ing, UI shows
stale/empty data).

Quirk observed live: after certain in-SPA navigations (e.g. right after a
form submit that triggers an Angular router transition) `document.body`
can render blank for a few seconds while JS re-renders -- if `page_info()`/
`js("document.body.innerText")` comes back nearly empty, wait ~2-3s and
re-check before assuming something broke; a hard `goto_url(current url)` +
`wait_for_load()` reliably recovers it.

## Usage notes / pitfalls
- Never type a password into the browser login form yourself and never ask
  for one in chat.
- CONCURRENCY: safe to reuse one token file across many parallel scripts;
  `get_access_token()` refreshes idempotently (though a refresh rotates the
  refresh_token, so avoid two processes refreshing at the exact same
  instant -- in practice the 120s leeway window makes races rare).
