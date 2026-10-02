---
name: ubiquity-metric-generators
description: Use to create/view Ubiquity metric generators on a feed.
---

# Ubiquity: metric generators

Covers the "Metric Generators" section of a pipeline's Understand tab --
creating custom metrics derived from a feed's artifacts, and viewing their
output. Requires a valid Bearer token -- see `ubiquity-auth`.

## Listing metric prompts -- confirmed shape via create response
```
GET /api/locations/api/v1/feeds/<feed_id>/metric_prompts
```
Returns `null` when none exist; presumably an array of objects shaped like
the create response below once at least one has been created. `feed_id`
comes from the pipeline object (see `ubiquity-pipeline-creation`).

## Creating a metric generator -- CONFIRMED, re-verified live
UI entry point: "New Metric" is a `<summary>`/dropdown trigger (not a plain
button -- query for it with `document.querySelectorAll('summary')` if
automating, not `button`) under METRIC GENERATORS on the Understand tab.
Opening it reveals three built-in presets: **Sentiment**, **Entities**,
**Stance** -- clicking one opens an "Edit Metric Generator" panel
pre-filled with a template name + prompt, which you can edit before saving.

**All three presets' exact default template text (confirmed live):**

- **Sentiment** -- Name: `Sentiment`, generates `metric_name: "sentiment"`:
  > Your task is to read the text carefully and assign a score relating to
  > the sentiment of the text. Your score should be a range of -10 to 10.
  > - a score of -10 indicates that the text has extremely negative
  >   feelings about its subject. - a score of 0 indicates that the text
  >   has neutral feelings about its subject. - a score of 10 indicates
  >   that the text has extremely positive feelings about its subject.

- **Entities** -- Name: `List Entities`, generates `metric_name` from that
  name (slugified, see below):
  > Your task is to make a list of important entities (people, places,
  > organizations, governments, businesses) mentioned in the text

- **Stance** -- Name: `Stance toward [ENTITY]` (a literal placeholder --
  this preset is explicitly meant to be filled in before saving, unlike
  Sentiment/Entities which are usable as-is):
  > Your task is to assign a score to this text on a scale of -10 to +10,
  > or null if not applicable:
  >
  > **Support for [ENTITY]**: This score reflects the text's overall
  > stance toward [ENTITY], [General list of related concepts].
  > - A score of +10 represents extremely positive, supportive, or
  >   favorable views of [ENTITY]
  > - A score of 0 represents neutral or balanced views.
  > - A score of -10 represents extremely negative, critical, or hostile
  >   views of [ENTITY]
  > - A score of null indicates no stance toward [ENTITY], or text is
  >   unrelated to [ENTITY]

Each preset form has: a `Name of metric...` text input, an `Active`
checkbox (defaults checked/true), and a `Prompt` textarea.

Save fires:
```
POST /api/locations/api/v1/feeds/<feed_id>/metric_prompts
Content-Type: application/json
{
  "feed_id": <feed_id>,
  "name": "Sentiment",
  "metric_name": "sentiment",
  "prompt": "<the full prompt text>",
  "active": true
}
```
`200 OK`, response adds `id` (uuid), `filter_prompt` (null, seen so far),
`filter_distance` (null, seen so far), `created_at`, `updated_at`:
```json
{"id": "<METRIC_GEN_UUID>", "feed_id": "<FEED_ID>", "name": "Sentiment",
 "metric_name": "sentiment", "prompt": "...", "filter_prompt": null,
 "filter_distance": null, "active": true, "created_at": "...", "updated_at": "..."}
```
Each `metric_prompts` list entry has two distinct name fields: `name` is
the user-readable label shown in the UI, and `metric_name` is the slug
actually used in API calls (`filter_state.metricName` in Ubi chat/Data
Browser, `score_map` keys when joining artifact scores, etc.) -- always
read `metric_name` off the object rather than re-deriving/guessing a slug
from `name` yourself. Client-side slug generation is lowercase with
spaces/punctuation collapsed, confirmed on two live examples:
`"Sentiment"` -> `"sentiment"`, and `"Stance toward [ENTITY]"` ->
`"stance_toward_"` (the bracketed placeholder collapsed away entirely,
leaving a trailing underscore) -- but since both examples contained
either a single word or a bracketed placeholder, don't assume this
pattern generalizes cleanly to an arbitrary plain multi-word name (e.g.
whether "List Entities" slugs to `"list_entities"` or something lossier
is unconfirmed) -- fetch the real `metric_name` from the list endpoint
instead of predicting it. `filter_prompt`/`filter_distance` remain
unexercised in both create and edit so far.

## Editing / deleting a metric generator -- CONFIRMED, prefer direct REST over the UI
**Don't drive the "Edit Metric Generator" UI modal for scripted edits --
call the REST API directly instead.** The modal's form is Angular
(`ngModel`), and a plain `fill_input`/native-setter DOM edit followed by
only a bare `input` event can silently no-op (first attempt in this
skill's development: `.value` read back correctly, but Save still
persisted the OLD text server-side) -- Angular's two-way binding needs
more than one bare `input` event to resync before the Save handler reads
from it. That whole class of problem is avoidable: **this resource has
its own direct per-id REST endpoints**, confirmed live, that work
identically whether or not any UI is open:
```
PUT    /api/locations/api/v1/feeds/<feed_id>/metric_prompts/<metric_id>
DELETE /api/locations/api/v1/feeds/<feed_id>/metric_prompts/<metric_id>
```
`PUT` takes the same body shape as create (`feed_id`, `name`,
`metric_name`, `prompt`, `active`) and returns `200` with the full
updated object (`updated_at` bumped, `id`/`created_at` unchanged) --
confirmed by creating a throwaway metric, `PUT`-editing its `name`/
`prompt` directly (no browser form involved at all), and re-fetching the
list to see the edit landed. `DELETE` returns `204` with an empty body
and confirmed removal from a subsequent list fetch. (`PATCH` on the same
path was tried and returned `404` -- this resource only supports `PUT`
for updates, not partial `PATCH`.) **Prefer this over any DOM-automation
approach** for scripted/automated edits -- it's simpler and has no
Angular-binding timing pitfall to work around. The UI's pencil (edit,
`ng-icon[name=heroPencilSquare]`) / trash (delete,
`ng-icon[name=heroTrash]`) icon buttons on each METRIC GENERATORS list
row are still the right entry point for a human clicking through the UI
manually, and both ultimately hit the same endpoints above -- just drive
them via `fetch`, not simulated clicks/typing, when scripting.

**Pitfall (UI-only, N/A when using the REST endpoints above):** the edit
dialog has an unrelated top-level pipeline-name "Save" button elsewhere
on the page with identical visible text ("Save") -- when automating via
the DOM anyway (e.g. for a human-driven walkthrough), scope your button
lookup to inside the metric-editor container rather than grabbing the
first/any button whose text is "Save", or you'll accidentally PUT the
pipeline/feed/saved-search name instead.

## Viewing metric output
There is no separate per-metric "results" GET -- computed metric values
are read via the Understand-layer endpoints that join scores to
artifacts/time, not from this `metric_prompts` resource. See
`ubiquity-understand-layer`'s `POST /api/understand/metrics/preview`
(`filter_state.metricName` = this metric's `metric_name` field) for the
time-series/chart data, and the per-artifact `data[].artifact_uuid` ->
`score` join for individual scored items.
