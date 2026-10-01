---
name: ubiquity-discovery-jobs
description: Use to run/scale/cancel Ubiquity discovery jobs.
---

# Ubiquity: running, scaling, and cancelling discovery jobs

## IMPORTANT: two different "save" paths -- only ONE of them launches a job
Ubiquity has (at least) two distinct ways to persist pipeline state, and
they are NOT interchangeable:

1. **Any chat action completing** ("Add <place>", "Change Location",
   "Adjust Topics", etc. in the Discover chat -- see
   `ubiquity-pipeline-creation`) and **Agent Settings "Save Settings"**
   -- both are pure state saves. CONFIRMED on the wire: as soon as Ubi's
   chat response finishes (e.g. `"Added: Austria"`), the pipeline's
   `search_filters`/`saved_search` are already persisted via
   `PUT .../saved-searches/<id>` + `PUT/PATCH .../pipelines/<id>` --
   independent of whatever button you click next on that turn. Likewise
   Agent Settings' `PATCH .../pipelines/<id>` only touches
   `metadata.agent_config`/`discovery_config`. Neither of these calls
   `POST /api/orchestrator/api/v1/jobs/create`. Safe to call/trigger
   repeatedly without adding to job load.
2. **Clicking "Yes, Discover Sources"** on a chat confirmation turn, or
   any coverage-level button ("Discover a few sources" / "Review" /
   "Increase Coverage" -> Low/Medium/High/X-High) -- THIS is the step
   that actually calls `POST /api/orchestrator/api/v1/jobs/create` and
   launches a brand new discovery/curation job. If a chat turn offers
   "Yes, Discover Sources" vs. "Continue Refining", only the former
   should trigger a new job -- "Continue Refining" lets you keep editing
   (the state is already saved from the completed chat action) without
   paying for another discovery run.

**Never click/script "Yes, Discover Sources" repeatedly without the user
explicitly asking for a new discovery run, and prompt the user before
launching a NEW discovery job if one was already run recently on the same
pipeline** -- even though the UI technically allows re-launching
(coverage buttons re-enable once the prior job reaches a terminal state),
doing so repeatedly is exactly how a backlog of hundreds of stale/zombie
`running` jobs accumulates on the account (CONFIRMED: one cleanup pass in
this skill's development found **436 jobs stuck in `running` status**
accumulated server-side, and this is suspected to be a contributing cause
of the `asyncpg.exceptions.TooManyConnectionsError: sorry, too many
clients already` failure seen on at least one real job -- a saturated
backend connection pool from too many concurrent discovery workflows).
When batch-adding locations/topics via chat (see
`ubiquity-pipeline-creation`), prefer **"Continue Refining"** between
adds and only click **"Yes, Discover Sources"** once, at the end, when
you actually want discovery to run against the final filter set -- not
once per add. If you (the agent) are about to call `jobs/create` (or
click/script the equivalent UI button) and you're not 100% sure the user
asked for THIS SPECIFIC new job right now, stop and ask first via
`clarify`.

**Before launching, always check for an existing job first**: query
`GET /api/locations/api/v1/jobs/count/status/running` and
`.../status/pending` for the account, and/or check whether this specific
pipeline already shows `Discovery Status: running` -- if either is
nonzero/true, ask the user whether they want to wait for it, cancel it,
or launch anyway, rather than silently stacking another job on top.

