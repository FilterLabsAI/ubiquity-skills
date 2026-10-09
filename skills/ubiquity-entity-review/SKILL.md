---
name: ubiquity-entity-review
description: Use to review Ubiquity discovered sources/entities, vote.
---

# Ubiquity: entity/source review (upvote, downvote, remove)

After a discovery job finds candidate sources for a pipeline, they land in
the feed's entity list for human review. This skill covers listing,
filtering, and voting on (or removing) those discovered sources/datasets.
Requires a valid Bearer token -- see `ubiquity-auth`.

## CRITICAL conceptual distinction: you are NOT reviewing content
An "entity" here is a SOURCE (a person, account, publication, or outlet)
-- not a specific article/post/comment it produced. Voting on an entity is
NOT a content-moderation judgment on anything that entity has said or
written so far. The question a vote actually answers is: **"is this
entity, as an ongoing source, likely to produce content relevant to the
conversations/questions the end user wants this feed to answer?"** --
a forward-looking relevance/fit judgment about the SOURCE, not a
backward-looking quality judgment about any one piece of CONTENT.
Concretely:
- A liked/kept entity is added to ongoing MONITORING -- once the
  Understand layer is enabled (`ubiquity-understand-layer`), the feed
  periodically re-scans that entity for new articles/posts/comments and
  ingests them as "artifacts," on whatever refresh interval the pipeline
  is set to. The vote happens once (per entity, until you change it);
  the monitoring it triggers is continuous.
- A disliked/removed entity stops being monitored going forward -- it
  does not retroactively judge or remove any artifacts already ingested
  from it, and it says nothing about whether that entity's past content
  was "good" or "bad," only that it's not a source worth continuing to
  track for this feed's purpose.
- The `credibility_score`/`quality`/`local_focus`/`type` fields and the
  free-text evaluation notes (see "Full free-text AI evaluation notes"
  below) describe the SOURCE's general characteristics (is it a real
  outlet, how reliable is it, is it US-focused, etc.) -- they are inputs
  to the relevance-as-a-source judgment, not a review of any specific
  thing it published.
- Actually reading/analyzing the CONTENT an entity has produced (its
  individual articles/posts/comments once ingested) is a DIFFERENT, LATER
  step -- that's the Understand layer / Data Browser / Ubi chat / direct
  feed-stream API (see `ubiquity-understand-layer`, `ubiquity-ubi-chat`,
  `ubiquity-data-feed-api`), not this entity-review step.
Keep this distinction in mind when writing vote-queue reasoning or
suggest-pass justifications: "this source is unlikely to keep producing
relevant content" is a valid entity-review reason; "this one post was
low-quality" is not a reason to vote on the entity (it may be a reason to
flag a data/evaluation problem, but it's a different kind of claim).

## List entities for a feed -- CONFIRMED
```
GET /api/locations/api/v1/feeds/<feed_id>/entities?limit=100&offset=0&q=&order_by=vote&order=asc&type=all
  -> {entities: [...], total, dataset_count, source_count}
```
`feed_id` comes from the pipeline object (see `ubiquity-pipeline-creation`).
Query params observed in the UI:
- `limit`: page size -- UI offers 10/50/100/500.
- `offset`: pagination.
- `q`: free-text search over discovered sources (UI: "Search Sources").
- `order_by`: UI sort options map to `vote` ("Vote Status"), `name`,
  `type`, `created_at` ("Date Created").
- `order`: `asc` | `desc`.
- `type`: UI filter tabs are "All" / "Sources" / "Datasets" -- `type=all`
  for everything, **CONFIRMED on the wire**: `type=sources` (plural) for
  the Sources tab. `type=datasets` (plural, by the same pattern) is the
  presumed value for the Datasets tab, though it was not independently
  confirmed live (the test feed had 0 datasets, which disables that tab in
  the UI) -- the plural form is strongly implied by `sources` being
  plural, not singular as an earlier version of this skill guessed.

