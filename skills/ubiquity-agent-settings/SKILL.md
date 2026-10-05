---
name: ubiquity-agent-settings
description: Use to tune Ubiquity Agent Settings for discovery pipelines.
---

# Ubiquity: recommending Agent Settings for a pipeline

Covers the "Agent Settings" dialog on a pipeline's Discover tab -- the panel
that edits `pipeline.metadata.agent_config` (and `discovery_config.max_queries`).
See `ubiquity-pipeline-creation` for how/when this gets PATCHed to the wire,
and `ubiquity-discovery-jobs` for the warning about not re-launching jobs
casually. This skill is about choosing GOOD values, not the save mechanics.

## Field reference (confirmed live, Oct 2026)

**Search Generation Agent** -> `agent_config.search_generation`:
- `max_queries` (slider 5-50, default 15): queries budget per discovery job.
- `creativity_level`: `low` | `medium` | `high`.
- `focus_types` (multi-toggle, all on by default): `news`, `government`,
  `blog`, `community`, `social`.
- `language_preference`: `native_first` | `mixed` | `english_first`.
- Custom Instructions: free-text extra requirements for query generation --
  CONFIRMED JSON key: `agent_config.search_generation.custom_instructions`
  (string). Seen live on a real pipeline:
  `"Prioritize individual resident voices and personal reactions: Reddit
  threads, local Facebook/Nextdoor community groups, personal social media
  posts (Instagram/TikTok/X), neighborhood forums, and community board
  discussions. Deprioritize and avoid corporate/commercial entities such as
  pest control companies, exterminator businesses, and other for-profit
  vendors -- focus on what everyday New Yorkers are personally saying, not
  businesses selling related services."`

