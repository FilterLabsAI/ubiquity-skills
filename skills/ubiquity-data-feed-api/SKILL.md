---
name: ubiquity-data-feed-api
description: Use to query Ubiquity feed content via raw Data Feed API.
---

# Ubiquity: Data Feed (Curator Locations) API

Covers the "Curator Locations API" -- a single-endpoint REST API for
pulling raw content items directly from a feed's vector store, bypassing
the Understand-layer endpoints (`artifacts/preview`, `metrics/preview` --
see `ubiquity-understand-layer`). Source: user-provided swagger file
(`doc.json`, swagger 2.0), confirmed live against the Germany pipeline
(feed_id 1663) on 2026-10-02. Requires a valid Bearer token -- see
`ubiquity-auth`.

**When to use this skill:** whenever the user asks Hermes to directly
reason about/analyze/summarize feed content (not just view or render the
Understand-layer UI panels) -- e.g. "what are people saying about X in
this feed", "summarize the last week of articles", "find all mentions of
Y entity" -- fetch the raw data via THIS API (`/stream`), not by scraping
the UI or re-deriving it from `artifacts/preview`/`metrics/preview`. This
endpoint gives direct, filterable access to the full underlying corpus
(up to `total` items, far beyond the Understand layer's 1000-item cap)
with full `content` text, which is what reasoning/summarization tasks
need -- the Understand-layer preview endpoints are tuned for the UI's
chart/table display (truncated/capped) and for driving Ubi chat, not for
Hermes's own direct analysis.

## Endpoint
```
GET https://ubiquity.filterlabs.ai/api/locations/api/v1/feeds/{id}/stream
Authorization: Bearer <token>
```
`{id}` is the numeric `feed_id` (same id used throughout the
Understand-layer skills, NOT the pipeline/search UUID).

## Query parameters (per swagger, with live-confirmed notes)
| Param | Type | Notes |
|---|---|---|
| `limit` | int | default 100, min 1, max 1000. |
| `offset` | int | default 0, min 0, max 10000 -- offset-based pagination, capped at 10000 (use `cursor` to page past that). |
| `cursor` | string | ISO 8601 timestamp for cursor-based pagination. **UNCONFIRMED / possibly buggy**: re-querying with the `next_cursor` value from a prior response returned the SAME leading item again rather than advancing, in one live test with `limit=2`. Verify cursor advancement behavior further before relying on it for exhaustive pagination; `offset` may be more predictable up to its 10000 cap. |
| `order_by` | string | `published_at` (default) or `scraped_at`. |
| `content_max_length` | int | default 500, min 0, max 10000. **Confirmed**: truncates `content` and appends a literal `...` suffix (3 chars) -- requesting `content_max_length=20` returns a 23-character string ending in `...`. |
| `include_vectors` | string | comma-separated: `search`, `cluster`. Adds a `vectors` object (vector name -> float32 array) to each item -- not tested live (payload-heavy, likely only useful for embedding-level analysis, not display). |
| `date_from` / `date_to` | string | RFC3339 or `YYYY-MM-DD`. Confirmed working together with `text_search` in one live call. |
| `text_search` | string | Full-text search across headline and content. Confirmed. |
| `entity_ids` | string | comma-separated entity IDs. |
| `entity_types` | string | comma-separated: `institution`, `individual`, or empty string. |
| `urls` | string | comma-separated URL prefixes to filter by. |

## Response shape (confirmed live, with undocumented fields)
```json
{
  "items": [
    {
      "uuid": "...",
      "headline": "...",       // can be empty string
      "content": "...",
      "url": "...",
      "published_at": "2026-10-01T06:09:02Z",
      "scraped_at": "2026-10-01T17:07:20Z",
      "entity_id": "50655",
      "entity_type": "institution",
      "authors": "deutsche-bank",   // NOT in the swagger definitions, seen live, string (sometimes empty)
      "metrics": {"comments": 12, "likes": 193}  // NOT in swagger, seen on social/micro_blog items only (engagement counts); absent on article-type items
    }
  ],
  "pagination": {
    "limit": 2,
    "total": 56314,
    "has_more": true,
    "next_cursor": "2026-10-01T06:09:02.773000"
    // "offset" also documented in the schema but not observed in a response that used cursor-based paging
  }
}
```
The swagger's `definitions.qdrant.StreamItem` schema is INCOMPLETE --
`authors` and `metrics` are real fields returned live that aren't listed
in the swagger file. Don't treat the swagger definitions as exhaustive;
prefer a live sample call when building anything that depends on exact
field presence.

## Pitfalls
- **Bad/future `published_at` dates observed on Wikipedia-sourced items**:
  seen live values of `2065-10-02` and `2050-10-02` on items whose `url`
  was a German Wikipedia renewable-energy article -- these are almost
  certainly extraction/parsing errors on the source side (Wikipedia pages
  don't have per-paragraph publish dates, so whatever heuristic assigned
  one produced garbage), not a bug in this API. Don't assume `published_at`
  is always sane/recent -- validate/filter before using it for date-range
  logic, especially on non-journalistic source types.
- This is a lower-level, higher-volume endpoint than `artifacts/preview`
  (Understand layer) -- `total` here was 56314 for a feed where
  `artifacts/preview` caps at 1000. Use this API when you need the FULL
  underlying corpus (e.g. exhaustive export, embedding-level work via
  `include_vectors`), and the Understand-layer endpoints when you want
  the same filtering/scoring behavior the Feed Data Artifacts UI uses.
- No `metricName`/custom-metric-score filtering here -- that's an
  Understand-layer-only concept (see `ubiquity-understand-layer`'s
  `metrics/preview`). This API only knows about `entity_ids`/
  `entity_types`/`text_search`/`urls`/date range, not custom metrics.
