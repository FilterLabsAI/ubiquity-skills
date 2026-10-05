---
name: ubiquity-pipeline-routing
description: Use to connect Ubiquity pipelines + egress to platforms.
---

# Ubiquity: pipeline routing (pipeline-to-pipeline) and data egress

"Pipeline Routes" and "Data Egress" both live on the **Understand tab**
(not a separate "Share" tab -- there is a top-level "Share" button but it's
a share-link action, unrelated). Scroll down past the Enable
Ubi/refresh-interval/metric-generator sections. Requires a valid Bearer
token -- see `ubiquity-auth`. All endpoints below CONFIRMED live.

## When to use routing instead of growing one pipeline's location list
See `ubiquity-pipeline-creation`'s "Rule of thumb: when to split into
multiple pipelines + route them" section -- for a pipeline covering a
large number of geographic areas (a country group, many cities, a
continent), it's often better to create several smaller pipelines (one
per region/sub-group) and connect them via Pipeline Routes below, rather
than adding all locations to one pipeline. Rough threshold: if the
location count would exceed ~10% of that pipeline's
`discovery_config.max_queries`, split instead -- a single pipeline's
query budget gets spread too thin across many locations, and there's also
an observed hard ceiling (~19-20 locations) where the backend silently
stops persisting further additions regardless of what the chat UI shows.
Routing multiple right-sized pipelines together gets the user one unified
view without either problem.

## Pipeline Routes (pipeline-to-pipeline) -- CONFIRMED
```
GET    /api/locations/v1/pipelines/<pipeline_id>/routes
POST   /api/locations/v1/pipelines/<pipeline_id>/routes
DELETE /api/locations/v1/pipelines/<pipeline_id>/routes/<route_id>
```
`pipeline_id` in the path is always the ROUTE'S SOURCE pipeline (the one
whose Understand tab you're on when you click "Connect a pipeline" /
"Add Route"). Create body only needs the destination:
```json
POST /api/locations/v1/pipelines/<source_pipeline_id>/routes
{"destination_pipeline_id": "<uuid>"}
```
`201` response:
```json
{"id": "<ROUTE_UUID>",
 "source_pipeline_id": "<SOURCE_PIPELINE_UUID>", "destination_pipeline_id": "<DEST_PIPELINE_UUID>",
 "enabled": true, "filter_mode": "all", "filter_config": {},
 "created_by": "<email>", "metadata": {},
 "created_at": "...", "updated_at": "..."}
```
`GET` (list) response additionally denormalizes names/feed ids for display:
adds `source_pipeline_name`, `destination_pipeline_name`, `source_feed_id`,
`destination_feed_id` to each route object.
`filter_mode`/`filter_config` default to `"all"`/`{}` -- these look like
hooks for routing only a subset of entities (e.g. by vote status or topic)
but no UI control for them was found; likely API-only for now.
**CONFIRMED API-only write path**: `POST .../routes` accepts and echoes
back arbitrary values for both fields with no server-side validation
observed -- a test call with `{"filter_mode": "liked_only",
"filter_config": {"min_credibility": 0.5}}` returned `201` with those
exact values persisted (`GET` afterward echoed the same).
**Effect NOT yet confirmed**: a live test created a `liked_only` route
from a pipeline with 15 liked entities (NYC rat-mitigation, feed 1668) to
a route-wise-empty destination pipeline (feed 1670, 47 pre-existing
entities from its own discovery), clicked the pipeline detail page's
"Trigger Sync" button (fired no observable network call under an XHR/
fetch interceptor -- either it's not wired to a request this skill's
interceptor pattern catches, or sync is scheduled/background rather than
an immediate on-click call), and re-checked the destination feed's
entity count ~15-20s later: still 47, no new entities appeared. This is
inconclusive, not a negative result -- route-based entity flow may simply
be slower than tested (e.g. a periodic background job, not something
"Trigger Sync" kicks off instantly), or may require `auto_sync_enabled`/
`sync_on_job_completion`-style conditions beyond just the route existing.
Treat `filter_mode`/`filter_config` values as accepted-on-write but
UNVERIFIED in effect -- don't promise a user that setting `liked_only`
will filter what flows through until this is re-tested with a longer
observation window or by triggering a fresh discovery job on the source
pipeline (which is confirmed to sync afterward per `sync_on_job_completion`)
rather than relying on the on-demand "Trigger Sync" button alone.
Delete: `DELETE .../routes/<route_id>` -> `204` empty body.

### UI mechanics (DOM quirks worth knowing if automating)
- "Connect a pipeline" / "Add Route" opens a picker modal
  (`div.pr-modal`) listing AVAILABLE pipelines as
  `button.pr-picker-item` elements (NOT plain `<li>` or generic
  clickable divs) -- find the pipeline's name as a leaf text node, then
  walk `parentElement` up to the nearest `button.pr-picker-item` and
  `.click()` that, not an intermediate wrapper div. Clicking a wrapper div
  instead of the actual button leaves "Create Route" disabled with no
  visible error.
- The picker only lists pipelines NOT already connected and excludes the
  current pipeline itself (fetches the full list via
  `GET /api/locations/v1/pipelines?limit=500&offset=0&order_by=created_at&order=DESC`
  and filters client-side) -- if you only have one pipeline, the picker
  shows nothing to connect to; create a second pipeline first (see
  `ubiquity-pipeline-creation`) to exercise this flow.
- Routing is directional per-call (`source` -> `destination`) but a
  pipeline's Understand tab shows ALL its routes regardless of direction
  (fan-in aggregation from multiple sources, or fan-out to multiple
  destinations) -- the 3-slot UI diagram ("a source" / "this pipeline" /
  "a destination") just illustrates that either role is possible, not that
  you pick a direction in the create call (direction is implied: you're
  always creating a route FROM the pipeline you're viewing).

## Data Egress (third-party push) -- UI confirmed, save endpoint TBD
Only one integration seen so far: **Meltwater**, in the same Understand-tab
section as Pipeline Routes, just below it. UI copy: "Send this feed's
content out to a third-party platform... Push this feed's articles and
posts into your Meltwater account... New content is delivered as it is
discovered. Existing content is not backfilled." Fields:
- Meltwater API key (write-only -- "Stored encrypted. It is never shown
  again after you save it." -- treat like any secret: never log it, never
  echo it back, never type it in except via vault-style credential entry).
- Company ID (optional).
- Import tag (optional) -- "Labels this feed's content inside Meltwater."
- Toggle: "Send this feed to Meltwater" (shows "Not sending" when off).
- "Save integration" button.

Exact endpoint (likely `PUT /api/locations/api/v1/feeds/<feed_id>/egress/meltwater`
or a generic `/integrations` resource keyed by provider name) was **not
captured on the wire** -- deliberately skipped since the API key field is
real-looking and write-only; don't exercise this with a throwaway value on
a real account without the user's say-so. If asked to automate this, warn
the user it will store whatever key is supplied server-side, then capture
the request shape with the fetch/XHR interceptor pattern (see
`ubiquity-entity-review`) while they provide a real key through the UI.
