---
name: ubiquity-onboarding
description: New-user overview of the full Ubiquity workflow + diagrams.
---

# Ubiquity: new-user onboarding overview

This is the map of the whole product for a brand-new user -- what order
things happen in, which skill covers each step, and how a user goes from
a plain-language data question to a running, analyzable feed. Every step
below links to the skill that has the full confirmed mechanics; this
skill is the index + narrative, not a replacement for them.

Linked files: `references/openapi.json` (OpenAPI 3.0 spec for every
endpoint exercised across the `ubiquity-*` skill family) and
`references/flowcharts.md` (Mermaid diagrams of the end-to-end workflow).

## The 8-step workflow

1. **Ask a data question in plain language.** e.g. "News and social media
   about renewable energy policy in Germany." No account setup beyond
   login is needed first -- see `ubiquity-auth`.
2. **Build a pipeline via the Discover chat.** Ubi ("the discovery bot")
   parses your sentence into LOCATION / TOPIC / entity-type chips, shows
   you what it found, and asks "Would you like to discover sources for
   this query?" Confirming creates the pipeline + its feed. See
   `ubiquity-pipeline-creation` -- including the important "verify the
   resolved location" check for multi-country/supranational queries
   (EU/UN/NATO geocode wrong by default). Under the hood, every parse AND
   every pre-confirmation chat refinement (Change Location, Add <place>,
   Adjust Topics, etc.) is the SAME `POST /api/orchestrator/search/unified`
   call -- refinements just add `prior_query`/`prior_entities`/
   `prior_context`/`session_id` carried forward from the previous turn.
   There is no separate chat-message endpoint for this phase. Skipping
   automated discovery entirely via "Import Sources" has three distinct
   sub-flows (Plain Text / CSV / Behavioral Dataset), each hitting a
   different endpoint -- see `ubiquity-pipeline-creation`.
3. **Tune Agent Settings** (optional but recommended) before or
   immediately after the first discovery job -- these bias HOW the
   discovery/evaluation agents search and filter sources (query volume,
   creativity, language preference, credibility/quality thresholds,
   custom instructions). Settings live under the pipeline object's own
   `metadata.agent_config`/`metadata.discovery_config` -- `GET`/`PATCH`
   `/api/locations/v1/pipelines/<pipeline_id>` directly, no UI required
   (Quick Presets are pure client-side form state; nothing persists until
   the PATCH fires). Settings only apply going FORWARD, never
   retroactively. See `ubiquity-agent-settings` for the full read/write
   API calls plus a recommendation strategy by use case (news monitoring,
   social/sentiment, government/policy, economic data).
4. **Run the discovery job and review entities.** Discovery is a slow
   agentic job (15-20+ min, sometimes longer); it searches, evaluates,
   and proposes candidate SOURCES ("entities") -- people, accounts,
   publications, outlets -- not individual pieces of content. Reviewing
   an entity is a judgment about whether that SOURCE is likely to keep
   producing content relevant to the questions/conversations the end
   user cares about -- NOT a review of any specific article/post/comment
   it has already published; content-level review happens later, once
   artifacts are ingested (step 6). Once sources appear, review them:
   like/dislike/flag/remove, read the AI's own written evaluation notes
   per source, and optionally run the automated suggestion pass. An
   entity whose attached source URLs actually span unrelated topics
   (a crawl/batching mismatch) can also be split into separate entities
   via a preview-then-commit flow -- destructive and can span multiple
   feeds at once, since one entity can be shared across pipelines. Your
   votes feed directly into the NEXT discovery job's prompt as positive/
   negative examples. See `ubiquity-entity-review` (which has the full
   explanation of this source-vs-content distinction) and
   `ubiquity-discovery-jobs` (including the "never stack discovery jobs"
   rule and the two-save-paths distinction).
5. **Scale up discovery as needed.** "Increase Coverage" (Low/Medium/
   High/X-High) launches a bigger follow-up job once you're happy with
   the direction entities are heading, incorporating your votes. One
   pipeline runs one discovery job at a time. See `ubiquity-discovery-jobs`.
