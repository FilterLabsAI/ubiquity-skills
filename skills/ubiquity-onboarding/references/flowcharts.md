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
    A["Free-text query typed into\nDiscover search box"] --> B["POST /api/orchestrator/search/unified\n(parses entities)"]
    B --> C["Ubi confirmation turn:\n'Would you like to discover\nsources for this query?'"]
    C -->|"Yes, Discover Sources"| D["POST /api/locations/v1/pipelines\nPOST /api/orchestrator/.../jobs/create"]
    C -->|"No, Revise Query"| E["Change Location /\nAdjust Topics /\nNarrow Entity Types"]
    E --> B
    C -->|"Import Sources"| F["Manual URL / CSV /\nBehavioral Dataset upload\n(skips automated discovery)"]
    D --> G["Pipeline object:\nfeed_id + pipeline_id"]
    F --> G
```

## 3. Discovery job + entity review loop

```mermaid
flowchart TD
    A["Discovery job: pending -> running"] --> B["Candidate sources land\nin feed entity list"]
    B --> C["Human reviews entities:\nread AI evaluation_notes per source"]
    C --> D{"Vote"}
    D -->|like| E["POST entity-votes/toggle\nvote_type=like"]
    D -->|dislike| F["vote_type=dislike"]
    D -->|flag| G["vote_type=flag"]
    D -->|remove| H["DELETE .../entities/{id}"]
    E & F & G & H --> I["vote_context (liked/disliked\nentities by name+type)\nstored on the pipeline"]
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
    A1 -->|"Pipeline Route"| D["Aggregating\ndestination pipeline"]
    A2 -->|"Pipeline Route"| D
    A3 -->|"Pipeline Route"| D
    D --> E["Unified Understand layer\nview across all regions"]
```