**Evaluation Agent** -> `agent_config.evaluation`:
- `credibility_threshold` (0.0 lenient-1.0 strict, default 0.5): hard
  reject floor.
  **Known bias, important for recommendations**: credibility scoring
  tends to correlate with institutional scale/establishment status, not
  genuine trustworthiness -- a HIGH threshold systematically biases
  acceptance toward large media corporations and state-owned/state-funded
  outlets (both tend to score well on conventional credibility signals
  like domain authority, editorial staffing, publishing history), while a
  LOW threshold opens the door to opinion-driven social media and
  independent/individual voices that score lower on those same signals
  despite often being exactly what a sentiment- or grassroots-focused
  pipeline wants. Treat `credibility_threshold` as a
  establishment-vs-independent dial, not just a quality dial, when
  recommending it:
  - If the user wants independent/individual/grassroots voices (see Step
    9's "only individuals, no corporate" pattern) but ALSO sets a high
    `credibility_threshold`, the two settings fight each other -- the
    threshold will filter out exactly the independent sources the Custom
    Evaluation Criteria is trying to let in. Flag this conflict explicitly
    and recommend lowering `credibility_threshold` (e.g. to 0.3-0.4) to
    match the Step 9 intent, rather than leaving a high threshold that
    silently undermines it.
  - If the user wants to EXCLUDE state-owned media (Step 9), a high
    `credibility_threshold` alone will NOT achieve this -- state media
    typically scores well on credibility. The exclusion has to be done via
    Custom Evaluation Criteria (ownership-based), not by raising the
    threshold; raising the threshold in this case mostly just adds a
    second, unrelated large-corporate-media bias on top.
  - Conversely, if the user explicitly wants authoritative/official
    sources (e.g. the Government & policy profile), a high threshold is
    the right tool and the corporate/state-media bias is a feature, not a
    bug, for that use case -- the caution above applies when the user's
    stated intent is independence/grassroots/opinion diversity and the
    threshold is set in a way that works against it.
- `local_focus_priority`: `low` | `medium` | `high`.
- `quality_standards`: `lenient` | `moderate` | `strict`.
  **Known bias, same family as credibility_threshold above**:
  `moderate`/`strict` quality standards tend to pass through sources with
  established societal prestige -- outlets with editorial polish,
  institutional backing, professional production values -- and filter out
  the messier, more informal content where genuine general-public
  discussion actually happens (raw social posts, forum threads, personal
  blogs, comment sections). For pipelines whose goal IS general discussion/
  grassroots sentiment rather than authoritative reporting, `lenient` is
  usually the right choice, not a compromise -- `moderate`/`strict` will
  quietly skew the feed toward prestige institutions even if
  `credibility_threshold` is already lowered to let opinion-based social
  media through, since the two fields filter on overlapping-but-distinct
  signals (credibility leans on authority/track-record, quality_standards
  leans on production polish/editorial rigor) and either one alone can
  still bias the result toward prestige sources.
  - If recommending a low `credibility_threshold` for sentiment/social
    tracking (per the Social Media profile and the bias note above), pair
    it with `quality_standards: lenient` too -- raising one while lowering
    the other re-introduces the prestige bias through the other field.
  - For profiles that want authoritative/institutional sources (Government
    & policy, Economic/statistical data), `moderate`/`strict` is correct
    and the prestige bias is desirable there.
- `topic_relevance_weight` (0.0 not important-1.0 critical, default 0.5).
  **Known limitation -- this slider is blunt**: it scores relevance off
  what the evaluation agent actually SEES on a source/entity at review
  time (recent posts, page content), which penalizes entities whose
  overall persona is a strong match for the topic but whose observable
  recent output doesn't happen to mention it directly. This bites hardest
  for entities defined by a broad recurring theme (e.g. an account that
  talks politics often, a publication that covers a general beat) being
  evaluated against a narrow specific topic (e.g. one particular bill or
  issue) -- the entity is highly LIKELY to cover that specific topic
  eventually given their persona, but the slider only ever sees a
  snapshot and has no notion of topical adjacency or behavioral
  probability, only presence/absence in what it observed. Lowering the
  weight to compensate is itself blunt -- it loosens relevance scoring
  for EVERY source, not just the persona-match cases, diluting precision
  pipeline-wide to fix a narrower problem.
  - **Preferred fix: use Custom Evaluation Criteria (Step 9) instead of
    just lowering the slider.** Add explicit instructions telling the
    evaluation agent to count topical adjacency and behavioral likelihood,
    not just literal on-topic content observed, e.g.: `"Count sources as
    relevant if they frequently discuss closely related topics (e.g.
    broader policy/political coverage), even if this exact topic doesn't
    appear in their most recent content"` or `"An entity that posts
    about politics/policy regularly should be treated as likely to cover
    this specific issue even without direct recent evidence -- do not
    reject solely for topic absence in observed posts"`. This targets the
    actual persona-match cases without loosening relevance scoring for
    unrelated sources the way a global weight reduction would.
  - Reserve lowering `topic_relevance_weight` itself for when topic drift
    tolerance is wanted BROADLY across the whole pipeline (e.g. the
    General news monitoring profile's 0.5-0.6, which intentionally
    tolerates some drift pipeline-wide) -- not as a workaround for this
    specific persona-adjacency problem, which the Custom Evaluation
    Criteria instruction above addresses more precisely.
- Custom Evaluation Criteria (free text, evaluation hints).

**Datasets** -> `agent_config.datasets_discovery.enable_dataset_hunting`
(bool, off by default) -- searches FRED/World Bank/OECD/Eurostat/IMF-style
catalogs in parallel, auto-ingests confirmed datasets into Behavioral Data.

**Quick Presets** (confirmed live values -- bulk-set everything, still
individually editable after):

| Preset | max_queries | credibility | topic_relevance | local_focus | quality | focus_types | dataset_hunting |
|---|---|---|---|---|---|---|---|
| Balanced | 15 | 0.5 | 0.5 | medium | moderate | all 5 | off |
| Social Media Boost | 15 | 0.3 | 0.2 | high | lenient | all 5 | off |
| News Focus | 15 | 0.6 | 0.7 | medium | strict | news+government only | off |
| Behavioral Datasets Boost | 15 | 0.6 | 0.5 | medium | strict | all 5 | on |

Changes apply to FUTURE discovery jobs only, never retroactively (don't
re-launch a job just to "apply" a settings change unless the user wants a
fresh discovery run -- see `ubiquity-discovery-jobs` before clicking any
coverage button).

## Recommendation procedure
Always DERIVE the recommendation from the pipeline's own configuration --
never hand back a generic preset without reading what the pipeline is
actually for. Pull the pipeline object (`GET /api/locations/v1/pipelines/<id>`)
or read the Discover tab chips (LOCATIONS / TOPIC / TYPE) and extract:
- `locations`: list of location entities (count matters, see below)
- `topic`: free-text topic string(s)
- `entity_types`/TYPE chip: the source types the user originally asked for
  when creating the pipeline (news/social media/government/etc.) -- this is
  a stronger signal than any generic preset, since the user already told
  Ubi what kind of source they want.

### Step 1 -- pick a base profile from use case
Map the user's stated goal to one of these four base profiles (closest
preset is noted, but always re-derive fields rather than applying the
preset verbatim):