Each entity's `metadata` object (CONFIRMED shape, from 178 real Germany
renewable-energy entities) carries the fields the review workflow below
keys off of: `type` (seen: `institution`, `unknown`), `credibility_score`
(float 0-1), `language` (e.g. `de`, `en`, `de, en`, or messier
freeform strings like `de (German primary); en (likely available)` --
don't assume it's always a clean comma list), `local_focus` (`high` /
`medium` seen), `quality` (`good` / `fair` seen), `url`,
`discovery_job_id`, `location_uuid`, `name`, `description` (often empty
string), `original_url` (often `null`).

The UI also shows a "Show Rejected (N)" toggle, implying rejected/removed
entities are excluded by default and need an explicit filter/flag to
surface again.

## List current votes for a pipeline -- CONFIRMED
```
GET /api/locations/v1/entity-votes/pipeline/<pipeline_id>?limit=1000
  -> [{id, entity_id, pipeline_id, keycloak_user_id, vote_type, vote_reason,
       session_id, metadata, created_at, updated_at}, ...]
```
This is how the review UI knows which entities already have a vote without
having to toggle blind -- fetch this ALONGSIDE the entities list and join
on `entity_id` to show current vote state per row. Returns `[]` cleanly
when no votes exist yet (not an error). `pipeline_id` here, not `feed_id`
-- votes are scoped to the pipeline, entities are scoped to the feed; a
pipeline always has exactly one feed, but don't mix the two ids up when
calling these two endpoints.

Each entity row has four controls, confirmed live against a running
discovery job's results:
- **Like this source** (upvote)
- **Dislike this source** (downvote)
- **Flag this source** (flag for review/concern -- distinct from dislike)
- **More options** menu -> **Split Entity** (not yet exercised) and
  **Remove from Pipeline** (hard delete from the feed)

### Voting (like / dislike / flag) -- CONFIRMED
```
POST /api/locations/v1/entity-votes/toggle
Content-Type: application/json
{
  "entity_id": <int>,
  "pipeline_id": "<pipeline_uuid>",
  "keycloak_user_id": "<keycloak user UUID, NOT the email -- see note below>",
  "vote_type": "like" | "dislike" | "flag"
}
```
This is a genuine **toggle**:
- First call for a given `(entity_id, pipeline_id, user, vote_type)` ->
  `201 Created`, `{"action": "created", "vote": {...}}`.
- Calling again with the SAME `vote_type` on the same entity -> `200 OK`,
  `{"action": "removed", "vote": {...}}` (un-votes it).
- Calling with a DIFFERENT `vote_type` on the same entity does NOT first
  clear the old vote -- it just creates a second vote record (e.g. an
  entity can hold both a "dislike" and a "flag" at once, or you can like
  then dislike without the like being auto-removed). If you need
  "exactly one active vote per entity" semantics, explicitly toggle OFF the
  previous vote_type yourself before toggling ON the new one.
- The returned `vote` object's `keycloak_user_id` field is your account's
  **email** (e.g. `<ACCOUNT_EMAIL>`), but the REQUEST body's
  `keycloak_user_id` field must be the Keycloak **user UUID** (e.g.
  `<USER_UUID>`), not the email -- these are
  different values for the same field name on the way in vs. out. Get the
  UUID from the JWT access token's `sub` claim (decode the token's middle
  base64url segment) or from whatever `/userinfo`-style call the SPA uses
  on login -- do not assume the email works as a drop-in substitute.
- `vote.id`, `vote.vote_reason` (always seen `null` so far), `vote.session_id`
  (always seen `null`), `vote.metadata` (always seen `null`),
  `vote.created_at`/`updated_at` round out the response.

