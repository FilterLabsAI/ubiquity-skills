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
`"Valid: false"`/all-zero fields means "Do Not Update"/unset). Also returned:
`refreshed_at` (last refresh timestamp), plus three OTHER interval fields
that are NOT exposed in this UI panel but exist on the feed resource and
ARE settable via this same PUT, **CONFIRMED on the wire**:
```
PUT /api/locations/api/v1/feeds/<feed_id>
{"name": "...", "refresh_interval_minutes": 1440,
 "deletion_detection_interval_minutes": 10080,
 "engagement_detection_interval_minutes": 720,
 "automatic_entity_rediscovery_interval_minutes": 43200,
 "force_review_for_auto_discover": true, "backdate_limit": 30}
```
All five accepted and persisted (response echoed each as its own
`{Microseconds,...}` struct, same shape as `refresh_interval`). Field
notes:
- `deletion_detection_interval_minutes` / `engagement_detection_interval_minutes`
  / `automatic_entity_rediscovery_interval_minutes`: same minutes-in,
  struct-out convention as `refresh_interval_minutes` -- no UI control
  exists for these, but the backend accepts and stores them via direct PUT.
  Their actual effect (what the deletion-detection/engagement-detection/
  entity-rediscovery background jobs DO with these intervals) was not
  independently verified -- only that the field is settable and persists.
- `force_review_for_auto_discover` (bool): accepted as `true`/`false`.
- `backdate_limit`: **CONFIRMED type is `int32`, NOT a date string** --
  sending a `"YYYY-MM-DD"` string 400s with
  `"json: cannot unmarshal string into Go struct field .backdate_limit of
  type int32"`. Sending a plain int (e.g. `30`) succeeds and is stored
  as-is (not wrapped in a `{Microseconds,...}` struct like the interval
  fields) -- almost certainly a day-count, not minutes, given the name and
  the fact it isn't struct-wrapped like the true intervals, but the exact
  unit wasn't independently confirmed.
- **Pitfall confirmed**: this feed resource's `metadata` field (separate
  from `pipeline.metadata`) got silently wiped to `null` after this PUT,
  because the PUT body didn't include it and this is a full replace, not a
  partial patch -- same "must re-send everything" pattern as `name`
  documented below, but it bit an UNLISTED field here. If a feed has a
  non-null `metadata` you want to keep, `GET` the feed first and include
  its current `metadata` verbatim in the PUT body, not just `name` and
  whatever interval fields you're changing.

**Confirmed live: changing the dropdown AUTO-SAVES immediately on
`change`, no separate Save button.** Driving this with `browser_exec`:
find the `<select>` whose options include `"Do Not Update"` (there are
other `<select>`s on the Understand tab -- a per-page row-count picker and
a metric picker -- so match on option text, not element order), set
`.value` via the native setter, then dispatch `input`+`change`+`blur` (the
same three-event pattern needed for the Angular metric-generator form, see
`ubiquity-metric-generators` -- a bare `input` event alone is unreliable on
this Angular app's bound controls):
```js
const sel = Array.from(document.querySelectorAll('select')).find(s => Array.from(s.options).some(o=>o.textContent.trim()==='Do Not Update'));
const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
const opt = Array.from(sel.options).find(o=>o.textContent.trim()==='Every 12 Hours');
setter.call(sel, opt.value);
sel.dispatchEvent(new Event('input', {bubbles:true}));
sel.dispatchEvent(new Event('change', {bubbles:true}));
sel.dispatchEvent(new Event('blur', {bubbles:true}));
```
Confirmed on the wire: `GET /api/locations/api/v1/feeds/<feed_id>`
immediately after showed `refresh_interval: "12 hours"` (note: the GET
response's `refresh_interval` here is a plain human-readable STRING like
`"12 hours"`/`"7 days"`, not the `{Microseconds,...}` struct shown earlier
-- that struct form was only observed in the PUT response; GET returns the
simpler string) and a bumped `updated_at`, with no extra click needed
beyond the dropdown change itself.

**Pitfall:** this is a full `PUT`, and the request body only showed `name`
+ `refresh_interval_minutes` in testing -- if the real client always
re-sends `name` alongside the interval, do the same (read the feed first
via `GET /api/locations/api/v1/feeds/<feed_id>` to get the current `name`,
then PUT both fields) rather than guessing at partial-update semantics.

## Recommended: propose metrics as soon as Ubi is enabled
As soon as a feed's Understand/Ubi layer is turned on (refresh interval
set to anything other than "Do Not Update"), think about metrics right
away -- don't wait for the user to ask for "numbers" later. Qualitative
Ubi-chat answers alone (prose summaries, hand-picked quotes) don't give a
real distribution across all ingested artifacts; metrics do, and scoring
lags ingestion, so the earlier metrics exist the sooner they have real
coverage.

