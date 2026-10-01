---
name: ubiquity-understand-layer
description: Use to enable Ubiquity's Understand/Ubi layer, refresh rate.
---

# Ubiquity: Understand layer -- enabling Ubi analysis + data refresh interval

Covers the "Understand" tab of a pipeline: turning on Ubi's artifact
analysis for a feed, and configuring how often the pipeline refreshes its
data. Requires a valid Bearer token -- see `ubiquity-auth`.

## Enable Ubi / Data Refresh Interval -- CONFIRMED (same control, one dropdown)
What the UI calls "Enable Ubi?" with a toggle, and the "Data Refresh
Interval" dropdown just below it, are actually **the same underlying
setting** -- there is no separate boolean "enabled" flag. Turning the
toggle off sets the refresh interval to 0 ("Do Not Update"); the dropdown
just gives finer-grained options for the same field. Confirmed on the wire:
```
PUT /api/locations/api/v1/feeds/<feed_id>
Content-Type: application/json
{"name": "<feed name, must be re-sent -- this is a full PUT, not a partial PATCH>",
 "refresh_interval_minutes": <int>}
```
Dropdown value -> `refresh_interval_minutes` mapping (confirmed from the
live `<select>` element's `value` attributes):
| UI label | minutes |
|---|---|
| Do Not Update | `0` (empty string in the raw `<option value>`, but PUT sends `0`) |
| Every 12 Hours | `720` |
| Daily | `1440` |
| Every 2 Days | `2880` |
| Weekly | `10080` (confirmed live) |
| Monthly | `43200` (approx, 30 days -- not individually confirmed, derive from pattern) |

Response echoes back a structured `refresh_interval` object, not minutes:
```json
{"refresh_interval": {"Microseconds": 604800000000, "Days": 0, "Months": 0, "Valid": true}, ...}
```
(a Postgres `interval`-style struct serialized by the backend -- `Valid:
false` + all-zero fields means "Do Not Update"/unset). Also returned:
`refreshed_at` (last refresh timestamp), plus three OTHER interval fields
that are NOT exposed in this UI panel but exist on the feed resource:
`deletion_detection_interval`, `engagement_detection_interval`,
`automatic_entity_rediscovery_interval` (all `Valid: false` by default --
presumably configurable elsewhere or reserved for future UI, not yet
exercised), plus `force_review_for_auto_discover` and `backdate_limit`
(both `null` so far).

**Pitfall:** this is a full `PUT`, and the request body only showed `name`
+ `refresh_interval_minutes` in testing -- if the real client always
re-sends `name` alongside the interval, do the same (read the feed first
via `GET /api/locations/api/v1/feeds/<feed_id>` to get the current `name`,
then PUT both fields) rather than guessing at partial-update semantics.

## Artifacts (what Ubi analyzes)
```
GET /api/understand/artifacts/count/<feed_id>   -> {count, feed_id}
POST /api/understand/artifacts/preview
  Content-Type: application/json
  {"feed_id": <feed_id>, "filter_state": {}, "limit": 1000}
  # filter_state can include a date range, e.g.:
  {"feed_id": <feed_id>, "filter_state": {"dateRange": {"start": "2026-09-01", "end": "2026-10-03"}}, "limit": 1000}
```
Confirmed on the wire (`"Enable Ubi"` button on the Discover tab actually
just navigates to the Understand tab, which fires this preview call
automatically). Before any artifacts have been ingested for a feed, this
returns `500` with a body like:
```json
{"detail": "Failed to get filtered artifacts: Unexpected Response: 404 (Not Found)\nRaw response content:\nb'{\"status\":{\"error\":\"Not found: Collection `<email>` doesn't exist!\"},...}'"}
```
i.e. the understand service keeps a per-user vector/document "Collection"
keyed by your account email, lazily created once the pipeline actually
has ingested artifacts to put in it -- a 500 with "Collection ... doesn't
exist" here just means "no artifacts yet," not a real server error. Expect
this until the discovery job completes AND a subsequent ingestion/sync step
has run (discovering sources alone does not create artifacts -- artifacts
come from actually fetching/scanning content from those sources).

Artifacts are presumably the ingested documents/posts/datasets collected by
the feed's sources -- what the Ubi chat bot (see `ubiquity-ubi-chat`) and
metric generators (see `ubiquity-metric-generators`) read from. "Collecting
data..." is shown on the Understand tab until artifacts exist.

## Pitfalls
- The Understand tab is largely non-functional (shows a "Collecting
data..." blocking banner) until the pipeline's discovery job has completed
and produced at least some artifacts -- don't expect to flip "Enable Ubi"
or get real chat answers immediately after pipeline creation.
- `feed_id` (not `pipeline_id`) is the key for all Understand-layer calls.
