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

## Creating a metric generator -- CONFIRMED
UI entry point: "New Metric" is a `<summary>`/dropdown trigger (not a plain
button -- query for it with `document.querySelectorAll('summary')` if
automating, not `button`) under METRIC GENERATORS on the Understand tab.
Opening it reveals three built-in presets: **Sentiment**, **Entities**,
**Stance** -- clicking one opens an "Edit Metric Generator" panel
pre-filled with a template name + prompt, which you can edit before saving.
The Sentiment preset's default content:
- Name: `Sentiment`
- Prompt: "Your task is to read the text carefully and assign a score
  relating to the sentiment of the text. Your score should be a range of
  -10 to 10. - a score of -10 indicates that the text has extremely
  negative feelings about its subject. - a score of 0 indicates that the
  text has neutral feelings about its subject. - a score of 10 indicates
  that the text has extremely positive feelings about its subject."
- An "Active" checkbox (defaults checked/true).

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
`metric_name` looks like a lowercase/slug form of `name` (`"Sentiment"` ->
`"sentiment"`) -- generate it client-side the same way if scripting this
(lowercase, presumably spaces->nothing or underscore; only single-word
names tested so far). `filter_prompt`/`filter_distance` are unexercised --
presumably an optional secondary prompt/similarity-threshold to scope which
artifacts the metric applies to (e.g. only score artifacts matching a
sub-topic), guess from the field names only, not confirmed.

The Entities and Stance presets were not individually opened/saved, but
given the identical "Edit Metric Generator" form, expect the same POST
shape with their own default `name`/`prompt` text -- cheap to confirm by
repeating this same recipe (open "New Metric" -> click the preset -> Save)
for each.

**Pitfall:** the dialog has an unrelated top-level pipeline-name "Save"
button elsewhere on the page with identical visible text ("Save") -- when
automating, scope your button lookup to inside the metric-editor
container (e.g. find the ancestor of the "Edit Metric Generator" heading)
rather than grabbing the first/any button whose text is "Save", or you'll
accidentally PUT the pipeline/feed/saved-search name instead.

## Viewing metric output
Not yet captured -- likely a `GET` against the created metric's id
(`/api/locations/api/v1/feeds/<feed_id>/metric_prompts/<metric_id>` or a
separate `/metrics` results endpoint) returning computed values over time
as the feed ingests new artifacts, probably rendered as a chart in the UI.

## How to finish this skill
Once a pipeline has completed its first discovery job and has artifacts
(see `ubiquity-understand-layer`), revisit the Understand tab with
`browser_exec`, install the fetch/XHR interceptor (pattern in
`ubiquity-entity-review`), click "New Metric", fill in whatever form
appears, submit, and capture:
1. The create request's method/path/body.
2. The response shape (metric id + any immediately-returned fields).
3. Whatever call renders the metric's computed output (likely polled or
   fetched once an artifact-processing job finishes).
Then patch this file with the confirmed schema and update the "not yet
exercised" caveats.