6. **Enable the Understand layer and set a refresh interval.** This is
   where the entities kept in step 4 actually start being MONITORED --
   each liked/kept entity is periodically re-scanned for new articles/
   posts/comments, which get ingested into analyzable "artifacts"
   (individual pieces of content). This is the point where "is this a
   good source" (step 4) turns into "what is this source actually
   saying" (this step onward) -- the two are genuinely different
   questions answered at different stages, see `ubiquity-entity-review`.
   Set how often the feed re-syncs (Do Not Update / 12h / Daily / Weekly
   / etc -- a single auto-saving dropdown). See `ubiquity-understand-layer`. To
   check whether artifacts have actually started arriving yet (vs. still
   "Collecting data..."), poll `GET /api/understand/artifacts/count/
   <feed_id>` -- this was broken (returned the same stale account-wide
   number for every feed) until a 2026-10-06 server-side fix; it's now
   confirmed accurate and is the cheap/fast way to check ingestion
   progress, preferred over fetching full records via `artifacts/preview`
   just to read its `total_count`.

7. **Add metrics.** Create custom scored metrics (Sentiment, Stance
   toward an entity, free-text Entity extraction, or a fully custom
   prompt) that run against every ingested artifact, producing a time
   series you can chart and query. See `ubiquity-metric-generators`.
   Two metric fields, `filter_prompt`/`filter_distance`, exist and are
   settable via the API with no UI control -- their reasoned purpose is
   a semantic pre-filter on which artifacts a metric scores, but this is
   a planned feature not yet confirmed to have an observed effect; don't
   promise a user it works until re-verified.
8. **Analyze the data -- three ways, pick based on the question:**
   - **Ubi chat** (`ubiquity-ubi-chat`) -- ask natural-language questions
     about the feed; grounded answers with real citations, can reference
     your custom metrics by name, can render charts on request. Drive
     this via the direct `understand/chat/sessions` API (synchronous,
     reply returned inline) rather than scripting the SPA -- see
     `ubiquity-ubi-chat` for the confirmed request/response shapes and
     why the browser path is fragile for this.
   - **Data Browser** (chart + artifact table on the Understand tab,
     documented in `ubiquity-understand-layer`) -- visual/UI exploration:
     a metric-over-time chart (or a raw "Sample Distribution" document
     count) plus a paginated, filterable table of individual artifacts.
   - **Direct API access** (`ubiquity-data-feed-api`) -- when Hermes
     itself needs to directly reason over/summarize/analyze feed content
     (not just render a UI view), pull the raw corpus via the
     `/feeds/{id}/stream` endpoint -- full, untruncated content, no
     1000-item display cap, filterable by date/text/entity.

   Optional: **Pipeline Routing** (`ubiquity-pipeline-routing`) connects
   multiple pipelines' feeds together (useful when a question spans more
   locations/topics than one pipeline should carry) and **Data Egress**
   pushes a feed's content to a third party (Meltwater integration seen
   so far). Routes have a `filter_mode`/`filter_config` pair that's
   settable via the API (no UI control) but whose actual effect on what
   flows through the route is unverified -- a live test didn't observe a
   difference within a short window; treat as accepted-on-write only
   until re-tested with a longer observation window or a fresh discovery
   job on the source pipeline.

## Skill map (which skill, which step)

| Step | Skill |
|---|---|
| Login / tokens | `ubiquity-auth` |
| Parse a question -> create a pipeline | `ubiquity-pipeline-creation` |
| Choose/tune Agent Settings | `ubiquity-agent-settings` |
| Review discovered sources, vote | `ubiquity-entity-review` |
| Launch/scale/cancel discovery jobs | `ubiquity-discovery-jobs` |
| Enable Understand layer, refresh interval, data browser | `ubiquity-understand-layer` |
| Create custom metrics | `ubiquity-metric-generators` |
| Chat with Ubi about the feed | `ubiquity-ubi-chat` |
| Direct raw-data API access for Hermes-side reasoning | `ubiquity-data-feed-api` |
| Connect pipelines together / egress | `ubiquity-pipeline-routing` |

## Key cross-cutting rules (apply at every step)
- Never launch a new discovery job as a side effect of an unrelated save
  (saving Agent Settings, adding a chat-driven location/topic refinement)
  -- those are pure state saves; only an explicit "Yes, Discover Sources"
  / coverage-level button actually launches a job (`ubiquity-discovery-jobs`).
- `feed_id` (artifacts, metrics, chat, refresh interval, votes-list-by-
  pipeline aside) vs `pipeline_id` (agent settings, routes, discovery
  jobs) are different ids on the same object -- keep both once you have
  them (`GET /api/locations/v1/pipelines/{id}` returns both).
- Changes to Agent Settings and metric generators apply going forward
  only -- never retroactively re-score/re-search past data.
- Everything requires a valid Bearer token refreshed via `ubiquity-auth`;
  tokens expire ~30 min, re-bootstrap browser sessions as needed.
