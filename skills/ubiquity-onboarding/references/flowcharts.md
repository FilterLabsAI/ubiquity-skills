# Ubiquity workflow -- Mermaid flowcharts

These render in any Mermaid-compatible viewer (GitHub, Obsidian, Mermaid Live Editor, etc).

## 1. End-to-end overview

```mermaid
flowchart TD
    A["User asks a data question\n(plain language)"] --> B["Discover chat parses it\ninto LOCATION / TOPIC / entity-type chips"]
    B --> C{"Resolved location\ncorrect?"}
    C -- "No (EU/UN/NATO etc.\nmis-geocoded)" --> B2["'No, Revise Query' ->\n'Change Location'"]
    B2 --> B
    C -- Yes --> D["Confirm: 'Yes, Discover Sources'"]
    D --> E["Pipeline + feed created\n(POST /pipelines, jobs/create)"]
    E --> F["Tune Agent Settings\n(optional, recommended)"]
    F --> G["Discovery job runs\n(15-20+ min, async)"]
    G --> H["Review discovered entities\nlike / dislike / flag / remove"]
    H --> I{"Happy with\ncoverage?"}
    I -- "No, scale up" --> J["Increase Coverage\n(Low/Medium/High/X-High)"]
    J --> G
    I -- Yes --> K["Enable Understand layer\n+ set refresh interval"]
    K --> L["Artifacts ingested\n(articles/posts/content)"]
    L --> M["Add custom metrics\n(Sentiment, Stance, Entities, custom)"]
    M --> N{"How to analyze?"}
    N --> O["Ubi chat\n(grounded Q&A, citations, charts)"]
    N --> P["Data Browser\n(chart + artifact table, UI)"]
    N --> Q["Direct API\n(/feeds/{id}/stream, full corpus)"]
    O & P & Q --> R["Insight / decision"]
    R -. "need more coverage\nor new angle" .-> F
```

## 2. Pipeline creation detail (Discover chat)

```mermaid
flowchart TD
    A["Free-text query typed into\nDiscover search box"] --> B["POST /api/orchestrator/search/unified\n(parses entities, returns session_id)"]
    B --> C["Ubi confirmation turn:\n'Would you like to discover\nsources for this query?'"]
    C -->|"Yes, Discover Sources"| D["POST /api/locations/v1/pipelines\nPOST /api/orchestrator/.../jobs/create"]
    C -->|"No, Revise Query"| E["Change Location /\nAdjust Topics /\nNarrow Entity Types /\n'Add &lt;place&gt;'"]
    E --> B2["SAME /search/unified call,\n+ prior_query / prior_entities /\nprior_context / session_id\n(NO separate chat-message endpoint)"]
    B2 --> C
    C -->|"Import Sources"| F{"Which sub-flow?"}
    F -->|"Plain Text\n(textarea, 1 URL/line)"| F1["POST .../sources/upload\n{urls: [...]}"]
    F -->|"CSV Upload\n(client-parses CSV first)"| F2["POST .../sources/upload\n{urls_with_metadata: [{url,name?}]}"]
    F -->|"Behavioral Dataset\n(jsonl/csv/xlsx, title+tags)"| F3["POST /orchestrator/workflows/\ndataset-upload/trigger (multipart)\n-> poll .../status"]
    F1 & F2 --> F4["202, async job_id\n(url_count/valid/invalid)"]
    F3 --> F5["pending -> running -> completed\ndataset_id + series_names"]
    D --> G["Pipeline object:\nfeed_id + pipeline_id"]
    F4 & F5 --> G
```

## 3. Discovery job + entity review loop

```mermaid
flowchart TD
    A["Discovery job: pending -> running"] --> B["Candidate sources land\nin feed entity list"]
    B --> C["Human reviews entities:\nread AI evaluation_notes per source"]
    C --> D{"Action"}
    D -->|like| E["POST entity-votes/toggle\nvote_type=like"]
    D -->|dislike| F["vote_type=dislike"]
    D -->|flag| G["vote_type=flag"]
    D -->|remove| H["DELETE .../entities/{id}\n(hard delete)"]
    D -->|"split (multi-URL\nentities only)"| S1["GET .../entities/{id}/split-preview\n(AI-clusters source URLs by topic)"]
    S1 --> S2["groups[], one flagged is_keeper\n(NOT always the semantic match)"]
    S2 --> S3["POST .../entities/{id}/split\nDESTRUCTIVE, cross-feed"]
    S3 --> S4["original id keeps is_keeper group;\neach other group -> new entity,\nlinked to every affected feed"]
    E & F & G & H & S4 --> I["vote_context (liked/disliked\nentities by name+type)\nstored on the pipeline"]
    I --> J{"Launch another\ndiscovery job?"}
    J -->|"Increase Coverage"| K["POST jobs/create\nincludes vote_context as\npositive/negative examples"]
    K --> A
    J -->|"Done reviewing"| L["Proceed to Understand layer"]
```

## 4. Understand layer + analysis fan-out

```mermaid
flowchart TD
    A["Enable Ubi / set refresh interval\n(PUT /feeds/{id})"] --> B["Artifacts ingested\n(content scanned from sources)"]
    B --> C["Create metric generators\n(Sentiment / Stance / Entities / custom)\nPOST /feeds/{id}/metric_prompts"]
    C --> D["Metrics scored per artifact\n(async, lags ingestion)"]
    D --> E1["Ubi Chat\nsessions/messages,\ncites real artifacts,\nmetric-aware answers"]
    D --> E2["Data Browser\nmetrics/preview (chart)\nartifacts/preview (table)"]
    D --> E3["Direct Data Feed API\n/feeds/{id}/stream\n(full corpus, for Hermes-side\nreasoning/summarization)"]
    E1 & E2 & E3 --> F["User gets an answer\n/ makes a decision"]
```

## 5. Multi-pipeline routing (large/geographically broad queries)

```mermaid
flowchart LR
    subgraph "Western Europe pipeline"
      A1["feed A"]
    end
    subgraph "Eastern Europe pipeline"
      A2["feed B"]
    end
    subgraph "Nordics pipeline"
      A3["feed C"]
    end
    A1 -->|"Pipeline Route\n(filter_mode defaults 'all';\nnon-default values accepted\n+ persisted but EFFECT\nUNVERIFIED, see openapi.json)"| D["Aggregating\ndestination pipeline"]
    A2 -->|"Pipeline Route"| D
    A3 -->|"Pipeline Route"| D
    D --> E["Unified Understand layer\nview across all regions"]
```