This skill also covers re-running discovery on an existing pipeline,
scaling it up ("Increase Coverage"), and cancelling a running job via the
Jobs Management page (https://ubiquity.filterlabs.ai/jobs). See
`ubiquity-pipeline-creation` for the very first discovery job created when
a pipeline is built. Requires a valid Bearer token -- see `ubiquity-auth`.

## Launching a (re-)discovery job -- CONFIRMED on the wire
The Discover tab's three buttons -- **"Discover a few sources"**,
**"Review"**, and **"Increase Coverage"** -- are three identical toggles
for the SAME inline panel, not three different actions: clicking any one
opens/closes a "Select a coverage level:" panel with four buttons -- `Low`,
`Medium`, `High`, `X-High` -- plus the note "Agent Settings will override
these values. Configure in Agent Settings modal."

**Constraint, confirmed live:** the four coverage-level buttons are
`disabled` while the pipeline already has a job in `"running"`/`"pending"`
status (`Discovery Status: running` shown at the top of the Discover tab)
-- a pipeline can only have ONE discovery job in flight at a time. Check
`GET /api/locations/api/v1/jobs/<job_id>` -> `status`, or just whether the
coverage-level buttons are disabled, before attempting to launch another
(or cancel the existing one first -- see below).

Clicking an enabled level button fires, in order:
1. `PUT /api/locations/api/v1/feeds/<feed_id>` `{"name": "<feed name>"}`
2. `PUT /api/locations/v1/pipelines/<pipeline_id>` `{"name": "<pipeline name>"}`
3. `PUT /api/locations/api/v1/saved-searches/<saved_search_id>` (full search_query/search_filters re-save)
4. `PATCH /api/locations/v1/pipelines/<pipeline_id>` -- re-applies `metadata.agent_config` plus a `discovery_config` with coverage-level-specific `max_queries`/`max_sources`/`min_sources` (`Low` observed as `max_queries: 15, max_sources: 100, min_sources: 25`)
5. `POST /api/orchestrator/api/v1/jobs/create` -- the actual job:
```json
{
  "location_uuid": "<uuid>",
  "job_type": "discovery",
  "parameters": {
    "search_query": "<pipeline's saved search query>",
    "parsed_entities": [ /* same entities array as the saved search */ ],
    "feed_id": <int>,
    "pipeline_id": "<uuid>",
    "vote_context": {
      "liked_entities": [{"name": "...", "type": "..."}],
      "disliked_entities": [{"name": "...", "type": "..."}]
    }
  },
  "max_queries": 15, "max_sources": 100, "min_sources": 25
}
```
Response `201`-ish (observed `200`): a job object with `status: "pending"`,
`progress: 0`, and a new `id` -- this is the job to poll/cancel.

**`vote_context` is the entity-review feedback loop made concrete**: every
entity you've liked/disliked (see `ubiquity-entity-review`) on this
pipeline gets fed back into the NEXT discovery job's prompt, by
name+type, as explicit positive/negative examples -- this is how voting
actually influences future discovery, not just display sorting.

Steps 1-4 are mostly no-op re-saves of unchanged data (the UI always
re-PUTs name/search fields even if nothing changed) -- if scripting this
directly, you can likely skip straight to step 5's job-create call once you
have the pipeline's current `feed_id`/`saved_search_id`/entities/vote
context, but mirror the full sequence if you want to match the real client
exactly.

## Cancelling a job -- CONFIRMED, via the Jobs Management page
Go to `https://ubiquity.filterlabs.ai/jobs` (top-level nav, separate from
any single pipeline's Discover/Understand tabs -- it lists ALL jobs across
ALL pipelines for the account, with Location/Status filters and summary
counts). Each row has two icon-only buttons in the Actions column: an
"eye" icon (view/inspect -- not yet explored) and an X icon with
`text-warning` styling (cancel) -- scope lookups to
`button.btn-ghost.btn-xs` and distinguish by the `text-warning` class, text
content is empty on both.

Clicking cancel triggers a native `confirm()` dialog ("Are you sure you
want to cancel job <job_id>?") -- if driving this headlessly, override
`window.confirm = () => true` BEFORE clicking, or the dialog silently
blocks/auto-dismisses with no request sent. Confirmed on the wire:
```
PUT /api/locations/api/v1/jobs/<job_id>/status
Content-Type: application/json
{"status": "cancelled"}
```
`200 OK`, response echoes the job with `status: "cancelled"` and
`progress` frozen at whatever it was when cancelled (does not reset to 0).
A second fetch of `GET /api/locations/api/v1/jobs/<job_id>` afterwards also
shows `completed_at` now set (cancellation counts as a terminal state) and
`updated_at` bumped to the cancel time.

Same endpoint presumably accepts other status transitions (e.g. manually
marking `"failed"`) but only `"cancelled"` was exercised.

## Tracking job progress
Poll `GET /api/locations/api/v1/jobs/<job_id>` for `status`/`progress`, or
`GET /api/orchestrator/jobs/<job_id>/async-status` for processed/pending/
failed counts. `job_type` seen so far: `"discovery"` (job-create request)
and `"curation"` (same job, as returned/displayed -- the orchestrator
apparently relabels/wraps a `discovery` request as a `curation` job
internally; don't be surprised if the type you sent differs from the type
you see back).

The Jobs Management page (`/jobs`) is the easiest way to see a pipeline's
full job history without guessing query params -- it fetches
`GET /api/locations/api/v1/jobs?limit=50&offset=0` (no `pipeline_id` filter
confirmed; the page likely filters client-side via its Location dropdown)
and shows Status/Type/Location/Progress/Created/Updated/Results columns
for every job on the account.

## Expectations on duration -- IMPORTANT, jobs can stall
Discovery/curation jobs are slow agentic pipelines (observed 15-20+
minutes for a broad location+topic). **However, a job can also fully
stall**: one test job sat at `status: "running"`, `progress: 10` for over
an hour with `updated_at` never advancing -- entities kept appearing in the
Discovered Sources list during this time (so SOME backend work was
happening), but the job's own progress counter never moved and never
completed. If a job's `updated_at` hasn't changed in a long time (tens of
minutes) despite polling, don't assume it will eventually finish --
cancel it (see above) and launch a fresh one rather than waiting
indefinitely.

Always poll asynchronously (every 30-60s) rather than blocking, and tell
the user up front to expect a long wait (and the possibility of a stall)
rather than silently hanging.