Look back at the user's ORIGINAL question/goal for this feed and derive
metric suggestions FROM IT, rather than defaulting to a fixed bundle --
what's useful varies a lot by topic. A sentiment-tracking question
usually wants a Sentiment metric; a question specifically about opinion
of a policy/entity wants a topic-scoped Stance metric (write it
concretely, e.g. "Stance toward NYC's rat mitigation efforts", not the
generic `[ENTITY]` placeholder -- this disambiguates tone from opinion,
since a snarky-but-supportive post can read sentiment-negative while
being stance-positive); a question comparing groups (residents vs. news,
competitors, regions) wants a classifier metric for that split; a
question covering multiple distinct programs/angles wants a sub-topic
classifier so scores can be broken down per angle instead of only in
aggregate. Propose 1-4 metrics as fits the actual question, not a fixed
count.

**Confirm each proposed metric with the user before creating it** (e.g.
via `clarify`, one metric per choice or a short list to approve/edit) --
don't create metrics speculatively. Still propose them unprompted/early
rather than waiting to be asked, but creation itself needs user
confirmation, since metric design (exact scale, prompt wording, which
split to classify by) is a judgment call worth a quick check rather than
a default to just run with. Still worth doing this early even though
scoring takes time to catch up with ingestion (see `metric_score is None
for many rows` under Pitfalls above) -- getting them created early
minimizes that lag window by the time anyone wants to review results.

## Artifacts (what Ubi analyzes)
```
GET /api/understand/artifacts/count/<feed_id>   -> {count, feed_id}
POST /api/understand/artifacts/preview
  Content-Type: application/json
  {"feed_id": <feed_id>, "filter_state": {}, "limit": 1000}
  # filter_state can include a date range, e.g.:
  {"feed_id": <feed_id>, "filter_state": {"dateRange": {"start": "2026-09-01", "end": "2026-10-03"}}, "limit": 1000}
```
**`artifacts/count/<feed_id>` was previously broken (returned the same
account-wide stale value for every feed) -- this has been fixed
server-side as of 2026-10-06 and re-verified live.** The underlying bug
was `feed_id` being matched as a non-`exact` filter against a field
that's actually stored as a string in the vector DB; the fix switches the
Qdrant filter to `exact=True` with the feed_id coerced to a string (see
`agents/understand-agent/api/main.py`, commit `79449109`). Live
re-verification against 5 real feeds now shows distinct, plausible
per-feed counts instead of one identical account-wide number, and for a
feed under the 1000-item `artifacts/preview` cap (640 artifacts) the two
endpoints' counts matched exactly:
```
feed 1662: artifacts/count -> 640   | artifacts/preview total_count -> 640  (exact match, under cap)
feed 1663: artifacts/count -> 95889 | artifacts/preview total_count -> 1000 (capped, consistent: real count > cap)
feed 1665: artifacts/count -> 14191 | artifacts/preview total_count -> 1000 (capped, consistent)
feed 1668: artifacts/count -> 22959 | artifacts/preview total_count -> 1000 (capped, consistent)
feed 1670: artifacts/count ->  3075 | artifacts/preview total_count -> 1000 (capped, consistent)
```
**`artifacts/count` is now the preferred, fast way to check whether a
feed has ingested anything yet / to poll ingestion progress** -- it's a
direct Qdrant count, cheaper than fetching and counting up to 1000 full
artifact records via `artifacts/preview`. Use it as:
```
GET /api/understand/artifacts/count/<feed_id>   -> {"count": N, "feed_id": N}
```
`count: 0` means nothing has been indexed yet; any positive count means
ingestion has produced at least that many artifacts. `artifacts/preview`
remains the right choice when you actually need the artifact records
themselves (for the data browser table, Sample Distribution chart, etc.)
-- `total_count` there is capped at 1000 regardless of the real
underlying count, so don't use `artifacts/preview`'s `total_count` as an
exhaustive count once a feed has grown past the cap; `artifacts/count`
is the uncapped, exact figure.