### Removing an entity -- CONFIRMED
```
DELETE /api/locations/api/v1/feeds/<feed_id>/entities/<entity_id>
  -> 200 {"message": "Entity removed from feed successfully"}
```
This is a hard delete -- the entity's count drops immediately (verified:
9 sources -> 8 after one removal) and it did not reappear in a subsequent
GET of the entities list in testing. Whether it lands in a recoverable
"rejected" bucket (the UI's "Show Rejected (N)" toggle) or is gone for good
was not confirmed -- treat removal as destructive until proven otherwise.

### Split Entity -- CONFIRMED functional end-to-end (preview + commit), both endpoints captured
**Correction**: an earlier pass of this skill wrongly concluded "Split
Entity" was a non-functional stub because clicking the menu item fired no
network call in that test. That conclusion was wrong -- the real flow was
missed because the preview call is slow (AI clustering) and that earlier
test didn't wait long enough / didn't have an XHR interceptor installed
(Angular's HttpClient uses XHR for this call, not `fetch`). The full flow,
confirmed on the wire including the destructive commit step:

**1. Preview (read-only):**
```
GET /api/locations/api/v1/entities/<entity_id>/split-preview
```
Takes several seconds (AI clustering over the entity's source URLs) -- use
the fire-and-forget pattern from `ubiquity-understand-layer`'s
`metrics/preview` note if driving this via `browser_exec` (`js()`'s own
`Runtime.evaluate` call has a short timeout that a direct
`await fetch(...)` will blow through; fire the promise onto a `window`
variable and poll it in a later call instead). Confirmed response shape
(real example, entity 53920 "Rats in New York City", 12 total sources
across 6 affected feeds):
```json
{
  "entity_id": 53920, "entity_name": "Rats in New York City", "total_sources": 12,
  "groups": [
    {"group_name": "Papua New Guinea", "source_count": 5,
     "source_ids": [247013, 246948, 246914, 246667, 246652],
     "urls": ["//en.wikipedia.org/wiki/Politics_of_Papua_New_Guinea", ...],
     "is_keeper": true},
    {"group_name": "Rats in New York City", "source_count": 4,
     "source_ids": [262810, 236914, 236913, 236912], "urls": [...], "is_keeper": false},
    {"group_name": "Artificial Intelligence Act", "source_count": 2, "source_ids": [...], "urls": [...], "is_keeper": false},
    {"group_name": "Liberal Democratic Federation of Hong Kong", "source_count": 1, "source_ids": [...], "urls": [...], "is_keeper": false}
  ],
  "discarded_urls": [],
  "feeds_affected": [1668, 1640, 1619, 936, 1665, 1650]
}
```
This targets exactly the "batch/crawl mismatch" problem (an entity whose
attached source URLs actually belong to unrelated topics) -- the preview
clusters the entity's source URLs by apparent topic and flags which
cluster is the `is_keeper`. **`is_keeper` does NOT mean "the
semantically-matching cluster"** -- in this example it landed on the
unrelated "Papua New Guinea" cluster rather than the "Rats in New York
City" cluster that actually matches the entity's own name, so don't
assume the keeper group is the one a human would intuitively pick.
`feeds_affected` matters: a single entity can be shared across MULTIPLE
feeds/pipelines simultaneously (6 in this example), so a split is a
cross-pipeline operation, not scoped to whichever pipeline's UI you
clicked from.

**CAVEAT -- the preview call appears to have result flakiness under rapid
repeat calls**: in testing (open menu, click Split Entity, close, repeat
within ~1-2s each time), one call returned a degenerate
`"No split needed... All 12 sources... belong to the same real-world
entity"` response instead of the 4-group breakdown every other call
(both earlier and later, against the identical entity) returned. Root
cause not isolated -- if you need a reliable preview, wait for the full
~8-10s response rather than polling impatiently, and if you get a "no
split needed" result on an entity you have reason to believe IS a
mismatch (e.g. you can see unrelated URLs in its source list), retry once
before trusting it.

**2. Commit the split -- CONFIRMED, DESTRUCTIVE, cross-feed:**
```
POST /api/locations/api/v1/entities/<entity_id>/split
Content-Type: application/json
{"groups": [
  {"group_name": "Papua New Guinea", "source_ids": [247013, 246948, 246914, 246667, 246652]},
  {"group_name": "Rats in New York City", "source_ids": [262810, 236914, 236913, 236912]},
  {"group_name": "Artificial Intelligence Act", "source_ids": [258566, 246951]},
  {"group_name": "Liberal Democratic Federation of Hong Kong", "source_ids": [245588]}
]}
```
(same `groups` the preview returned, but each entry trimmed to just
`group_name`+`source_ids` -- `source_count`/`urls`/`is_keeper` are
preview display-only and not sent back). `200 OK` response:
```json
{
  "original_entity_id": 53920, "original_entity_sources_kept": 5,
  "new_entities": [
    {"id": 57941, "uuid": "4a3c44f8-...", "name": "Rats in New York City", "source_count": 4},
    {"id": 57942, "uuid": "3cb22412-...", "name": "Artificial Intelligence Act", "source_count": 2},
    {"id": 57943, "uuid": "864b4bba-...", "name": "Liberal Democratic Federation of Hong Kong", "source_count": 1}
  ],
  "discarded_urls": [],
  "feeds_linked": [1668, 1640, 1619, 936, 1665, 1650]
}
```
**Key mechanics, all confirmed live:**
- The ORIGINAL `entity_id` is preserved and keeps whichever group was
  flagged `is_keeper` in the preview -- in this example that meant the
  original id 53920 (still named "Rats in New York City" in its own
  metadata, unaffected by the group reassignment) now only carries the 5
  Papua-New-Guinea-topic sources, NOT the New-York-rats-topic sources its
  name suggests. **The entity's display `name` is NOT automatically
  updated to match its new (possibly unrelated) source content** -- if
  you split an entity, check whether its name still makes sense
  afterward and consider renaming it (no rename endpoint confirmed in
  this skill family yet).
- Every NON-keeper group becomes a brand-new entity with a new numeric
  `id`/`uuid`, named after that group's `group_name`, and is linked
  (`feeds_linked`) to EVERY feed the original entity was in -- a split
  multiplies entity count across all affected feeds at once, not just the
  feed you were viewing when you triggered it.
- `original_entity_sources_kept` (5) matches the `is_keeper` group's
  `source_count` from the preview, confirming the kept/split accounting.
- The original entity's own `updated_at` timestamp bumps (confirmed via a
  follow-up `GET /entities/<id>`); its `uuid` does NOT change.
- This is DESTRUCTIVE and not scoped to a single pipeline -- treat it
  like `Remove from Pipeline` in terms of needing explicit user
  confirmation before executing on a real/production entity, especially
  since the `is_keeper` assignment can be counterintuitive (see above)
  and a user reviewing only the preview's group names might not
  immediately notice which group keeps the original id.

### Interceptor pattern used to capture the above
```js
window.__reqlog = [];
(function() {
  const orig = window.fetch;
  window.fetch = function(...args) {
    const url = args[0] && args[0].url ? args[0].url : args[0];
    const opts = args[1] || {};
    const p = orig.apply(this, args);
    p.then(async r => {
      let body=null; try{body=await r.clone().text();}catch(e){}
      window.__reqlog.push({url:String(url), method:opts.method||'GET', reqBody:opts.body, status:r.status, respBody:body});
    });
    return p;
  };
})();
```
Then after the click: `js("JSON.stringify(window.__reqlog.slice(-5))")`.
Angular's HttpClient used `fetch` for most calls observed in this skill
family, but NOT all -- the Jobs page and some vote-list calls go through
`XMLHttpRequest` instead, which this interceptor won't see. Add an XHR
override too (see `ubiquity-discovery-jobs` for the pattern) or just poll
`performance.getEntriesByType('resource')` for URL strings when `fetch`
hooking comes up empty -- it catches both.

## Downloading results -- CONFIRMED: client-side CSV, no export endpoint
"Download CSV" on the Discover tab does NOT call a dedicated export
endpoint. Confirmed on the wire: clicking it fires exactly these two
calls, then builds the CSV in the browser from the joined results:
```
GET /api/locations/api/v1/feeds/<feed_id>/entities?limit=1000&offset=0
GET /api/locations/v1/entity-votes/pipeline/<pipeline_id>?limit=500
```
(the first with no `type`/`q`/`order_by` params -- i.e. it always fetches
ALL entities up to the 1000 cap, ignoring whatever filter/sort/search was
active in the UI at the time of the click). If scripting a CSV export
yourself, just call these same two endpoints and join on `entity_id`
client-side -- there is nothing server-side to call instead.

## Full free-text AI evaluation notes per source -- CONFIRMED
The structured `credibility_score`/`quality`/`local_focus`/`type` fields on
the entity are NOT the whole story -- there IS a free-text reasoning record
per source URL, just on a separate endpoint the entities list doesn't
inline:
```
GET /api/locations/api/v1/source-evaluation-logs/by-url?url=<url-encoded source URL>
  -> {
       id, credibility_score, local_focus, quality,
       evaluation_details: {
         type, title, batch_index, description, topic_focus,
         evaluation_notes: "<long free-text paragraph>",
         matching_location, dataset_confidence, dataset_likely_format,
         dataset_provider_hint, is_behavioral_dataset, dataset_classifier_reason
       }
     }
```
`evaluation_notes` is the discovery agent's actual written reasoning for
that source -- typically an opening verdict sentence, then
`STRENGTHS: (1) ... (2) ...`, `LIMITATIONS: (1) ... (2) ...`,
`RECOMMENDED USE: ...`, and sometimes trailing `SUPPLEMENT WITH:` /
`ACKNOWLEDGE:` clauses, all as one inline-labelled paragraph (not JSON --
parse by splitting on those literal labels, see `_split_notes_sections` in
`scripts/entity_review.py`). This supersedes the earlier assumption in this
skill that no free-text reasoning field exists anywhere in the API --
`entities`/`result_data`/`parameters.context_report` genuinely don't have
it, but this dedicated by-URL endpoint does.
- Keyed by the entity's `url` (its primary URL, from `metadata.url`), NOT
  by `entity_id` -- there is no `by-entity-id` variant confirmed, only
  `by-url`. URL-encode the full URL as the `url` query param.
- Returns `200` with the object above when a log exists; in testing every
  entity with a non-empty `url` had one. If `url` is empty/missing on the
  entity, skip the call (nothing to look up).
- This is a per-REQUEST network call, not bundled into the entities list --
  fetching it for an entire large feed (100+ entities) means 100+ extra
  requests. Fetch it lazily, only for the entities you're actually about to
  show a human (e.g. the current page), and parallelize (the bundled
  script uses an 8-worker `ThreadPoolExecutor`) rather than fetching serially
  or for the whole feed up front.

## IMPORTANT: never auto-apply votes mid-review
When a user is actively reviewing a feed in chat (i.e. a `start` session is
open for this `feed_id`/`pipeline_id`), use `queue`/`queue-remove` for every
vote/removal call they give you and do NOT run `apply` until the user
explicitly says they're done reviewing (e.g. "apply", "done", "push my
votes", "commit"). Applying early changes live vote state mid-pass, which
defeats the whole point of `start`'s frozen order and can make `page`'s
`--only-unvoted` filtering shift under the user while they're still working
through the list. Only call `vote`/`remove` directly (bypassing the queue)
for one-off ad-hoc votes outside of an active review pass.

## IMPORTANT: offer the automated suggestion pass after every manual pass
Right after the user finishes a manual review pass and their votes are
applied (i.e. right after an `apply` call that was triggered by "I'm done"/
"apply"/"commit", not an ad-hoc mid-pass apply), ASK the user whether they
want you to run the automated cross-reference pass: fetch the full,
currently-unvoted entity list plus each one's evaluation-log notes, compare
them against the pattern of what the user has liked/disliked so far (see
"Suggesting additional votes from prior patterns" below), and surface
concrete up/down candidates for them to approve. Don't assume they want it
and don't skip asking just because they didn't ask for it this time -- this
is a standing offer to make after every manual-review-and-apply cycle, since
it's cheap to run and the user has asked for it explicitly before. If they
say yes, queue the suggested votes (do not auto-apply them) and let the
user confirm before `apply`.

## End-to-end review workflow -- CONFIRMED, scriptable, reusable
`scripts/entity_review.py` (bundled with this skill) wraps the endpoints
above into a CLI, verified live against a real 178-entity Germany feed.
It needs only `feed_id` and `pipeline_id` (get both from
`GET /api/locations/v1/pipelines/<pipeline_id>` or the `/pipelines` list
page) and reads the access token from the same
`~/.hermes/secrets/filterlabs_tokens.json` as `ubiquity-auth`'s script --
refresh it first if stale.

**Pitfall discovered while building this**: calling the API with Python's
builtin `urllib` and no `User-Agent` header gets a `403` with
`error code: 1010` from Ubiquity's edge/WAF, even with a valid Bearer
token -- the script sets a normal browser-style `User-Agent` on every
request to avoid this; keep that header if you write your own client
instead of using `browser_exec`'s in-page `fetch()` (which inherits a real
User-Agent automatically and never hit this).

```
# 0. Freeze the review order ONCE at the start of a pass (RECOMMENDED)
python3 entity_review.py start --feed-id <feed_id> --pipeline-id <pipeline_id> \
    --sort-by credibility --only-unvoted
#   -> snapshots the current entity id order to a session file at
#   ~/.hermes/cache/entity_review_sessions/<feed_id>_<pipeline_id>.json
#   and an empty queued_votes/queued_removals dict. Without this, `page`
#   falls back to a LIVE re-sort every call -- and because voting changes
#   an entity's state, re-sorting + --only-unvoted after each vote can
#   shift what "page N" means between calls. `start` fixes the order for
#   the whole pass so page 3 always means the same 5 entities, regardless
#   of what you vote on in between.

# 1. List all entities + current vote state, side by side
python3 entity_review.py list --feed-id <feed_id> --pipeline-id <pipeline_id>
#   -> prints a compact table: ID, VOTES (like/dislike/flag or '-'), CRED, TYPE, LANG, NAME
#   Add --sort-by {credibility,name,id} (default credibility) and --reverse
#   (highest-first) to control order; --only-unvoted hides anything already voted.

# 1b. Page through entities a few at a time, with full AI evaluation notes
python3 entity_review.py page --feed-id <feed_id> --pipeline-id <pipeline_id> \
    --page 0 --page-size 5 --only-unvoted
#   -> one card per entity: header line (id/name/credibility/type/vote --
#   shows "(queued, not yet applied)" for anything staged via `queue` below
#   but not yet pushed), then VERDICT (the agent's opening verdict sentence
#   from the real evaluation-log notes, see below), STRENGTHS/CONCERNS/USE AS
#   sections when the notes follow that labelled pattern, then the primary
#   URL and a count of any other source URLs on the entity.
#   If a session exists (from `start`), walks ITS frozen order -- --sort-by/
#   --reverse are ignored in that case (they only matter for `start`).
#   Fetches the real per-URL evaluation log (see section above) for just
#   this page's rows by default -- pass --no-with-notes to skip that and
#   fall back to the structured credibility/quality/local_focus/type
#   one-liner instead (much faster, no extra network calls, but less detail).
#   Prints a hint for the next --page call when more entities remain.
#   Default --page-size is 5 -- small enough to read a handful at a time in
#   chat without flooding it; raise it for a human reading a file instead.

# 1c. Or render the SAME page as a standard markdown table instead of cards
python3 entity_review.py page --feed-id <feed_id> --pipeline-id <pipeline_id> \
    --page 0 --page-size 5 --only-unvoted --table
#   -> | ID | Name | Source URLs | Type | Notes | Vote status |, ONE
#   physical line per entity row (standard CommonMark table syntax, pipes
#   escaped inside cell text). Hermes's TUI does its own column-width
#   measurement and per-cell word-wrapping at RENDER time (see
#   agent/markdown_tables.py / ui-tui/.../markdown.tsx), including an
#   automatic vertical key:value fallback if a row is too tall/wide for
#   the terminal -- it does NOT interpret '<br>' or manual box-drawing as
#   line breaks, both just show up as literal text. So this function
#   deliberately emits plain single-line cells and lets the renderer
#   handle wrapping; don't try to hand-wrap cell text yourself. Notes
#   holds the FULL evaluation-log writeup untruncated (lede +
#   STRENGTHS/CONCERNS/USE AS joined with spaces, since newlines inside a
#   markdown table cell break the row) -- nothing is summarized away.

# 2a. RECOMMENDED when using `start`: stage votes, review the whole batch,
#     THEN push them all at once -- keeps the frozen order's --only-unvoted
#     filtering stable until you're actually ready to commit
python3 entity_review.py queue --feed-id <feed_id> --pipeline-id <pipeline_id> \
    --entity-id <id> --vote-type like   # or dislike / flag / clear
python3 entity_review.py queue-remove --feed-id <feed_id> --pipeline-id <pipeline_id> --entity-id <id>
# ... repeat queue/queue-remove for everything you decided on this pass ...
python3 entity_review.py apply --feed-id <feed_id> --pipeline-id <pipeline_id>
#   -> pushes every queued vote (POST .../entity-votes/toggle) and queued
#   removal (DELETE .../entities/<id>) to the live API in one pass, prints
#   OK/FAILED per entity. On success the applied action is REMOVED from
#   the queue (failed ones -- e.g. an expired token -- stay queued so you
#   can refresh the token and retry `apply` without resending anything
#   that already landed). This matters because vote:toggle is NOT
#   idempotent -- re-sending an already-applied vote flips it back off,
#   so a stale/un-cleared queue silently undoes prior votes on the next
#   `apply`. Run `start` again only when you want to begin a completely
#   fresh pass (new frozen order); it is not required between `apply`
#   calls within the same pass.

# 2b. Alternative: vote/remove IMMEDIATELY, bypassing the queue (fine for
#     a handful of ad-hoc votes outside a `start`-based review pass, but if
#     you've already run `start` for this feed/pipeline this will immediately
#     change what counts as "voted" for `page`'s --only-unvoted filtering --
#     prefer `queue` + `apply` once a session is active)
python3 entity_review.py vote --pipeline-id <pipeline_id> --entity-id <id> --vote-type like
python3 entity_review.py vote --pipeline-id <pipeline_id> --entity-id <id> --vote-type dislike
python3 entity_review.py vote --pipeline-id <pipeline_id> --entity-id <id> --vote-type flag
python3 entity_review.py remove --feed-id <feed_id> --entity-id <id>

# 3. After a review pass, get plain-language suggestions for Agent Settings
python3 entity_review.py suggest --feed-id <feed_id> --pipeline-id <pipeline_id>
```
**On the evaluation notes shown by `page`**: by default `page` fetches the
real per-URL evaluation log (see "Full free-text AI evaluation notes"
above) for each row on the current page and renders its VERDICT/STRENGTHS/
CONCERNS/USE AS sections -- this genuinely reflects the discovery agent's
written reasoning, not a guess. A small number of entities' notes don't
follow the labelled STRENGTHS:/LIMITATIONS:/RECOMMENDED USE: pattern (free
text varies); for those, only VERDICT (the lede sentence) prints. If
`--no-with-notes` is passed, or no evaluation log exists for a row's URL
(e.g. empty `url` field), it falls back to a plain-language rendering of
just the structured `credibility_score`/`quality`/`local_focus`/`type`
fields instead -- say so plainly if asked, since that fallback carries much
less detail than the real notes.

The recommended workflow for a human reviewing a large feed in chat: run
`start` once to freeze the order, then run `page` with a small
`--page-size` (3-5) to read a batch, use `queue`/`queue-remove` to stage the
user's like/dislike/flag/remove calls for those IDs (this does NOT call the
vote/remove API yet), advance to `--page <n+1>` for the next batch, and
repeat until the whole list is reviewed. Only call `apply` at the end (or
at natural checkpoints) to push everything staged so far to the live API in
one pass. This matches a natural "review everything, then commit" flow and
guarantees page numbers stay stable even with `--only-unvoted` active --
queuing a vote marks it "(queued, not yet applied)" in `page`'s display
without actually changing the entity's live vote/filter state until
`apply` runs.
`suggest` is a pure heuristic over the metadata fields confirmed above
(`type`, `language`, `local_focus`, `quality`, `credibility_score`): it
compares the distribution of each field between liked and disliked
entities, flags fields where one value is disproportionately
liked/disliked, and prints concrete `agent_config` dotted-paths to adjust
(e.g. "entities of quality='fair' are disproportionately disliked ...
consider adjusting agent_config.evaluation.quality_standards"), plus an
average-credibility comparison suggesting a `credibility_threshold` value.
It makes NO API calls and changes nothing by itself -- a human (or the
calling agent, with the user's explicit go-ahead) reads the suggestions and
decides whether to apply them via the Agent Settings PATCH documented in
`ubiquity-pipeline-creation`. It prints "No votes recorded yet" and exits
cleanly if nothing has been voted on.

Important context the `suggest` output reminds you of: voting ALREADY
feeds into the next discovery job automatically via `vote_context`
(liked_entities/disliked_entities by name+type -- see
`ubiquity-discovery-jobs`), independent of whether you also tune Agent
Settings. Changing `agent_config` is for steering future discovery
queries/evaluation criteria more broadly; it's an addition, not a
prerequisite, to voting mattering.

This workflow is pipeline/feed-agnostic -- pass any `feed_id`/`pipeline_id`
pair, not just the Germany test pipeline it was built and verified
against.

## Suggesting additional votes from prior patterns (manual cross-reference pass)
`suggest` (above) only compares STRUCTURED fields (type/language/
local_focus/quality/credibility_score) between liked and disliked entities
-- it does not read the free-text evaluation notes or recommend specific
entity IDs to vote on next. For that, there is no dedicated subcommand yet;
do it manually with the building blocks already in `entity_review.py`:
1. `fetch_entities` + `fetch_votes` + `build_review_table` to get every
   entity, split into voted vs. unvoted.
2. For every UNVOTED entity with a non-empty `url`, call
   `fetch_evaluation_log(token, url)` (parallelize with a
   `ThreadPoolExecutor`, e.g. 12 workers -- 150+ entities fetched
   sequentially is slow).
3. Look at the free-text `evaluation_notes` (plus the entity name) for
   patterns that match what the user already liked/disliked: liked
   entities in this workflow tended to be nonprofits/cooperatives,
   official government sources, academic/research institutes, and
   specialized/dedicated renewable-energy outlets (advocacy, news
   platforms, trade associations); disliked entities tended to be
   commercial vendors (sales-oriented, promotional, narrow single-product
   focus), crowdsourced business directories, and sources where the
   evaluation notes themselves flagged "not suitable for research" /
   "marginal relevance" / topic drift. A simple keyword-presence scoring
   pass over the notes text (positive terms: cooperative, nonprofit,
   government, policy, academic, research institute, dedicated/
   specialized news; negative terms: commercial bias, sales-oriented,
   promotional, narrow scope, marginal relevance, not suitable for
   research, crowdsourced directory) is enough to surface good candidates
   -- it doesn't need to be fancy, just consistent with the user's own
   stated reasoning so far.
4. Also flag data-quality problems independent of the like/dislike
   pattern -- e.g. an entity whose `urls` list is mostly unrelated pages
   (a batch/crawl mismatch) is worth flagging for a dislike/removal even
   if its primary URL and name look on-topic (seen in practice: a
   Wikipedia "Renewable energy in Germany" entity whose other 8 source
   URLs were completely unrelated -- Bangladesh textile industry,
   Sheikh Hasina, a New Zealand wine region).
5. Present the candidates with the specific evaluation-note language that
   justifies each one, and `queue` (never auto-`apply`) them once the user
   approves -- same rule as every other vote in this skill.

This is a genuinely useful standing offer (see "offer the automated
suggestion pass" above) precisely because it's cheap to run against
whatever's left unvoted and keeps surfacing candidates the user didn't
have to find by paging through everything by hand.
