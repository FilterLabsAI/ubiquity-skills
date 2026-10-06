---
name: ubiquity-pipeline-creation
description: Use to create Ubiquity pipelines via the Ubi discovery chat.
---

# Ubiquity: creating a pipeline (discovery chat + agent settings + discovery job)

Covers the "Discover" phase of a Ubiquity pipeline: turning a free-text
query into a saved pipeline, chatting with the "Ubi" discovery bot to
confirm scope, tuning agent settings, and launching the discovery job that
finds sources. Requires a valid Bearer token -- see `ubiquity-auth` first.

Sibling skills in this family: `ubiquity-auth` (login/tokens),
`ubiquity-entity-review` (upvote/downvote/remove discovered sources),
`ubiquity-discovery-jobs` (re-running/scaling up discovery, "Increase
Coverage"), `ubiquity-understand-layer` (enabling Ubi analysis + refresh
intervals), `ubiquity-metric-generators`, `ubiquity-pipeline-routing`,
`ubiquity-ubi-chat`.

## Base URL and auth
All calls below are to `https://ubiquity.filterlabs.ai/api/...` with header
`Authorization: Bearer <access_token>` (get one via `ubiquity-auth`'s
`filterlabs_auth.get_access_token()`).

## CRITICAL: verify the resolved location before confirming discovery
The entity chips shown after Step 1 ("LOCATIONS: European Union") only
echo back the user's input TEXT -- they do NOT reflect what the geocoder
actually resolved that text to. There is a separate, authoritative
`location` object in the SAME `/api/orchestrator/search/unified` response
that must be checked every time, especially for anything that isn't a
plain country/city name:
```json
{
  "location": {
    "id": "<location_uuid>",
    "name": "<<< THE REAL RESOLVED PLACE, check this >>>",
    "country": "...",
    "coordinates": {"latitude": ..., "longitude": ...},
    "bounding_box": {"type": "Polygon", "coordinates": [[...]]},
    "is_multi_location": false,
    "component_locations": []
  }
}
```
**CONFIRMED bug pattern**: supranational/international-organization names
systematically geocode to a literal street address or building matching a
business/POI with that exact name, NOT to the actual political/
geographic extent of the organization:
- `"European Union"` -> `"European Union, Cherni vrah Blvd., 1421 Sofia,
  Bulgaria"` (`country: Bulgaria`) -- a single street in Sofia, not the
  27-member-state EU. Reproduced with `"EU"`, `"European Union
  institutions"`, and even an explicit disambiguating phrase ("the
  European Union (EU, the political and economic union of 27 member
  states)") -- ALL four phrasings resolved to the exact same wrong Sofia
  address. Rewording the query text does not fix this.
- `"African Union"` -> a street called "African Union" in Lakewood, WA,
  USA.
- `"the Eurozone"` -> a street called "Eurozone" in Burbank, CA, USA.
- `"ASEAN"` -> resolved to the ASEAN Secretariat's actual HQ building
  address in Jakarta -- plausible-looking (real ASEAN HQ) but still a
  single building's bounding box, not the 10-member-state region.
- `"United Nations"` and `"NATO"` -> `location` is `null` entirely (search
  found no location match at all) -- the whole `/search/unified` call can
  fail outright for some org names, not just mis-resolve.
- Plain country/city names resolve correctly (`"Germany"` ->
  `id=c4df67e4-...`, `name="Germany"`, `country="Germany"`) -- this is
  specifically a multi-country/supranational-entity problem, not a general
  geocoder failure.

**How to catch this before confirming "Yes, Discover Sources"**: always
inspect `location.bounding_box` -- a correct country/region match has a
bounding box sized to that country/region (many degrees wide); a
mis-resolved street-address match has a TINY bounding box (observed: a
~0.01&deg;x0.01&deg; square, roughly a few hundred meters) regardless of
how large the real-world entity should be. Checking the bounding box's
size is more reliable than reading `location.name`/`country` alone, since
a user skimming the UI could still misread "Sofia, Bulgaria" as plausible
if they don't know Sofia isn't the EU's seat (Brussels is). Also sanity-
check `location.country` against what the user actually meant -- if the
user said "European Union" and `country` comes back as a single unrelated
member state (or a non-member state entirely, as seen with the US-based
African Union/Eurozone mismatches), that is itself a strong signal
something went wrong.

**CONFIRMED FIX -- use the pre-confirmation "Change Location" chat
action**: the fix is NOT the Discover tab's post-creation "Edit" button
(see below for why that one doesn't work) -- it is a specific button only
available BEFORE confirming discovery, on Ubi's "Would you like to
discover sources for this query?" turn:
1. Click **"No, Revise Query"** (NOT "Yes, Discover Sources") -- this
   expands four buttons: **Change Location**, **Adjust Topics**, **Narrow
   Entity Types**, **Other**.
2. Click **"Change Location"** -- this pre-fills the refine textarea
   (placeholder "Refine your search (e.g., 'Add New York' or 'Focus on
   bloggers')...") with the literal template text `"I want to change the
   location to "` for you to complete, e.g. `"I want to change the
   location to Brussels, Belgium (the EU's seat of government) instead of
   Sofia, Bulgaria"`.
3. Submit it (click the send button next to the textarea -- a small
   icon-only `<button>` immediately after the `<textarea>` in the DOM, no
   visible label).
4. Ubi responds with a changed-entities summary (`"Removed: European
   Union"` / `"Added: Brussels, Belgium"`), the LOCATIONS chip updates,
   the map re-centers/re-zooms, and (CONFIRMED on the wire) a fresh
   `/search/unified`-equivalent resolution runs against the NEW text,
   producing a genuinely different, correctly-sized `location` object --
   verified live: asking to change "European Union"/Sofia to "Brussels,
   Belgium" resolved to `id=93ee84a8-...`, `name="Brussels, BRU, Belgium"`,
   `country="Belgium"`, with a proper city-boundary `MultiPolygon`
   bounding box (not a tiny street-sized box) -- a real fix, not just a
   relabeled chip.
5. The turn returns to "Yes, Discover Sources" / "Continue Refining" --
   confirm discovery now that the location is correct, or repeat
   "Change Location" again if still wrong.

This means the overall mitigation for a supranational/multi-country query
is: don't fight the geocoder with rephrased free text (confirmed not to
help, see above) -- instead let it mis-resolve once, then explicitly route
through "No, Revise Query" -> "Change Location" (pre-confirmation) or
"Edit" (post-confirmation, works the same way -- see below) and name a
real, correctly geocodable place (the organization's actual seat/
headquarters city, or a specific member country) in the follow-up
message. This works both before AND after a pipeline is created/discovery
has started -- it is a chat correction either way, not a config field.

**CONFIRMED: the "Edit" button ALSO works on an already-created pipeline,
including one with a discovery job actively `running`** -- an earlier
test in this skill's development wrongly concluded otherwise; that
conclusion was a premature-timeout artifact, not a real limitation.
Retested properly: on a pipeline with `Discovery Status: running` (0
sources yet), clicking **Edit** opens the SAME "Refine your search" chat
box as the pre-confirmation flow. Typing `"I want to change the location
to Paris, France"` and submitting took **~10-15 seconds** to respond (vs.
near-instant for topic/entity_type refinements observed elsewhere) --
don't assume a quick 2-3s check means nothing happened; wait at least 15s
and recheck both the chat transcript AND the live pipeline object before
concluding a refine action no-oped. Confirmed on the wire: this change
was NOT just a local chat-UI relabel -- it genuinely persisted server-side
(`GET /api/locations/v1/pipelines/<id>` afterward showed
`search_filters.entities[location].value` updated to `"Paris, France"`,
a brand-new `search_filters.location_uuid`, and a bumped `updated_at`),
while the already-running discovery job for the OLD location kept running
unaffected underneath (it does not get cancelled/restarted automatically
-- you'd need to separately cancel/relaunch it if you want the new
location reflected in the actual discovered sources, see
`ubiquity-discovery-jobs`).

The earlier "not a fix" write-up (removed) was based on a single test
where the response legitimately just took longer than the ~3-4s this
session waited before checking -- same chat endpoint, same mechanism, same
fix, works in BOTH the pre-confirmation state and the post-confirmation/
job-running state. There is no evidence of a state-dependent restriction;
treat "No, Revise Query" -> "Change Location" (pre-confirmation) and
"Edit" -> type a change-location message (post-confirmation, any job
status) as the SAME underlying mechanism, both reliable, both just slower
than you might expect under load.

Other things ruled out:
- No direct "edit/override location" input field, map-pin drag, or
  location-picker UI was found on the Discover tab itself.
- A location name-search endpoint does exist --
  `GET /api/locations/v1/locations?q=<text>&limit=<n>` -- but querying it
  directly for "European Union" returned a page of UNRELATED Mexican/
  other city results, not the EU or anything close -- it's a free-text/
  fuzzy search over the same underlying POI dataset the buggy geocoder
  uses, not a curated country/region list, and isn't a reliable way to
  find a correct supranational-entity UUID to substitute manually.

**Practical guidance**: for supranational or multi-country entities (EU,
UN, NATO, ASEAN, African Union, Eurozone, etc.), always check
`location.bounding_box` size and `location.country` before confirming
discovery (see above). If it's wrong, use "No, Revise Query" -> "Change
Location" (or "Edit" if already past confirmation) and name the
organization's actual seat city (e.g. Brussels for the EU, New York for
the UN, Brussels for NATO HQ) or the specific member countries the user
actually cares about -- don't just reword the original organization name,
that was confirmed not to help. If a discovery job is already running
against the old (wrong) location when you fix it, remember the running
job keeps going unaffected -- cancel it and launch a fresh one (see
`ubiquity-discovery-jobs`) if you want the corrected location to actually
produce new discovered sources, rather than assuming the fix alone
retroactively corrects what's already in flight.

## Multiple locations on one pipeline
A pipeline can target MORE than one location at once -- useful for a group
of countries/states/cities instead of (or in addition to) a single
supranational entity whose geocoding can't be trusted (see above).

**How to add locations, one at a time**: use the same "Edit" (or
pre-confirmation "No, Revise Query" -> "Change Location") chat mechanism,
but phrase the message as **`"Add <place>"`** (the refine textarea's own
placeholder literally shows this as its example: "Refine your search
(e.g., 'Add New York' or 'Focus on bloggers')..."). This is ADDITIVE --
it keeps all previously-added locations and appends the new one, unlike
"I want to change the location to X" which REPLACES the current location
set. Confirmed live: `"Add Austria"` on a pipeline already scoped to
"Paris, France" produced `"Added: Austria"` with BOTH locations now shown
as separate LOCATIONS chips, and `search_filters.entities` in the
pipeline object gained a second `{"type": "location", "value":
"Austria"}` entry alongside the first.

**Each `"Add <place>"` chat action FULLY SAVES the pipeline on
completion, independent of what you click next.** Confirmed on the wire:
as soon as Ubi responds `"Added: <place>"`, a `PUT
.../saved-searches/<id>` and `PUT/PATCH .../pipelines/<id>` already fire
and persist the new location into `search_filters.entities` -- this
happens whether or not you ever click "Yes, Discover Sources" afterward.
The save and the discovery-job-launch are two SEPARATE steps:
- The chat response completing (`"Added: X"`) = pipeline state saved.
- Clicking **"Yes, Discover Sources"** on the follow-up turn = launches a
  NEW discovery job (see `ubiquity-discovery-jobs`).
- Clicking **"Continue Refining"** instead should let you move straight
  to the next "Add"/refine message WITHOUT launching a job, since the
  state is already saved -- this is the lighter-weight path for batch-
  adding locations (not yet re-verified after this correction; if you
  previously always clicked "Yes, Discover Sources" between adds, as the
  EU-27 test in this skill's history did, re-test with "Continue
  Refining" instead before assuming it avoids job launches).

This means the chat UI's "Edit" turn-confirmation requirement (needing
the prior turn resolved before the next "Edit" button appears/responds)
is NOT the same thing as needing to launch a job each time -- resolving
the turn via "Continue Refining" should be sufficient and should NOT
trigger `POST .../jobs/create`. Budget ~15-20 seconds per add-and-save
cycle when scripting this either way (chat response latency, not job
launch latency).

**How multiple locations are represented server-side**: `search_filters`
gets one `{"type": "location", ...}` entry per added place (so `N`
locations means `N` list entries), but there's still only ONE
`location_uuid` field. Ubiquity dynamically synthesizes a NEW combined
location object on each add -- fetching
`GET /api/locations/v1/locations/<location_uuid>` for it returns an
`abbreviation` starting with `"COMBINED-"` and a `name` like
`"Combined-Paris-IDF-France-Austria-Belgium-..."` (every component place
name concatenated), with a genuine merged multi-polygon `bounding_box`
(not a bogus street-sized box) spanning the real union of the member
places' own boundaries. This confirms the combination is geometrically
real, not just a label -- discovery actually runs against the union of
all the member areas.

## CONFIRMED LIMIT: multi-location sets cap out well below 27 members
Tested end-to-end by adding each of the EU's 27 member states one at a
time (`Add Austria`, `Add Belgium`, `Add Bulgaria`, ... `Add Sweden`,
waiting for and confirming each turn) to a pipeline already scoped to
"Paris, France". **The chat UI's own transcript and LOCATIONS chip list
kept growing and visually showed all 27 names after the last add** (chip
list genuinely read ..."Slovenia, Spain, and Sweden" with 27 separate
LOCATIONS chips) -- but checking the pipeline object on the wire
(`GET /api/locations/v1/pipelines/<id>`) afterward showed
**`search_filters.entities` had silently stopped growing at 19 locations
(Paris, France through Malta) -- Netherlands, Poland, Portugal, Romania,
Slovakia, Slovenia, Spain, and Sweden (the last 8 adds) were accepted and
echo'd by the chat UI but never actually written to the pipeline's
persisted search_filters**, even after waiting 30+ seconds for
consistency. This was re-verified multiple times (not a transient delay).

**Practical implication**: don't trust the chat transcript/LOCATIONS chip
count alone as proof a location was added -- for any pipeline with more
than roughly 15-20 locations, verify directly against
`GET /api/locations/v1/pipelines/<id>` (`search_filters.entities` count
and values) before relying on the set being complete, especially before
launching an expensive discovery job. The exact cutoff point (19 in this
test) was not confirmed to be a fixed hard limit vs. something that
varies by place-name length/complexity of the combined-location string --
treat ~20 locations as a practical ceiling to flag to the user, not an
exact guaranteed number, and always verify via the API for anything
approaching that range. If a user wants true EU-27 coverage and hits this
ceiling, consider: (a) using the (buggy, see above) "European Union"
single-location resolution instead and accepting its risk, (b) splitting
into 2 pipelines each covering ~half the member states, or (c) checking
whether a true continent/region-level location entity exists in
Ubiquity's location database that could be added as a single clean entry
instead of 27 individual countries.

## Rule of thumb: when to split into multiple pipelines + route them
For a large number of geographic areas, don't default to cramming them
all into one pipeline's location list -- consider creating SEPARATE
pipelines (e.g. one per region/country-group) and connecting them with
Pipeline Routes (see `ubiquity-pipeline-routing`) so their discovered
sources/entities flow into one place, instead of growing a single
pipeline's location list indefinitely.

**Specific threshold to flag to the user**: compare the number of
locations you're about to add/have added against the pipeline's own
`discovery_config.max_queries` (visible in Agent Settings / the pipeline
object's `metadata.discovery_config.max_queries` -- defaults seen: 15 for
Low coverage, 100 for X-High). **If the location count exceeds roughly
10% of `max_queries`**, recommend splitting rather than continuing to add
to one pipeline. Rationale: `max_queries` caps how many distinct search
queries the discovery agent will run per job -- spreading that same fixed
query budget across too many locations starves each location of query
coverage (each place gets a shrinking fraction of the total queries),
AND (see "CONFIRMED LIMIT" above) the location list itself has an
observed practical ceiling around ~19-20 entries before the backend
silently stops persisting new adds regardless of what the chat UI shows.
Example: at the default X-High `max_queries: 100`, that's a soft
threshold around 10 locations -- noticeably below the ~19-20 hard
persistence ceiling, so the query-budget problem bites FIRST and should
be the earlier warning sign, not the later storage-ceiling bug.

**What to do instead**: create one pipeline per sub-group of locations
(e.g. one pipeline for Western Europe, one for Eastern Europe, instead of
one 27-country EU pipeline), each sized so its location count stays
comfortably under 10% of its own `max_queries` (bump `max_queries` higher
per pipeline via Agent Settings if you want more locations in a single
sub-group), then use **Pipeline Routes**
(`POST /api/locations/v1/pipelines/<source_id>/routes
{"destination_pipeline_id": "<uuid>"}`, see `ubiquity-pipeline-routing`)
to fan all the sub-group pipelines into one aggregating destination
pipeline (or fan them into each other) so the user still gets one unified
view of entities/sources across the full set of locations, without any
single pipeline's discovery agent being query-starved or hitting the
location-list persistence ceiling. Mention this tradeoff to the user
up front when they ask for a pipeline covering more than a handful of
places (a country group, multiple cities, a continent broken into
nations, etc.) -- let them choose single-pipeline-with-many-locations
(cheaper to set up, but weaker per-location query coverage once count is
high) vs. multiple-pipelines-routed-together (more setup, better
per-location coverage, avoids the persistence ceiling, and each sub-
pipeline can be independently retuned/re-discovered).

## Step 1: parse a free-text query into structured filters -- CONFIRMED on the wire
The Discover UI's search box ("Describe a location and optional topic to
get started") kicks off:
```
POST /api/orchestrator/search/unified
Content-Type: application/json
{"query": "News about renewable energy in Germany", "limit": 20,
 "max_new_sources": 100, "include_suggestions": true}
```
A location is required; topic and entity_type (news/social media/etc.) are
optional refinements. Write queries as natural language, e.g. "News and
social media about artificial intelligence regulation in the European
Union" -- the location, topic, and source-type filters are all extracted
from one free-text sentence, same philosophy as Scout search.

Confirmed response shape (fuller than previously documented):
```json
{
  "existing_sources": [],
  "discovery_job_id": "<uuid -- NOT the same id as the eventual real job, just a session handle>",
  "parsed_entities": {
    "locations": [{"value": "Germany", "type": "location", "confidence": 1.0,
      "normalized_value": null, "aliases": null, "metadata": null, "languages": ["de"]}],
    "topics": [{"value": "renewable energy", "type": "topic", "confidence": 1.0, ...}],
    "entity_types": [], "persons": [], "organizations": [], "events": []
  },
  "context_report": "<prose summary of the resolved search>",
  "suggestions": ["<3 example follow-up query strings>"],
  "stats": {"existing_sources_found": 0, "entities_extracted": 2, "locations": 1, "topics": 1, "entity_types": 0},
  "location": { ... the location object documented above (id/name/country/coordinates/bounding_box/...) ... },
  "entity_changes": {"added": [{"type": "locations", "value": "Germany"}, ...], "removed": [], "modified": []},
  "confidence": 0.9,
  "reasoning": "<prose explaining how the query was interpreted>",
  "query": "<the raw query string sent>",
  "session_id": "<uuid -- THIS is the id to pass back on the next refine call>"
}
```
**CRITICAL for scripting the refine/"Change Location"/"Add <place>" chat flow
without the UI**: there is no separate "send a chat message" endpoint --
every chat refinement (Change Location, Adjust Topics, Narrow Entity Types,
"Add <place>", Other) is just ANOTHER call to this SAME
`/api/orchestrator/search/unified` endpoint, with three extra fields added
to carry the conversation state forward:
```json
{
  "query": "I want to change the location to Brussels, Belgium",
  "limit": 20, "max_new_sources": 100, "include_suggestions": true,
  "prior_query": "<the previous turn's query string>",
  "prior_entities": { ...the previous turn's parsed_entities object, verbatim... },
  "prior_context": "<the previous turn's context_report string, verbatim>",
  "session_id": "<the previous turn's response's session_id, verbatim>"
}
```
The response shape is identical to the first-turn response (same fields,
including a fresh `location`/`parsed_entities`/`entity_changes` reflecting
the delta: confirmed live, `entity_changes.added`/`removed` showed
`[{"type":"locations","value":"Brussels, Belgium"}]` /
`[{"type":"locations","value":"Luxembourg"}]` after a location-change
refine). This means the entire pre-confirmation chat loop ("No, Revise
Query" -> "Change Location"/"Adjust Topics"/etc. -> typed refine message)
can be scripted purely by looping this one endpoint, carrying
`session_id`/`prior_query`/`prior_entities`/`prior_context` forward each
call -- no separate orchestrator chat/message endpoint exists for this
phase (contrast with the per-feed Ubi chat in `ubiquity-ubi-chat`, which
DOES have dedicated `chat/sessions`/`chat/sessions/<id>/messages`
endpoints -- that is a different, later-stage chat system from this
discovery-time query parser).

## Step 2: Ubi's confirmation chat turn
After parsing, the UI shows a "Ubi" chat bubble summarizing what it found
("I found these in your search: Location: X / Entity Types: ... / Topics:
...") and asks "Would you like to discover sources for this query?" with
three options:
- **Yes, Discover Sources** -- proceeds to Step 3 (creates the pipeline +
  launches discovery). **Before clicking this, verify the resolved
  location is actually correct -- see "CRITICAL: verify the resolved
  location" above, especially for supranational/multi-country queries
  (EU, UN, NATO, etc.), which have a confirmed systematic geocoding bug.**
- **No, Revise Query** -- expands into **Change Location** / **Adjust
  Topics** / **Narrow Entity Types** / **Other** -- this is also the
  CONFIRMED fix path for a mis-resolved location (see above), not just a
  generic "go back" action.
- **Import Sources** -- skip automated discovery entirely; manually supply
  source URLs (plain text, one per line, max 25,000), a CSV upload, or a
  "Behavioral Dataset" upload. Has a "Skip AI validation" checkbox to add
  URLs without quality checks. Useful when you already know your sources
  and don't want to wait on an agent. **All three sub-flows CONFIRMED on
  the wire** (captured against a disposable test pipeline, feed_id 1670):

  **Plain Text / CSV Upload** (same endpoint, different payload shape):
  ```
  POST /api/locations/api/v1/feeds/<feed_id>/sources/upload
  Content-Type: application/json
  ```
  Plain Text body (one URL per textarea line):
  ```json
  {"skip_validation": false, "location_uuid": "<pipeline's location_uuid>",
   "urls": ["https://example.com/article"]}
  ```
  CSV Upload body (CSV is parsed/previewed CLIENT-SIDE first -- the UI
  auto-detects a URL column in any layout, shows a live preview table
  with a detected row/URL count before you confirm, and supports an
  optional "Name" column per URL):
  ```json
  {"skip_validation": false, "location_uuid": "<...>",
   "urls_with_metadata": [{"url": "https://example.com/a"}, {"url": "https://example.com/b"}]}
  ```
  (`urls_with_metadata` entries can presumably also carry a `name` field
  from the CSV's Name column, though this wasn't independently exercised
  with a populated Name column.) Both return `202` immediately:
  ```json
  {"job_id": "<uuid>", "feed_id": 1670, "url_count": 2, "valid_urls": 2,
   "invalid_urls": 0, "status": "processing", "message": "Source URLs submitted for processing"}
  ```
  This is fire-and-forget (async) -- no confirmed polling endpoint for
  `job_id`'s own progress was captured in this pass (the UI's own success
  card just shows the submitted TOTAL/VALID/INVALID counts from the `202`
  response and a "Done" button, it doesn't appear to poll further). The
  "Download Template" link for CSV Upload is purely client-side (no
  network call) -- it just generates and downloads a blank CSV skeleton
  in-browser.

  **Behavioral Dataset** -- a completely DIFFERENT endpoint family (not
  `sources/upload`), multipart file upload plus a polling job:
  ```
  POST /api/orchestrator/workflows/dataset-upload/trigger
  Content-Type: multipart/form-data
  ```
  Form fields confirmed present in the UI (`name` attributes read directly
  off the live form): `dataset_title` (required, text), `dataset_behavior`
  (optional, free-text tag, UI placeholder example `"consumer-spending"`),
  `dataset_unit` (optional, e.g. `"Percent of 2019"`), `dataset_source_url`
  (optional, `type=url`), `dataset_description` (optional, textarea),
  `dataset_external_id` (optional, defaults to "auto-generated from
  filename" per its placeholder) -- plus the file itself (`jsonl`/`csv`/
  `xlsx`, max 25MB). Exact multipart field name the file is attached
  under was not independently isolated (captured as an opaque `object`
  reqBody by the fetch interceptor, which doesn't serialize FormData
  readably) -- if scripting this outside the browser, inspect a raw HTTP
  capture (e.g. mitmproxy) rather than relying on this skill's
  interceptor pattern for the exact multipart part names.

  `200 OK` response is a job object, then poll:
  ```
  GET /api/orchestrator/workflows/dataset-upload/<job_id>/status
  ```
  Confirmed job lifecycle (real example, a 2-row test CSV with `date,value`
  columns): `status` goes `"pending"` (`progress: 0.0`) -> `"running"`
  (`progress: 0.5`) -> `"completed"` (`progress: 1.0`, within ~3 seconds
  for a trivial file) with the final object populated:
  ```json
  {"job_id": "<uuid>", "status": "completed", "progress": 1.0,
   "dataset_id": "<uuid>", "series_names": ["value"], "observations_stored": 2,
   "skipped_rows": 0, "warnings": [], "error": null,
   "created_at": "...", "updated_at": "...", "completed_at": "..."}
  ```
  `series_names` is derived from the file's non-date column header(s) --
  this confirms Behavioral Dataset upload is building a genuine time-series
  dataset (one or more named series over dates), not just importing raw
  rows -- consistent with the "Behavioral Datasets" / dataset-hunting
  concept documented in `ubiquity-agent-settings`/`ubiquity-pipeline-creation`'s
  Agent Settings section. `observations_stored` / `skipped_rows` give row-
  level ingestion accounting; `warnings` surfaces soft parse issues without
  failing the whole job.

## Step 3: pipeline + feed creation, discovery job launch -- CONFIRMED on the wire
Choosing "Yes, Discover Sources" fires FIVE separate calls in sequence,
not the single `POST /pipelines` previously assumed. **An earlier version
of this skill said the pipeline-creation request body was unconfirmed and
recommended driving the browser UI instead -- that's now resolved; a
browser `fetch`/`XMLHttpRequest` interceptor captured the real sequence,
and it was independently re-run as plain direct API calls (no browser)
and confirmed to work end-to-end (pipeline created, discovery job reached
`running`).** The sequence:

**3a. Create the saved search** (persists the parsed query + filters):
```
POST /api/locations/api/v1/saved-searches
Content-Type: application/json
{"name": "<query text, used as default pipeline name>",
 "search_query": "<same query text>",
 "search_filters": {
   "entities": [ ...flatten parsed_entities.locations + .topics + .entity_types
                 from the /search/unified response into one list, each
                 entry keeping its value/type/confidence/normalized_value/
                 aliases/metadata/languages fields verbatim... ],
   "location_uuid": "<location.id from /search/unified>"
 }}
```
`201`, returns the saved-search object with a new `id` -- this is
`saved_search_id` for step 3c.

**3b. Create the feed** (separate resource, NOT created by the pipelines
endpoint despite what the response shape in the old write-up implied):
```
POST /api/locations/api/v1/feeds
Content-Type: application/json
{"name": "<query text>",
 "metadata": {"description": "Feed for search: <query text>",
              "search_query": "<query text>"}}
```
`201`, returns the feed object with a new numeric `id` -- this is
`feed_id` for step 3c. **This is the root cause of the earlier `400
{"error": "Feed not found"}`** when `POST /pipelines` was tried directly
with a guessed body: no feed existed yet to reference, because feed
creation is this separate prior call, not something the pipelines
endpoint does itself.

**3c. Create the pipeline**, referencing both ids plus the original
`/search/unified` `session_id`:
```
POST /api/locations/v1/pipelines
Content-Type: application/json
{"name": "<query text>",
 "saved_search_id": "<id from 3a>",
 "feed_id": <id from 3b>,
 "auto_sync_enabled": true, "sync_on_job_completion": true, "sync_on_map_change": false,
 "session_id": "<session_id from /search/unified>"}
```
`201`, returns the pipeline object (`id`, `feed_id`, `saved_search_id`,
`session_id`, empty `metadata: {}` at this point).

**3d. PATCH discovery_config onto the new pipeline** (sets the default
query/source budget observed in the UI's "Agent Settings" defaults):
```
PATCH /api/locations/v1/pipelines/<pipeline_id>
Content-Type: application/json
{"metadata": {"discovery_config": {"max_queries": 15, "max_sources": 100, "min_sources": 25}}}
```
`200`, returns the updated pipeline with `metadata.discovery_config` set.

**3e. Launch the discovery job:**
```
POST /api/orchestrator/api/v1/jobs/create
Content-Type: application/json
{"location_uuid": "<location.id>",
 "job_type": "discovery",
 "parameters": {
   "search_query": "<query text>",
   "parsed_entities": [ ...same flattened entities list as 3a... ],
   "feed_id": <feed_id>,
   "pipeline_id": "<pipeline_id>",
   "vote_context": null
 },
 "max_queries": 15, "max_sources": 100, "min_sources": 25}
```
`200`, returns a job object with `status: "pending"` -> poll per Step 4
below. **Note: the request sends `job_type: "discovery"`, but
`GET /api/locations/api/v1/jobs/<job_id>` echoes it back as
`job_type: "curation"`** -- confirmed live (same job, both values seen on
the wire for the same `job_id`) and consistent with `ubiquity-discovery-
jobs`'s existing note that the orchestrator relabels a `discovery`
request as a `curation` job internally; this isn't a documentation error
in either skill, both values are real, just at different points in the
request/response cycle.

The UI shows toasts "Saving pipeline..." -> "Pipeline \"<name>\" saved
successfully!" -> "Discovery agent launched successfully!" as these five
calls land. **Fire them in this exact order** (3a -> 3b -> 3c -> 3d ->
3e) -- each later step's body references an id returned by an earlier
one, so none of them can be reordered or parallelized.

**CONFIRMED: launching discovery (3d/3e) is OPTIONAL -- a pipeline can be
created and saved WITHOUT ever starting a discovery job.** The Discover
tab has a separate **"Save"** button (next to Discover/Understand/Share
at the top) distinct from "Yes, Discover Sources". Re-ran the same
flow (parse -> confirmation turn) but clicked **Save** instead, with an
XHR interceptor capturing every call: it fired ONLY steps 3a-3c (saved-
search, feed, pipeline -- byte-identical request body shapes to the
Discover-Sources path, confirmed side-by-side) and stopped there -- no
`PATCH .../pipelines/<id>` for `discovery_config` and no `POST
/jobs/create` at all. Verified two ways after the Save click: (1) the
resulting pipeline's `metadata` was still `{}` (3d never ran), and (2) a
full scan of `GET /api/locations/api/v1/jobs?limit=10` turned up no job
with a `created_at` anywhere near the Save click's timestamp. The UI
itself also reflects this immediately -- the Discover tab shows a
**"Discover Sources"** button (not "Discovery Status: running") right
after Save, i.e. the pipeline exists but discovery hasn't started.

**Practical implication**: if a user wants a pipeline/feed to exist for
later (e.g. to import sources manually via `sources/upload` instead of
agentic discovery, or to configure Agent Settings before committing to a
discovery run) run only 3a-3c and stop -- don't assume discovery must be
launched as part of pipeline creation. The equivalent direct-API
shortcut is simply to skip steps 3d and 3e; discovery can always be
launched later by running 3d (if you want `discovery_config` set) then
3e once the user actually confirms it, exactly like the UI's own "Discover
Sources" button on an already-saved pipeline does.

The resulting
pipeline object (`GET /api/locations/v1/pipelines/<id>`) looks like:
```json
{
  "id": "<pipeline_uuid>", "keycloak_user_id": "<email>",
  "name": "<the free-text query, used as the default name>",
  "saved_search_id": "<uuid>", "feed_id": 1662, "session_id": "<uuid>",
  "auto_sync_enabled": true, "sync_on_job_completion": true, "sync_on_map_change": false,
  "metadata": {
    "discovery_config": {"max_queries": 15, "max_sources": 100, "min_sources": 25},
    "agent_config": { ... see Agent Settings below ... }
  },
  "created_at": "...", "updated_at": "...",
  "search_name": "...", "search_query": "...",
  "search_filters": {"entities": [...], "location_uuid": "..."},
  "feed_name": "..."
}
```
`feed_id` is the handle you use for almost everything downstream (entities,
metric prompts, refresh interval, Ubi chat) -- `pipeline_id` (`id` above) is
used for permissions, agent settings, and routing. Keep both.

List pipelines: `GET /api/locations/v1/pipelines?limit=10&offset=0&order_by=created_at&order=DESC`
(also filterable by `?saved_search_id=<uuid>&limit=300`).

## Step 4: track the discovery job
The discovery job is slow -- in testing a job took **15-20+ minutes** to
go from 0% to completion against a continent-scale location + broad
topic. Poll either:
```
GET /api/locations/api/v1/jobs/<job_id>
  -> {id, location_uuid, location_name, job_type: "curation" (see Step 3e note on discovery->curation relabeling), status: pending|running|completed|failed|cancelled,
      progress (0-100 int), error_message, parameters (base64), result_data, created_at, updated_at, completed_at, pipeline_id}
GET /api/orchestrator/jobs/<job_id>/async-status
  -> {job_id, pending_count, processed_count, failed_count, total_count, all_complete, has_async_work, last_updated, snapshots}
```
Use the `/jobs/<job_id>` `progress` field for a simple percent; poll every
30-60s, not more often -- this is a slow agentic job, not a quick lookup.
Never block a foreground terminal call on it; launch a background poll (see
the pattern in the `filterlabs-scout` skill's `scout_search.py
--background`) if driving this from a script.

Job-list / counts (useful for a dashboard view across all pipelines):
```
GET /api/locations/api/v1/jobs?limit=10
GET /api/locations/api/v1/jobs/count
GET /api/locations/api/v1/jobs/count/status/{pending|running|completed|failed|cancelled}
```

## Agent Settings (tune the discovery/evaluation agents)
On the Discover tab, the "Agent Settings" button opens a dialog that edits
`pipeline.metadata.agent_config`. Changes apply to **future** discovery
jobs only (not the one already running). Fields:

- **Quick Presets** (buttons that bulk-set everything below): `Balanced`,
  `Social Media Boost` (relaxes evaluation thresholds so more social
  accounts pass review), `News Focus`, `Behavioral Datasets Boost` (turns on
  dataset hunting).
- **Hunt for behavioral datasets** (toggle) ->
  `agent_config.datasets_discovery.enable_dataset_hunting` (bool). When on,
  the discovery agent also searches statistical data catalogs/national
  statistics offices (seen providers: `fred`, `world-bank`, `oecd`,
  `eurostat`, `imf`) and auto-ingests confirmed datasets (CSV/XLSX/JSON
  APIs/PDF reports) into Behavioral Data, queryable by Ubi.
- **Search Generation Agent** -> `agent_config.search_generation`:
  - `max_queries` (int, slider 5-50, default 15) -- more queries = more
    diverse results but slower discovery.
  - `creativity_level`: `low` | `medium` | `high`.
  - `focus_types` (array, checkboxes): any of `news`, `government`, `blog`,
    `community`, `social`.
  - `language_preference`: `native` (search only local language(s)) |
    `mixed` (English + native) | `english` (English only). Use `native` for
    non-English-dominant locations (China, Russia, etc.) to actually surface
    local sources.
  - Custom Instructions: free-text extra requirements for query generation --
    CONFIRMED JSON key: `agent_config.search_generation.custom_instructions`
    (string). Seen live on a real pipeline:
    `"Prioritize individual resident voices and personal reactions: Reddit
    threads, local Facebook/Nextdoor community groups, personal social media
    posts (Instagram/TikTok/X), neighborhood forums, and community board
    discussions. Deprioritize and avoid corporate/commercial entities such as
    pest control companies, exterminator businesses, and other for-profit
    vendors -- focus on what everyday New Yorkers are personally saying, not
    businesses selling related services."`
- **Evaluation Agent** -> `agent_config.evaluation`: `quality_standards`
  (e.g. `moderate`), `local_focus_priority` (e.g. `medium`),
  `credibility_threshold` (float 0-1, e.g. 0.5), `topic_relevance_weight`
  (float 0-1, e.g. 0.5). (UI section exists but detailed per-field controls
  were not individually exercised -- confirm against the live dialog if you
  need to script a specific value.)

Save with "Save Settings" -- CONFIRMED on the wire:
```
PATCH /api/locations/v1/pipelines/<pipeline_id>
Content-Type: application/json
{
  "metadata": {
    "agent_config": {
      "search_generation": {"max_queries": 15, "creativity_level": "medium",
        "focus_types": ["news","government","blog","community","social"],
        "language_preference": "mixed"},
      "evaluation": {"credibility_threshold": 0.5, "local_focus_priority": "medium",
        "quality_standards": "moderate", "topic_relevance_weight": 0.5},
      "datasets_discovery": {"enable_dataset_hunting": false,
        "providers": ["fred","world-bank","oecd","eurostat","imf"]}
    },
    "discovery_config": {"max_queries": 15}
  }
}
```
`200 OK`, returns the full updated pipeline object. The whole `metadata`
object is sent back as-is (not a partial diff) -- read the current pipeline
first, mutate the fields you want to change inside `metadata.agent_config`/
`metadata.discovery_config`, and PATCH the complete `metadata` object back
so you don't accidentally clobber unrelated settings. "Reset to Defaults"
and "Cancel" are also available in the UI (not yet captured, but Reset
likely just re-PATCHes with the default values shown above).

## Pitfalls
- A pipeline is only created once the user confirms **"Yes, Discover
  Sources"** -- just typing a query and clicking "Build Pipeline" alone only
  parses it and shows the confirmation chat; no pipeline/feed exists yet
  until that confirmation.
- Discovery jobs are genuinely slow (tens of minutes). Don't assume a job is
  stuck just because progress is still low after a minute or two.
- **Pipeline creation is a 5-call sequence (saved-search -> feed ->
  pipeline -> PATCH metadata -> jobs/create), not a single `POST
  /pipelines`** -- see Step 3 above. Calling `POST
  /api/locations/v1/pipelines` alone, before a feed exists, fails with
  `400 {"error": "Feed not found"}` -- that's not a sign the endpoint is
  broken, it's a sign the feed-creation call (3b) was skipped.
- **Starting discovery is optional, not required, to create a pipeline**
  -- the first 3 of those 5 calls (saved-search, feed, pipeline) are all
  that's needed for a pipeline/feed to exist; the UI's "Save" button
  (vs. "Yes, Discover Sources") confirms this live -- see Step 3. Don't
  assume you must launch a discovery job just because the user asked for
  a pipeline to be created.