This was verified with one before/after-style live comparison across 5
feeds plus one exact-match check under the cap -- solid evidence the fix
works as described, but not an exhaustive regression suite (e.g. a true
zero-artifact brand-new feed wasn't available to test against during
this verification pass). If `artifacts/count` is ever again observed
returning an identical value across clearly-different feeds, treat that
as a regression and fall back to `artifacts/preview`'s `total_count`
until re-confirmed.

**`artifacts/preview` defaults to capping results at 1000** (the `limit`
param) -- it does NOT try to return everything matching the filter.
**CONFIRMED: the `limit` param does NOT actually limit the response --**
sending `limit: 10` still returned all 1000 artifacts; 1000 appears to be
a hard server-side cap regardless of what `limit` is set to. Any
page-size/row-count behavior (10/25/50/100 in the UI) is applied
CLIENT-SIDE by slicing the full up-to-1000-item response, not by the
server honoring `limit`. Don't rely on `limit` to reduce payload size or
cost -- fetch once, slice locally.
Contrast with `metrics/preview` below, which has no such cap and will try
to pull in and score the MAXIMUM amount of matching data it can find
(hence why it's slow on wide/unfiltered date ranges, and why
`filter_state.dateRange` matters so much more for `metrics/preview` than
for `artifacts/preview` -- for the artifacts table/list you're usually
already capped at 1000 rows regardless of filtering, but for the metrics
chart an unscoped request really will try to walk the metric's entire
scored history).
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

## Feed Data Artifacts (the data browser: chart + table) -- CONFIRMED structure
Below the Ubi chat panel on the Understand tab sits a "Feed Data Artifacts"
card -- a combined chart + paginated table view over the SAME underlying
data, both driven by one shared filter bar and ONE API call:
```
POST /api/understand/artifacts/preview
Content-Type: application/json
{"feed_id": <feed_id>, "filter_state": {...}, "limit": <int>}
```
Response: `{"artifacts": [{"id", "headline", "url", "site_type",
"published_at", "content_sample", "score"}, ...]}` -- `score` here is a
generic relevance/filter score (seen as `1.0` with no filters applied),
NOT a metric value; metric scores are a separate per-artifact lookup (see
below).

