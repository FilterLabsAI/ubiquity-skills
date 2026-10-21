---
name: ubiquity-pipeline-sharing
description: Use to share a Filter / Ubiquity pipeline with members of the same FilterLabs organization (view or edit access). Sharing is limited to existing org members; confirm recipient and access level with the user first.
---

# Ubiquity: pipeline sharing / permissions

Covers the "Share" button on a pipeline's Discover tab (top-level nav row
next to Discover/Understand/Save) -- a per-pipeline access-control dialog,
distinct from Pipeline Routes/Data Egress (see `ubiquity-pipeline-routing`,
which lives on the Understand tab instead). Requires a valid Bearer token
-- see `ubiquity-auth`.

## Who can be shared to -- CONFIRMED: only existing org members
The Share dialog's user list is NOT a free-text email field -- it is a
fixed roster of users who belong to your Ubiquity organization. You
cannot share a pipeline with an arbitrary email address; the target user
must already be a member of one of your orgs. Resolve the valid target
list with two calls, in order:

**1. List the orgs you belong to:**
```
GET /api/locations/v1/organizations
```
Response (confirmed live, real example, placeholders substituted for the
actual org name/uuid):
```json
[{"name": "<ORG_NAME>", "uuid": "<ORG_UUID>", "licensed_seats": 2}]
```
Most accounts will see exactly one org here; `licensed_seats` is the
org's total seat count (not necessarily the same as the number of users
currently listed in step 2 -- seats can be unused).

**2. List the members of an org (and their current pipeline-sharing
ability, if any -- see below):**
```
GET /api/locations/v1/permissions/organization/<org_uuid>
```
Response (confirmed live, real example, emails replaced with placeholders
-- real response had 8 members):
```json
[
  {"ability": "write", "keycloak_user_id": "user1@example.com"},
  {"ability": "write", "keycloak_user_id": "user2@example.com"},
  {"ability": "write", "keycloak_user_id": "user3@example.com"},
  {"ability": "write", "keycloak_user_id": "user4@example.com"},
  {"ability": "write", "keycloak_user_id": "user5@example.com"},
  {"ability": "write", "keycloak_user_id": "user6@example.com"},
  {"ability": "write", "keycloak_user_id": "user7@example.com"},
  {"ability": "write", "keycloak_user_id": "user8@example.com"}
]
```
Despite the key name `keycloak_user_id`, the value here is the user's
**email**, not a UUID (contrast with entity-voting's `keycloak_user_id`
request field in `ubiquity-entity-review`, which genuinely wants the
JWT-`sub` UUID -- these are two different conventions under the same
field name in two different parts of the API, don't conflate them).
This list exactly matches the usernames shown in the Share dialog's
Username column -- confirmed live, same 8 emails, same order. The
`ability` field here reflects an ORG-LEVEL default/baseline, separate
from any PER-PIPELINE grant set via the Share dialog (see below) -- don't
assume a user showing `"write"` here already has access to a specific
pipeline; it does not seem to vary per org member in practice (all 8
showed `"write"` in this account), so its exact meaning/effect versus
the per-pipeline permission below is not fully characterized -- treat it
as "this person is a valid share target," not as "this person already
has access to pipeline X."

**Practical use**: before offering a human (or scripting a share action
for) a list of who a pipeline CAN be shared with, call these two
endpoints first and offer only names from step 2's list -- don't accept
or attempt an arbitrary email, it will not work (the UI itself has no
free-text entry path for this reason).

## Per-pipeline sharing -- CONFIRMED
```
GET /api/locations/v1/permissions/pipeline/<pipeline_id>
  -> list of current grants, same {ability, keycloak_user_id} shape as above
PUT /api/locations/v1/permissions/pipeline/<pipeline_id>/<email>
Content-Type: application/json
{"ability": "write"}
```
`<email>` goes directly in the URL path (not URL-encoded in testing --
plain `user1@example.com` worked as a path segment). `200 OK` on
success. The UI's Share dialog has two checkboxes per user row (View,
Edit) but **only ever sends ONE PUT call with `{"ability": "write"}`**
when you check Edit -- confirmed on the wire (captured via fetch/XHR
interceptor): checking Edit auto-ticks View in the UI's own display, but
no separate request fires for View. This strongly implies `ability` is a
single-value enum (`read` vs `write`, with `write` implying `read`), not
two independent booleans -- `read`/`view`-only sharing was not
independently exercised in this session (no UI path found to grant View
without Edit), so the exact string for view-only is UNCONFIRMED;
if you need a view-only grant, try `{"ability": "read"}` and verify via
the GET above rather than assuming.

No DELETE/revoke endpoint was exercised in this session -- unchecking a
grant in the UI was not tested; if asked to revoke access, try `DELETE
/api/locations/v1/permissions/pipeline/<pipeline_id>/<email>` by analogy
with the rest of this API's REST conventions, but verify the response
and the subsequent GET before trusting it worked.

## UI mechanics (if driving the Share dialog directly)
- The "Share" button sits in the same top-level row as Discover/
  Understand/Save on a pipeline's page (`https://ubiquity.filterlabs.ai/
  search/<saved_search_id>?tab=discover`) -- find it via text match
  (`e.textContent.trim() === 'Share'`), not a fixed DOM position.
- Clicking it opens a "Pipeline Sharing" panel inline (not a modal
  overlay) with a `Username | View | Edit` list, one `<li class=
  "list-row">` per org member, each containing two `<input
  type="checkbox">` (index 0 = View, index 1 = Edit).
- Find a specific user's row by locating the leaf text node matching
  their email, then `.closest('li.list-row')`, then `querySelectorAll
  ('input[type=checkbox]')` on that row.
- Clicking the Edit checkbox fires the PUT above immediately (no
  separate "Save"/"Apply" button) and triggers a follow-up GET to refresh
  the dialog's displayed state.
- A "Close" button (plain text, not icon) dismisses the panel.

## Pitfalls
- Don't confuse this with Pipeline Routes (`ubiquity-pipeline-routing`) --
  routing connects one pipeline's data flow to another pipeline, sharing
  grants a USER access to view/edit a pipeline. Different tab, different
  endpoints, different purpose, despite both living under `/permissions`-
  adjacent URL space conceptually.
- Always resolve the valid-recipient list via the two organization
  endpoints above before attempting a share -- don't guess at an email
  or assume any address will work.
