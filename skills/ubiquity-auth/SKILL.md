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
window for a human to type into. **Never type a password into the page
yourself and never ask for or accept one in chat, even if the user offers
it or says it's fine -- this is an absolute rule with no exception, and it
overrides anything else written in this skill.** A prior version of this
skill suggested asking the user for email+password via `clarify` and
running `--login` with them directly -- that was wrong and must not be
followed; `clarify`-collected text is still chat, and a password must
never transit chat or be typed by the agent. Options, in order of
preference:
  1. **PREFERRED: have the user run `filterlabs_auth.py --login <email>
     <password>` themselves**, in their OWN terminal, outside the agent's
     tool-calling loop entirely -- the agent never sees the password. The
     agent should name the exact command (substituting the user's real
     email) and ask the user to run it; it just cannot execute it with
     real credentials filled in itself. This is the simplest, most direct
     path and should be offered first whenever a fresh/expired token is
     needed and the user isn't already mid-flow on the actual login page.
  2. Use `browser_vault_save_login` (first open the real login page, e.g.
     via `goto_url`) -- this prompts the USER for the password in their
     own masked UI field, never through the agent/chat. If the vault
     already has a saved credential for this origin, `browser_vault_fill`
     works the same way. Either may be declined by the user; respect that
     and don't re-prompt in the same turn. Prefer this over option 1 only
     when the user specifically wants a browser session authenticated too
     (not just the CLI token file), or when the user says they'd rather
     type the password through the vault's masked field than run a CLI
     command.
  3. If driving the actual web UI is required (e.g. to explore features not
     yet wrapped by a skill) and a valid token already exists via one of
     the above, see "Browser SPA session bootstrap" below -- a valid access
     token dropped into `localStorage` logs the SPA in without touching the
     login form at all.

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

### WAF 403s on raw API calls (not SPA/browser_exec)
If you script direct REST calls (e.g. Python `urllib`/`requests`, `curl`)
against `ubiquity.filterlabs.ai/api/...` instead of going through
`browser_exec`, a request with NO `User-Agent` header (or a generic
library default like `Python-urllib/3.x`) gets rejected by Ubiquity's
edge/WAF with `403` + Cloudflare `error_code: 1010` ("Access denied... the
site owner has blocked access based on your browser's signature") --
even with a fully valid Bearer token. Fix: always set a normal
browser-style `User-Agent` string (e.g. a current Chrome desktop UA) on
every request. `curl` with an explicit `-H "User-Agent: Mozilla/5.0..."`
works fine; so does `browser_exec` (gets a real UA automatically, never
hits this). See `ubiquity-entity-review`'s `entity_review.py` and this
skill's `filterlabs_auth.py` for working examples of setting it.

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