**Filter bar** (funnel icon + chips, shared by chart and table): Date
range chip (defaults matching the feed's current date window), plus
whatever other `filter_state` keys are active render as additional chips
-- same `filter_state` shape as Ubi chat sessions (see `ubiquity-ubi-chat`:
`topics`, `entities`, `dateRange`, `siteTypes`, `metricName`, `textSearch`,
`entityTypes`).

**Chart data endpoint -- CONFIRMED, corrected**: the chart is NOT powered
by `artifacts/preview` (that endpoint returns generic `score:1` filter
scores, not metric values). The actual metric-chart endpoint is:
```
POST /api/understand/metrics/preview
Content-Type: application/json
{"feed_id": <feed_id>, "filter_state": {"metricName": "<metric_name>"}}
```
- **Slow**: observed ~2.5 minutes to respond for a feed with 4000+ scored
  buckets. Any `browser_exec`/automation call to this endpoint MUST use a
  fire-and-forget pattern (store the fetch promise result on a `window`
  variable, return immediately, then poll `window.__result` in later
  calls) -- a direct `await fetch(...)` inside the JS passed to `js()`
  will blow the harness's own ~5s `Runtime.evaluate` timeout long before
  the real network response lands, even though the underlying request
  eventually succeeds.
- Response shape: `{"data": [...], "series": [...], "total_count": int,
  "filter_applied": {...}}`.
  - `data`: per-artifact scores, `[{"artifact_uuid", "score", "list"}, ...]`
    (this is what feeds the table's "Metric" column).
  - `series`: **the chart data** -- `[{"bucket": "<ISO8601 date>", "score":
    <float>}, ...]`, one point per day that has at least one scored
    artifact (not evenly spaced -- gaps on days with no data).
  - `total_count`: total scored artifacts matching the filter.
  - `filter_applied`: echoes back the resolved filter_state, confirms
    which keys were actually honored.
- **Always scope `metrics/preview` with `filter_state.dateRange` -- never
  call it unfiltered.** The underlying data has real quality problems:
  some scored artifacts have no reliable date at all, and some have
  badly-parsed/garbage dates that place them far in the future (see
  `ubiquity-data-feed-api`'s note on bogus `2050`/`2065` `published_at`
  values from Wikipedia-sourced items -- the same bad-date problem shows
  up here). Confirmed: an unfiltered request (no `dateRange` set) returns
  `series` buckets spanning the metric's entire history, including these
  garbage far-future dates (seen: buckets from 2013 through 2027 on a
  feed whose real content only starts ~Aug 2026). This isn't just a
  display nuisance -- an unfiltered call also triggers a much deeper and
  slower scan of the underlying data (observed ~2.5 minutes vs ~45s
  scoped), which almost certainly wastes time and backend resources for
  no benefit, since you'd have to trim the garbage dates back out
  client-side anyway. **Always pass an explicit `filter_state.dateRange`,
  preferably starting with a 1-month window**, rather than fetching full
  history and trimming afterward.
- **CONFIRMED: `filter_state.dateRange` DOES scope server-side and
  significantly speeds up the query.** `{"dateRange": {"start":
  "2026-09-02", "end": "2026-10-02"}}` (plain `YYYY-MM-DD` strings, no
  time component needed) cut response time from ~150s to ~45s (roughly
  3x faster) and `total_count` dropped from 4090 to 1804 -- a real
  server-side filter, not client truncation. This is the SAME scoped
  call referenced above -- the two observations (deep/slow unfiltered
  scan vs. fast/clean scoped result) describe the unfiltered and filtered
  cases of the identical endpoint, not two different behaviors.

**Chart controls**: a "Pick a metric" `<select>` scoped to this card,
options = `Sample Distribution` (default -- presumably a generic
document-count-over-time view, not tied to any custom metric) plus one
option per `active: true` metric generator on the feed (confirmed: our
two custom metrics "Sentiment" and "Stance toward Renewable Energy
Policy" both appeared as selectable options immediately after being
created via `ubiquity-metric-generators`, no extra wiring needed).
Selecting a metric re-renders the chart to show that metric's values over
time AND populates a "Metric" column in the table below with each row's
per-artifact score for that metric (seen as `N/A` when no metric is
picked, i.e. `Sample Distribution` mode shows no per-row metric value).

**Table columns** (confirmed from live DOM): Published Date, Headline,
Content Preview, Filter Score, Metric, Actions. Each row has **View**
(opens a per-artifact detail modal -- discovered pages, crawl/created
timestamps, type) and **Find Similar** (not yet explored, presumably a
vector-similarity lookup against this artifact). Pagination: page-size
`<select>` (10/25/50/100) plus numbered page buttons (confirmed up to
"100" pages at 1000 docs / 10-per-page).

**IMPORTANT -- there is a SEPARATE, confusingly similar metric picker on
Ubi chat itself**, not inside this card: the chat panel's own filter bar
also has a "Pick a metric"-style control that sets `filter_state.
metricName` for a NEW chat session (confirmed: selecting a metric there
added a "With Metric: <metric_name>" chip to the chat header and changed
the active doc count, e.g. 1000 -> 925 docs). **Don't conflate the two**
when automating -- scope your `querySelectorAll('select')` lookup to
inside the "Feed Data Artifacts" card specifically (walk up from the
card's heading text node) rather than grabbing the first "Pick a metric"
select found page-wide, since both exist simultaneously on the same page.

## Rendering the artifact table as text (for Hermes chat)
Columns: Published Date, Headline, Content Preview, Filter Score, and
(optionally) Metric Score. **Don't assume the user wants a metric column
at all.** Before fetching anything from `metrics/preview`, ask the user
which metric (if any) they want joined in, offering the feed's active
metric generators as choices plus a "None" option (e.g. via the
`clarify` tool: list each `active: true` metric name from
`GET /api/locations/api/v1/feeds/<feed_id>/metric_prompts` as a choice,
with "None" as one of the options). Only call `metrics/preview` if the
user picked one -- skip it entirely (and the Metric Score column) if they
said none, since `metrics/preview` is the slow endpoint and shouldn't be
hit speculatively.

**Render the table using actual markdown table syntax** (`| col | col |`
with a `---` header separator row), not a fixed-width/box-drawn text
table -- markdown tables reflow per the chat renderer's own column
sizing/wrapping instead of relying on a monospace font and fixed padding,
which handles varying screen widths much better. Still truncate long
Headline/Content Preview text to a reasonable character count (e.g.
~60-80 chars with an ellipsis) so a single cell doesn't dominate the
table, and strip embedded newlines first (see pitfalls below) since
markdown table cells can't contain literal line breaks either.

Pull artifacts via `artifacts/preview` (one `filter_state.
dateRange`-scoped fetch, then slice client-side to the page size you
want -- see the `limit`-doesn't-limit pitfall above), then join in metric
scores (if requested) by matching `artifact.id` against `metrics/
preview`'s `data[].artifact_uuid`:
```python
score_map = {d["artifact_uuid"]: d["score"] for d in metrics_data}  # from metrics/preview, same dateRange + metricName
for a in artifacts[:page_size]:
    metric_score = score_map.get(a["id"])  # None/missing is a REAL, expected state -- not every artifact in the window has been scored yet
    ...
```
**Expect and handle gracefully, these are normal/observed, not bugs:**
- `metric_score` is `None` for many rows even within the metric's own
  scoped date window. Per `ubiquity-metric-generators`: a metric only
  scores artifacts ingested AFTER the metric was created -- it does NOT
  backfill/retroactively score artifacts that already existed at creation
  time, so `None` on a pre-existing artifact is permanent, not transient
  lag that will resolve itself. Only artifacts ingested going forward
  (post metric-creation) will accumulate scores. Render as `N/A` either
  way, but don't tell a user it'll "catch up soon" for old artifacts.
- `headline` or `content_sample` can be empty strings on some artifacts
  (seen on `article_list`-type sources with no headline parsed, or
  micro_blog posts with no body text extracted) -- render as a fallback
  placeholder like `(no headline)` rather than leaving a blank column.
- Headlines/content can be long and contain newlines -- truncate with an
  ellipsis to a fixed column width and strip embedded `\n` before
  truncating, to keep each artifact on one table row.

**Pagination:** since `artifacts/preview` returns everything (up to the
1000 cap) in one call regardless of `limit`, treat the full fetched list
as already in memory and just slice different windows of it client-side
when the user asks for "the next page" / "page 2" / "show more" -- don't
re-fetch from the API for each page, re-slice the same cached result
(e.g. keep the fetched `artifacts` list around for the conversation and
track an offset). Only re-fetch if the user changes the filter (date
range, metric, etc.) itself.

**Numeric ID column + full-record lookup:** add a leading `#` column
with a simple 1-based row number (NOT the artifact's real UUID -- that's
too long/noisy for a table and the user has no use for it directly). Keep
a mapping from that display number to the real `artifact.id` (UUID) for
the current page/fetch in memory. When the user asks to see the full
record for a row (e.g. "show me #3" / "expand row 3"), look up that
artifact by the cached number -> UUID mapping and print ALL of its
fields unredacted and untruncated (`id`, `headline`, `url`, `site_type`,
`published_at`, `content_sample` in full, `score`, plus the joined metric
score if one was requested) -- this is the place to show the full
`content_sample` and `url` that the table view truncates/omits. Numbering
should be stable across pages of the SAME fetch (e.g. row 11 on page 2 of
a 10-per-page view, not reset to 1 each page) so a user can reference any
row from any page without re-stating which page it was on.

Example output (real data, Germany pipeline, Sentiment metric chosen):
```
| # | Published Date      | Headline                                 | Content Preview                               | Filter | Metric |
|---|---|---|---|---|---|
| 1 | 2026-10-02 14:57:00  | 18 Jahre alter Terrorverdächtiger steht… | (no preview)                                   | 1.00   | -6.0   |
| 2 | 2026-10-02 10:05:29  | #strategie #batteriespeicher #ccus #ki…  | EEHH gibt sich eine neue #Strategie bzw. ...   | 1.00   | 9.0    |
| 3 | 2026-09-29 00:00:00  | Bidirektionales Laden: Experte erklärt…  | Gehört haben wohl vor allem E-Autofahrer ...   | 1.00   | N/A    |
```

## Pitfalls
- The Understand tab is largely non-functional (shows a "Collecting
data..." blocking banner) until the pipeline's discovery job has completed
and produced at least some artifacts -- don't expect to flip "Enable Ubi"
or get real chat answers immediately after pipeline creation.
- `feed_id` (not `pipeline_id`) is the key for all Understand-layer calls.

## Reproducing the "Sample Distribution" chart (artifacts/preview only)
The default chart mode (before picking a custom metric) is "Sample
Distribution" -- it does NOT call `metrics/preview` at all. Internally the
SPA just takes the `artifacts/preview` response and sums artifact counts
per day client-side. Reproduce it the same way:
```python
from collections import Counter
import datetime

counts = Counter()
for a in artifacts:          # artifacts/preview response, dateRange-filtered
    if a.get("published_at"):
        counts[a["published_at"][:10]] += 1

start, end = datetime.date(2026, 9, 2), datetime.date(2026, 10, 2)
days = []
d = start
while d <= end:
    days.append(d.isoformat())
    d += datetime.timedelta(days=1)
series = [{"bucket": day, "score": counts.get(day, 0)} for day in days]
```
Then render with columns 1 (date), 2 (count), and 4 (zoomed ASCII line)
from the metrics-chart layout above -- there is no fixed-scale column 3
here since a raw count has no natural -10/+10-style bound, only the
auto-scaled zoomed view makes sense. **For the zoomed range, floor `zlo`
at 0 rather than padding below the minimum observed count** -- counts can
never go negative, so only the top bound (`zhi`) should get the 10% pad:
```python
zlo = 0
zhi = max(scores) * 1.1 or 0.5
```

**How the 1000-item cap actually samples (CONFIRMED semantics)**: when a
request matches more than 1000 artifacts, the API does NOT return the
most recent 1000 chronologically -- it **randomly samples** from the
matching set, down to some system-determined minimum match threshold if
a topic/text filter is applied. The practical effect: the resulting
day-by-day distribution is a genuine (if noisy) reflection of how much
matching content exists in the underlying collection per day, which is
exactly what makes the Sample Distribution chart useful as a "when was
this topic more/less prominent" signal, rather than useless the way a
naive most-recent-first fill would be. The earlier working theory in this
skill (that the API "fills slots most-recent-first," explaining the
~224-articles-on-the-last-day skew observed in one test) was the wrong
mechanism -- that skew is better explained by genuinely higher real
ingestion/collection volume on recent days than by any fill-order bias in
the sampling itself. **Important caveat for recently-created feeds**: a
feed turned on only days/weeks ago will show sparse/near-zero counts on
its earlier days not because of sampling bias, but because of ordinary
"online bit rot" (sources that existed back then may no longer be
discoverable/scrapable, so there's genuinely less content to find) --
treat early-window sparsity on a new feed as a sign of how much old
content survived to be found, not as a defect in this chart.

**Timezone edge case when setting a "last 30 days" `dateRange`:** `end`
should be set one day past "today" (i.e. tomorrow's date), not exactly
today. `published_at` timestamps on artifacts have their timezone offset
truncated (e.g. `"2026-10-01T08:15:00"` with no `Z`/offset suffix), so a
document published late in the day in a timezone ahead of the user's can
land on what looks like "tomorrow" relative to the user's local today.
Padding `end` by one extra day avoids silently dropping those edge-case
artifacts from the window. **Both `start` and `end` are technically
subject to this same timezone-truncation skew** (a document could in
principle land on what looks like "yesterday" too, not just "tomorrow")
-- but in practice padding `end` matters more, since the recency-skewed
sampling and ongoing ingestion mean most of what you'd clip by under-
padding is concentrated at the tail end.

**Separate 7-day `start` padding needed specifically for `metrics/preview`
(not `artifacts/preview`/Sample Distribution)**: `metrics/preview`'s
`series` values are computed with a multi-day rolling average applied
across buckets, not a true per-day point value. If you need the FIRST
few days of your requested window to be accurate (not artificially
dragged by missing days before the window start), pad `start` **7 days
earlier** than what you actually want to display, fetch that wider
range, then trim the extra lead-in days back off before rendering. This
only matters for higher-precision use of `metrics/preview` (e.g. day-to-
day movement near the start of a window) -- the Sample Distribution
reproduction above doesn't need it, since it's a raw per-day count with
no rolling-average smoothing applied.

## Rendering the metrics/preview chart as a text table (for Hermes chat)
For surfacing the chart half of the Feed Data Artifacts browser in a
text-only chat context: one row per `series` point, columns are
(1) date, (2) the score rounded to 3 decimals, (3) an ASCII number-line
with a `|` marking the value's position across the metric's fixed scale
(e.g. -10 to +10 for Sentiment/Stance-style metrics), and (4) a SECOND,
"zoomed" number-line auto-scaled to the actual min/max of the fetched
data window -- the fixed full-range column alone often barely moves when
real-world swings are small relative to the metric's theoretical range
(e.g. 4.4-5.9 out of a -10..+10 scale), so the zoomed column is what
actually shows day-to-day movement:
```python
def render_line(value, lo, hi, width=21):
    frac = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    pos = round(frac * (width - 1))
    line = [" "] * width
    line[pos] = "|"
    return "".join(line)

scores = [p["score"] for p in series]
zlo, zhi = min(scores), max(scores)
pad = (zhi - zlo) * 0.1 or 0.5  # avoid a zero-width zoom range when flat
zlo -= pad
zhi += pad

for pt in series:  # trimmed to the relevant date window first, see above
    date = pt["bucket"][:10]
    val = round(pt["score"], 3)
    full_line = render_line(pt["score"], -10, 10)
    zoom_line = render_line(pt["score"], zlo, zhi)
    print(f"{date:<12} {val:>8.3f}   [{full_line}]   [{zoom_line}]")
```
Example output (real Sentiment data, Germany pipeline, last 30 days,
fetched with `dateRange` set per the speedup note above):
```
Date            Value   [-10             +10]   [1.41           6.32]
2026-09-29      3.572   [              |      ]   [         |           ]
2026-09-30      2.321   [            |        ]   [    |                ]
2026-10-01      1.821   [            |        ]   [  |                  ]
```
Use the metric's actual defined scale as `lo`/`hi` for the full-range
column (read from the metric generator's config if available) rather than
assuming -10/+10 universally -- that happens to be Sentiment/Stance's
scale but other metrics may differ. The zoomed column's `zlo`/`zhi` should
always be derived from the fetched data itself, not hardcoded.
