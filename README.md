# ubiquity-skills

Hermes skills for operating the Ubiquity platform (https://ubiquity.filterlabs.ai).

These skills are developed and tested from a Hermes agent session and
mirrored here for review, versioning, and team collaboration.

## Skills

| Skill | Folder | Description |
|---|---|---|
| Ubiquity Auth | `skills/ubiquity-auth` | Handles login and OAuth token management against the shared Keycloak instance backing Ubiquity and its services. All other `ubiquity-*` skills depend on this one for a valid Bearer token. |
| Ubiquity Onboarding | `skills/ubiquity-onboarding` | Gives a brand-new user the end-to-end map of the Ubiquity workflow, from a plain-language data question to a running, analyzable feed. It's an index and narrative over the other skills rather than a replacement for their detailed mechanics. |
| Ubiquity Pipeline Creation | `skills/ubiquity-pipeline-creation` | Covers the "Discover" phase of building a pipeline: turning a free-text query into a saved pipeline via the "Ubi" discovery chat, tuning agent settings, and launching the discovery job that finds sources. Includes guidance on verifying the resolved location before confirming discovery. |
| Ubiquity Agent Settings | `skills/ubiquity-agent-settings` | Covers the "Agent Settings" dialog on a pipeline's Discover tab, which edits `agent_config` and `max_queries` metadata. Focuses on choosing good values and the direct API calls to read/write them, with no UI automation required. |
| Ubiquity Discovery Jobs | `skills/ubiquity-discovery-jobs` | Covers running, scaling, and cancelling Ubiquity discovery jobs, including the distinction between actions that merely save pipeline state versus the one action that actually launches a (costly) discovery job. Helps avoid accidentally triggering repeated backend job runs. |
| Ubiquity Entity Review | `skills/ubiquity-entity-review` | Covers reviewing candidate sources/entities that a discovery job finds for a pipeline, including listing, filtering, and voting (upvote/downvote) or removing them. Used once sources have landed in a feed's entity list for human review. |
| Ubiquity Understand Layer | `skills/ubiquity-understand-layer` | Covers the "Understand" tab of a pipeline: turning on Ubi's artifact analysis for a feed ("Enable Ubi") and configuring the data refresh interval. Documents that the enable toggle and refresh-interval dropdown are actually the same underlying setting. |
| Ubiquity Metric Generators | `skills/ubiquity-metric-generators` | Covers the "Metric Generators" section of a pipeline's Understand tab, for creating custom metrics derived from a feed's artifacts and viewing their output. Includes built-in presets like Sentiment, Entities, and Stance. |
| Ubiquity Data Feed API | `skills/ubiquity-data-feed-api` | Covers the raw "Curator Locations API" for pulling content items directly from a feed's vector store, bypassing the Understand-layer UI endpoints. Used whenever a task needs direct reasoning over full feed content (not just viewing UI panels), since it gives filterable access to the full corpus beyond the Understand layer's item cap. |
| Ubiquity Ubi Chat | `skills/ubiquity-ubi-chat` | Covers chatting with "Ubi", the standing per-feed assistant on the Understand tab that answers questions about a pipeline's feed artifacts. Distinct from the discovery-time Ubi chat bubble, which only parses the initial search query. |
| Ubiquity Pipeline Routing | `skills/ubiquity-pipeline-routing` | Covers "Pipeline Routes" and "Data Egress" on the Understand tab, for connecting pipelines to each other and routing feed data out to platforms. Includes guidance on when to split a large pipeline into several smaller ones connected via routes instead of overloading one pipeline's location list. |
| Ubiquity Skill Dev Workflow | `skills/ubiquity-skill-dev-workflow` | Governs how changes to any `ubiquity-*` skill get reviewed and pushed to this repo's GitHub mirror, requiring a leak scan and logical-soundness review before any commit. Exists because these skills are developed against a real production account and real pipeline/feed data, making accidental credential or UUID leaks an ongoing risk. |