1. **General news monitoring** (broad, mixed sources)
   - Base: close to `Balanced`, but bias `focus_types` toward
     `news`+`blog`+`community` (drop `social` unless the pipeline's
     original TYPE chip asked for it).
   - `quality_standards: moderate`, `credibility_threshold: 0.5`,
     `topic_relevance_weight: 0.5-0.6` (broad monitoring tolerates some
     topic drift but shouldn't lose the thread entirely).
   - `local_focus_priority`: see Step 4 (depends on location granularity).
   - `creativity_level: medium`.

2. **Social media / sentiment tracking**
   - Base: `Social Media Boost`.
   - `focus_types`: `social` (+`community` if the pipeline also wants
     forums/comment-heavy sources). Drop `government`/pure `news` sites --
     they dilute a sentiment-focused feed.
   - `credibility_threshold: 0.2-0.3` (deliberately lenient -- real accounts
     posting real sentiment often look "low-authority" by news-credibility
     metrics; a strict threshold throws out exactly what you want).
   - `topic_relevance_weight: 0.2-0.3` (keep loose; sentiment signal often
     shows up in tangentially-related chatter, not just on-topic posts).
   - `local_focus_priority: high` if location is a specific city/region
     (local sentiment is the point); `medium` if location is a whole
     country/multi-country set.
   - `creativity_level: high` (social search benefits from more creative
     query phrasing -- hashtags, slang, colloquial terms).

3. **Government & policy / regulatory tracking**
   - Base: `News Focus`.
   - `focus_types`: `government`+`news` only -- actively exclude `blog`/
     `community`/`social` (noise-to-signal ratio is bad for regulatory
     tracking; a strict evaluation agent will spend budget rejecting them
     anyway).
   - `credibility_threshold: 0.6-0.7` (official/regulatory tracking needs
     authoritative sources).
   - `quality_standards: strict`.
   - `topic_relevance_weight: 0.7` (policy topics are often precise --
     e.g. a specific regulation name -- so drift is costly).
   - `local_focus_priority: medium-high` depending on whether the
     regulation is sub-national (city/state ordinance -> high) or
     national/supranational (country/EU-wide -> medium, since the
     authoritative source may legitimately sit in a capital far from
     the affected locality).
   - `creativity_level: low` (government/policy search benefits from
     literal, precise terminology, not creative rephrasing).

4. **Economic / statistical data (behavioral datasets)**
   - Base: `Behavioral Datasets Boost`.
   - `enable_dataset_hunting: true` -- this is the whole point of this
     profile; always turn it on.
   - `focus_types`: `government`+`news` (statistics offices and official
     releases are usually covered by these two; `social`/`blog` rarely
     surface primary data).
   - `credibility_threshold: 0.6`, `quality_standards: strict` (bad/stale
     data is worse than no data for this use case).
   - `topic_relevance_weight: 0.5` (keep moderate -- a dataset about a
     related indicator is often still useful even if not an exact topic
     match).
   - `creativity_level: medium`.

If the user names a use case not covered by these four, build the
recommendation by analogy: identify which of the four it's closest to in
intent (precision-vs-recall tradeoff, source-type mix, how costly topic
drift is) and start from that profile's reasoning rather than defaulting
to `Balanced` blindly.

### Step 2 -- reconcile with the pipeline's own original prompt/config
After picking a base profile, cross-check against what the user already
told Ubi when creating the pipeline (the TYPE/TOPIC/LOCATIONS chips, or
`search_filters.entities`):
- If the original query explicitly named source types (e.g. "news and
  social media about X"), that's a direct signal -- set `focus_types` to
  match the union of (use-case base profile's types) and (originally
  requested types), not just the preset default. Don't silently drop a
  type the user explicitly asked for even if the use-case profile doesn't
  usually include it.
- If the topic is narrow/specific (a named regulation, a named event),
  bump `topic_relevance_weight` up ~0.1-0.2 from the base profile value --
  narrow topics tolerate less drift. If the topic is broad/thematic ("AI
  regulation", "renewable energy"), the base profile value is fine as-is.

### Step 3 -- language preference (English-prevalence tiers)
Classify the pipeline's location(s) into one of four tiers and set
`language_preference` accordingly -- do this per-location-set, not
globally, and if a pipeline spans multiple locations in different tiers,
default to the LEAST-English-dominant tier represented (favors not missing
local-language sources over over-filtering English ones):

| Tier | Description | Examples | `language_preference` |
|---|---|---|---|
| A | English a small minority of written content | China, Russia, Japan, South Korea, most of Latin America, Middle East (non-Gulf), most of Francophone/Lusophone Africa | `native_first` |
| B | English present/elevated (business, education, tourism, often an official language) but native language still dominant everyday/media use | Germany, France, Italy, Scandinavia, Netherlands, India, Philippines, most non-Anglophone EU | `mixed` |
| C | English dominant overall, but a vocal/sizable linguistic minority produces real native-language content worth not missing | USA (Spanish), Canada (French/Quebec), Belgium (Dutch/French split), Wales (Welsh), Ireland (Irish-language minority) | `mixed` |
| D | English is effectively the only written language of public discourse | UK, Australia, New Zealand, Anglophone Canada regions, USA where no notable minority-language signal applies | `english_first` |

Rationale for collapsing B and C to the same `mixed` setting: both have
real non-English content worth surfacing, so `native_first` would
over-filter the (also real) English-language majority content in both
cases, while `english_first` would miss the minority-language content
in both. Only use `native_first` when English content genuinely would be
a small, likely-irrelevant minority of what's actually published, and
only use `english_first` when there's no meaningfully-sized non-English
audience to miss.

If unsure which tier a location falls into, err toward `mixed` -- it's the
safer default when evidence is ambiguous, and only step to `native_first`
or `english_first` when the tier classification is clear-cut.

### Step 4 -- max_queries from location count (10% rule)
From `ubiquity-pipeline-creation`'s existing guidance: location count
should stay under ~10% of `max_queries`, or each location gets
query-starved. Apply quantitatively:

```
n_locations = count of distinct location entities on the pipeline
recommended_max_queries = clamp(max(15, 10 * n_locations), 5, 50)
```

- `n_locations = 1` -> floor at the default 15 (no scaling needed for a
  single-location pipeline; use the base profile's implied query need --
  broad/exploratory topics can still go higher, e.g. 25-30, within the
  5-50 slider range, but 15 is a fine default).
- `n_locations = 3` -> `max(15, 30) = 30`.
- `n_locations = 5` -> `max(15, 50) = 50` (slider ceiling already hit).
- `n_locations > 5` -> formula wants >50, which the slider can't reach.
  **Flag to the user**: recommend splitting into multiple pipelines +
  Pipeline Routes (per `ubiquity-pipeline-creation`'s "when to split"
  section) rather than silently capping `max_queries` at 50 and accepting
  query-starved locations. Cap the recommended value at 50 but say
  explicitly that this is a compromise, not a fix.
- This max_queries recommendation is INDEPENDENT of the use-case base
  profile's other fields -- compute it from location count alone and
  report both numbers (e.g. "News Focus profile suggests default query
  volume, but your 4 locations push the floor to 40") when they'd
  otherwise disagree; the location-count floor should win since
  under-sized max_queries silently degrades every location's coverage
  without any visible error.

### Step 5 -- creativity_level from chip count (specificity rule)
`creativity_level` should be driven by how CONSTRAINED the pipeline's own
chips already are, not just the use-case profile -- a profile's suggested
value (Step 1) is a starting point this step then adjusts:

```
n_chips = count of LOCATIONS entries + count of TOPIC entries + count of entity_type/TYPE entries
```
(use `search_filters.entities` length from the pipeline object, or count
the chips shown on the Discover tab, as a proxy.)

- **Many chips already present** (several locations, multiple topics,
  and/or multiple entity types stacked on one pipeline) -> the query space
  is already heavily pre-constrained by the chips themselves; a creative
  query generator mostly wastes budget wandering into tangents the chips
  already ruled out. **Nudge creativity_level DOWN** (e.g. profile said
  `medium` -> use `low`; profile said `high` -> use `medium`).
- **Few chips present** (one location, one narrow topic, no extra entity-
  type constraint beyond a single TYPE) -> the query space is wide open;
  the discovery agent benefits from creative rephrasing to actually find
  the varied sources that exist under a loosely-specified search. **Nudge
  creativity_level UP** (e.g. profile said `low` -> use `medium`; profile
  said `medium` -> use `high`).
- No fixed numeric cutoff for "many" vs "few" -- treat 1-2 total chips as
  "few" (favor raising creativity) and 4+ total chips (e.g. the 19-location
  EU pipeline, or any pipeline with multiple topics AND multiple entity
  types layered on) as "many" (favor lowering creativity), with 3 as a
  judgment-call middle case to decide using the specific chips involved
  (e.g. 3 very narrow/specific chips still counts as constrained; 3 broad/
  vague chips may not).
- This is a NUDGE on top of the use-case profile's base value (Step 1),
  not a replacement for it -- report both the profile's starting value and
  the chip-count-adjusted final value when they differ, same pattern as
  the max_queries vs. location-count reconciliation in Step 4.

### Step 7 -- Search Generation Custom Instructions (free text)
The structured fields (max_queries, creativity_level, focus_types,
language_preference) can't express everything -- Custom Instructions is
where you hand the query-generation agent plain-language direction for
what the structured sliders/toggles can't capture. Use it for:

- **Adding topics/angles the TOPIC chip doesn't cover but are implied by
  the pipeline's purpose.** E.g. a "renewable energy" pipeline whose real
  goal is investment tracking benefits from `"Include queries about
  renewable energy financing, subsidies, and investment announcements"` --
  the chip stays broad/clean for display, the instruction adds the angle
  without needing a second TOPIC chip (which would also dilute
  topic_relevance_weight scoring against the main topic).
- **Linguistic nuance beyond language_preference's three-way choice.**
  `language_preference` only picks native/mixed/English; it can't say
  *which* native language variant, regional dialect, or specific
  terminology to use. E.g. for a Quebec-focused pipeline:
  `"Use Quebec French terminology (e.g. 'courriel' not 'email'), not
  France French"`; for a China pipeline: `"Include Simplified Chinese
  government/media terminology, not Traditional Chinese or Hong Kong
  phrasing"`. Also use this for synonym/jargon coverage within one
  language, e.g. `"Also search using the technical/legal term 'GDPR'
  alongside 'data protection regulation'"`.
- **Directing toward BROADER categories** when the TOPIC chip is narrower
  than what should actually be searched. E.g. TOPIC chip is a specific
  named bill, but the user wants surrounding context too:
  `"Also generate queries about the broader regulatory category this bill
  belongs to, not just the bill by name"`. Prefer this over just widening
  the TOPIC chip itself when the user still wants the narrow topic to
  drive evaluation/scoring (topic_relevance_weight) -- the instruction
  widens search recall without changing what counts as "relevant" at
  evaluation time.
- **Directing toward NARROWER categories** when the TOPIC chip is broader
  than the real target and creativity/broad focus_types are pulling in
  too much tangential volume. E.g. TOPIC chip is "renewable energy" but
  the user only cares about offshore wind: `"Focus specifically on
  offshore wind projects -- do not generate general renewable-energy or
  solar/onshore-wind queries"`. Prefer this over narrowing the TOPIC chip
  itself if the user may want to broaden back out later without re-doing
  the chip-based search parse.
- **Exclusions** -- things to actively avoid that focus_types/evaluation
  fields can't express at the query-generation stage: `"Avoid generating
  queries that would surface paywalled academic journals"` or `"Do not
  search for sources already in languages other than German or English"`.

**When to recommend it vs. leave blank**: don't fill it by default --
recommend Custom Instructions specifically when Steps 1-6's structured
fields can't fully express something the user told you about the
pipeline's intent (a sub-topic emphasis, a dialect/terminology need, a
broaden/narrow mismatch between the TOPIC chip and the real target). If
the structured fields already cover the pipeline's needs, say so and
leave Custom Instructions empty rather than padding it with restated
config. Keep instructions short, imperative, and specific (one or two
sentences) -- this feeds a query-generation prompt, not a brief.

### Step 9 -- Evaluation Agent Custom Evaluation Criteria (free text)
Where Search Generation Custom Instructions (Step 7) shapes what gets
SEARCHED FOR, Custom Evaluation Criteria shapes what gets ACCEPTED once
found -- it's the evaluation agent's own free-text field, applied on top
of credibility_threshold/quality_standards/topic_relevance_weight, for
ownership/provenance/entity-type filters those sliders can't express.
Use it for:

- **Ownership/provenance exclusions.** The structured fields score
  credibility and topic/local fit, but have no notion of WHO owns or
  funds a source. E.g. `"Exclude state-owned or state-funded media
  outlets"`, `"Exclude sources owned by [specific conglomerate/holding
  company]"`, `"Exclude sources with undisclosed funding from political
  parties or governments"`. Important for pipelines where editorial
  independence matters more than raw credibility score -- a state-owned
  outlet can score highly on credibility/quality while being exactly what
  the user wants filtered out.
- **Entity-type/corporate-structure filters.** `"Only accept sources
  published by individuals (independent journalists, personal blogs,
  individual social accounts) -- reject corporate-owned or institutional
  publications"`, or the inverse: `"Only accept sources from registered
  organizations or companies, reject personal blogs and anonymous
  accounts"`. This is a different axis than `focus_types` (news/blog/
  social/etc. is about FORMAT, this is about the publisher's legal/
  organizational nature) -- the two are independent and can combine, e.g.
  `focus_types: [blog, social]` + a Custom Evaluation Criteria excluding
  corporate accounts gets at "individual voices only, in blog/social
  format".
- **Independence/affiliation checks the credibility score alone misses.**
  `"Reject sources that are PR arms, press offices, or official
  communications channels of the entities they report on"` (e.g. a
  company's own newsroom reporting on itself) -- a self-published press
  release can be "high quality" and "on-topic" while still being exactly
  the kind of non-independent source a monitoring pipeline wants out.
- **Combine with, don't duplicate, the structured fields.** Don't restate
  `credibility_threshold`/`quality_standards` in prose (e.g. don't write
  "only accept high-quality sources" -- that's what `quality_standards:
  strict` already does); reserve this field for the ownership/entity-type/
  independence dimension the sliders can't reach.

**When to recommend it vs. leave blank**: same rule as Step 7 -- only
recommend when the user has stated (or the pipeline's purpose implies) an
ownership/entity-type/independence requirement the structured evaluation
fields can't express. If nothing like that applies, leave it empty rather
than padding it with a restated credibility/quality setting. Keep it
short, imperative, and specific -- one or two sentences, phrased as an
accept/reject rule the evaluation agent can apply per-source.

### Step 10 -- local_focus_priority from location granularity
As a general modifier on top of whatever the use-case base profile says
(apply as a nudge, not an override):
- Single city/sub-national location -> nudge toward `high`.
- Single country -> base profile's default value is usually fine as-is.
- Multi-country / continent-scale / supranational -> nudge toward
  `medium` even if the base profile said `high` -- "local" is diffuse
  across many locations, and an overly strict local-focus setting will
  reject sources that are legitimately national/regional-level for one
  of the many target locations.

## Output format for a recommendation
When asked to recommend settings for a specific pipeline, report:
1. The derived use-case profile(s) applied (can be a blend if the user
   gave more than one use case for the same pipeline).
2. Every field's recommended value WITH a one-line reason tied to this
   specific pipeline's location/topic/original-prompt -- not just "because
   the preset says so".
3. The computed `max_queries` from Step 4, flagged separately if it
   required a split-pipeline recommendation.
4. The language_preference tier classification and why.
5. The chip-count-adjusted `creativity_level` from Step 5, noting the
   profile's starting value if the chip-count nudge changed it.
6. Any recommended Search Generation Custom Instructions text (Step 7),
   or an explicit note that none is needed and why.
7. Any recommended Evaluation Agent Custom Evaluation Criteria text
   (Step 9), or an explicit note that none is needed and why.
8. Explicitly note this only edits `agent_config` -- confirm with the user
   before clicking "Save Settings" if driving the UI, and never click
   any coverage-level/"Discover Sources" button as a side effect of saving
   settings (saving settings and launching a job are separate actions --
   see `ubiquity-discovery-jobs`).
