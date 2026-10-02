# Ubiquity API recon notes (captured live, 2026-10-01)

Auth: Keycloak realm filter-labs-web, client web-app, ROPC grant works (see filterlabs_auth.py).
Frontend SPA (ubiquity.filterlabs.ai) auth bootstrap: set localStorage key `access_token` to a
valid Bearer token, then (re)load the page -> SPA treats you as logged in. (No need to drive the
login form.) Also calls `GET {auth}/realms/filter-labs-web/protocol/openid-connect/userinfo`.

All backend calls go through the SPA's own origin as reverse-proxied paths:
  https://ubiquity.filterlabs.ai/api/<service>/<path>
Services seen so far: `locations`, `orchestrator`, `understand`. All require
`Authorization: Bearer <access_token>` header, same token as Scout.

## Pipelines (locations service)
- GET /api/locations/v1/pipelines?limit=10&offset=0&order_by=created_at&order=DESC
    -> {items?... } list of pipelines (none yet seen non-empty besides create)
- GET /api/locations/v1/pipelines?saved_search_id=<uuid>&limit=300
- POST /api/locations/v1/pipelines   (create; triggered by "Build Pipeline" / "Yes, Discover
  Sources" flow -- exact body not yet captured, but response/GET shows resulting shape:)
    {
      id, keycloak_user_id, name, saved_search_id, feed_id, session_id,
      auto_sync_enabled, sync_on_job_completion, sync_on_map_change,
      metadata: {
        discovery_config: {max_queries, max_sources, min_sources},
        agent_config: {
          evaluation: {quality_standards, local_focus_priority, credibility_threshold, topic_relevance_weight},
          search_generation: {focus_types[], max_queries, creativity_level, language_preference},
          datasets_discovery: {providers[], enable_dataset_hunting}
        }
      },
      created_at, updated_at, search_name, search_query,
      search_filters: { entities: [{type: location|topic|entity_type, value, aliases, metadata,
                          languages, confidence, normalized_value}], location_uuid },
      feed_name
    }
- GET /api/locations/v1/pipelines/<pipeline_id>  -> same shape as above (used to read agent
  settings / metadata)
- PUT/PATCH /api/locations/v1/pipelines/<pipeline_id>  -> used by "Save Settings" (Agent Settings
  dialog) to persist metadata.agent_config. Exact verb not confirmed (sniff with DevTools or test
  PUT vs PATCH); body likely full pipeline object or partial metadata patch.
- GET /api/locations/v1/permissions/pipeline/<pipeline_id>
- GET /api/locations/v1/permissions/organization/<org_id>
- GET /api/locations/v1/organizations
- GET /api/locations/v1/admin/me/capabilities

## Saved searches / feeds (locations service)
- GET /api/locations/api/v1/saved-searches
- GET /api/locations/api/v1/feeds
- GET /api/locations/api/v1/feeds/<feed_id>
    -> {id, uuid, name, refresh_interval ("7 days" etc, human string), force_review_for_auto_discover,
        metadata, created_at, updated_at}
- Data Refresh Interval UI options: "Do Not Update", "Every 12 Hours", "Daily", "Every 2 Days",
  "Weekly", "Monthly" -> presumably PATCH /api/locations/api/v1/feeds/<id> {refresh_interval: ...}
- GET /api/locations/api/v1/feeds/<feed_id>/metric_prompts  -> metric generator list (null when
  none exist yet)
- GET /api/locations/api/v1/feeds/<feed_id>/entities?limit=100&offset=0&q=&order_by=vote&order=asc&type=all
    -> {entities: [...], total, dataset_count, source_count}  (entity/source review list; vote
    field implies upvote/downvote state per entity, type=all filters source/dataset/etc)
- GET /api/locations/api/v1/entities/by-location/<location_uuid>

## Jobs (locations + orchestrator services -- two parallel job views)
- GET /api/locations/api/v1/jobs?limit=10
- GET /api/locations/api/v1/jobs/count , /count/status/{pending,running,completed,failed,cancelled}
- GET /api/locations/api/v1/jobs/<job_id>
    -> {id, location_uuid, location_name, job_type ("curation" seen), status (pending/running/
        completed/failed/cancelled), progress, error_message, parameters (base64?), result_data,
        created_at, updated_at, completed_at, pipeline_id}
- POST /api/orchestrator/api/v1/jobs/create   -- launches discovery job (triggered by "Yes,
  Discover Sources" / "Increase Coverage" / big discovery runs). Body not yet captured.
- GET /api/orchestrator/jobs/<job_id>/async-status
    -> {job_id, pending_count, processed_count, failed_count, total_count, all_complete,
        has_async_work, last_updated, snapshots}

## Search / discovery entry point (orchestrator service)
- POST /api/orchestrator/search/unified  -- called right after "Build Pipeline" submit, parses
  the free-text query into location/topic/entity_type filters shown in the UI chips (Discover
  tab). Body/response not yet captured in detail but drives search_filters.entities[] seen in
  pipeline object above.
- GET /api/orchestrator/datasets/behaviors  -- behavioral dataset listing

## Understand layer (understand service)
- GET /api/understand/chat/sessions?keycloak_user_id=<url-encoded email>&limit=50&offset=0&feed_id=<id>
    -> [] when none; this is the "Ubi" chatbot session list, scoped per feed + user
- GET /api/understand/artifacts/count/<feed_id>  -> {count, feed_id}
- GET /api/understand/artifacts/preview  -- preview of ingested artifacts (body/query params TBD)
- "Enable Ubi" toggle on the Understand tab turns on analysis; appears tied to feed having
  artifacts (shows "Collecting data... pipeline is initializing" until then)
- Suggested chat prompts seen in UI (likely canned, not API-sourced):
    "Summarize the recent artifacts from my feed, highlighting key themes and important findings."
    "List the main themes and topics that appear in the recent artifacts."
    "Analyze and evaluate the overall tone and sentiment of the recent artifacts."
- "New Chat" button -- chat message send endpoint not yet captured (need POST, likely
  /api/understand/chat/... with feed_id + message, streaming response probably SSE/websocket)

## Metric Generators (Understand tab, "METRIC GENERATORS" section)
- "New Metric" button -- not yet exercised (pipeline was still initializing); likely POST to
  /api/locations/api/v1/feeds/<feed_id>/metric_prompts or similar understand-service endpoint.

## Pipeline Routing / Egress (Share tab)
- "Pipeline Routes" section: connect this pipeline to other pipelines as source/destination of
  entity flows ("Connect a pipeline" button) -- aggregate city->state or fan state->city pattern.
  Endpoint not yet captured.
- "Data Egress" section: third-party push integrations. Only "Meltwater" seen so far:
    fields: Meltwater API key (write-only, encrypted), Company ID (optional), Import tag
    (optional); "Save integration" button; toggle "Send this feed to Meltwater". Endpoint not
    yet captured (likely /api/locations/api/v1/feeds/<id>/egress or /integrations/meltwater).

## Agent Settings dialog (Discover tab, "Agent Settings" button)
Full set of controls seen:
  Quick Presets: Balanced | Social Media Boost | News Focus | Behavioral Datasets Boost
  Toggle: "Hunt for behavioral datasets" -> metadata.agent_config.datasets_discovery.enable_dataset_hunting
  Search Generation Agent:
    - Number of Search Queries (slider 5-50, default 15) -> search_generation.max_queries
    - Creativity Level: Low/Medium/High -> search_generation.creativity_level
    - Source Types to Focus On: News, Government, Blog, Community, Social Media (checkboxes)
        -> search_generation.focus_types[]
    - Language Preference: Native Only / Mixed / English Only -> search_generation.language_preference
    - Custom Instructions (free text)
  Evaluation Agent: (section present but not expanded/captured in detail yet -- likely maps to
    metadata.agent_config.evaluation.{quality_standards, local_focus_priority,
    credibility_threshold, topic_relevance_weight})
  Buttons: Reset to Defaults, Cancel, Save Settings (-> PUT/PATCH pipeline metadata)

## Pipeline creation / discovery chat flow (Discover tab walkthrough)
1. Go to /search, type free-text query into textarea (placeholder "Describe a location and
   optional topic to get started"), click "Build Pipeline".
2. SPA calls POST /api/orchestrator/search/unified, navigates to
   /search-results?q=<url-encoded query>, shows parsed chips (LOCATIONS/TOPIC/TYPE) + a map +
   a "Ubi" chat bubble: "I found these in your search: ... Would you like to discover sources
   for this query?" with buttons [Yes, Discover Sources] [No, Revise Query] plus an "Import
   Sources" panel (manual URL/CSV/behavioral-dataset import, bypasses discovery).
3. Click "Yes, Discover Sources" -> SPA creates the pipeline (POST /api/locations/v1/pipelines),
   creates the feed, and launches the discovery job (POST /api/orchestrator/api/v1/jobs/create),
   toasts "Pipeline ... saved successfully!" then "Discovery agent launched successfully!".
   Lands on /pipelines/<id>? (confirm exact route) with Discover tab showing
   "Discovery Status: pending/running", entity/source review grid (initially 0), and buttons:
   "Revise Rankings", "Agent Settings", "Download CSV", and tools: "Discover a few sources",
   "Review", "Increase Coverage", "Enable Ubi", "Search Sources", filters (All/Sources/Datasets),
   sort (Vote Status/Name/Type/Date Created), per-page (10/50/100/500), "Show Rejected (N)".
4. Discovery job runs ~10-15+ min (job_type "curation"); poll
   /api/locations/api/v1/jobs/<job_id> and/or /api/orchestrator/jobs/<job_id>/async-status for
   status until completed, then GET feeds/<feed_id>/entities to see discovered sources.
5. Entity/source review grid supports per-row upvote/downvote/remove (sort by "Vote Status"
   implies a vote field per entity) -- NOT yet exercised with real data (job was still running).
   "Increase Coverage" button presumably re-launches discovery with broader settings ("larger
   discovery jobs").

## Still TBD (job finishes ~10-15 min after being kicked off at 2026-10-01T15:26 UTC; pipeline_id
<PIPELINE_UUID>, feed_id <FEED_ID>, job_id <JOB_UUID>):
- Exact entity upvote/downvote/remove endpoint + payload shape
- Exact "Increase Coverage" / larger discovery job endpoint+params
- Metric generator create/view endpoints
- Pipeline routing (connect-a-pipeline) endpoint
- Egress (Meltwater) save endpoint
- Ubi chat send-message endpoint (likely /api/understand/chat/sessions POST then
  /api/understand/chat/sessions/<id>/messages or similar, possibly SSE streaming)
- Data feed query API (artifacts/preview, artifacts list/query) full shape
- POST /api/locations/v1/pipelines and POST /api/orchestrator/api/v1/jobs/create request bodies
  (need to repeat the create flow with request-body logging, e.g. override XHR.send too, not just
  fetch, since Angular HttpClient may use XHR under feature-detection)
