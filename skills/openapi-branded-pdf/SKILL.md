---
name: "openapi-branded-pdf"
description: "Use when documenting openapi.json. Builds branded PDFs."
---

# OpenAPI -> branded API PDFs

Produces two PDFs from an OpenAPI 3.x spec:
- **Overview**: cover, intro, stats, servers, auth, core workflow, numbered endpoint tables per resource area (about 6 pages for 56 operations).
- **Detailed Reference**: everything above plus, for every endpoint, parameters, request body fields, example payload and response structures (about 30-41 pages for 56 operations).

The look is black/navy and red (taken from the logo), light grey code panels, numbered red-ruled section headings that are visibly stronger than the smaller endpoint headings, a running header that names the current section, and syntax-highlighted JSON/form examples. Every text/background colour pair is asserted at import to be at least 4.5:1 (WCAG AA).

**CONFIRMED working end-to-end** (tested live against `ubiquity-onboarding/references/openapi.json`, 46 paths / 56 operations): both PDFs build cleanly, no leaked internal wording survives (verified via `pdftotext` grep for `CONFIRMED`/`skill`/`XHR`/`browser`/`UI`/`Angular`/`ubiquity-*`), no orphaned `Responses`/`Parameters` labels at page bottoms, and rendered pages are non-blank. **Requires Python 3.10+** -- the pinned `reportlab` release refuses to import under 3.9. If the default `python3` on the machine is 3.9 (common on macOS), create a venv with a newer interpreter (e.g. `/opt/homebrew/bin/python3.12 -m venv venv && ./venv/bin/pip install reportlab`) and run the builder through that venv's `python`, not the system one.

## Inputs
1. `openapi.json` (the spec).
2. A logo PNG. If none is attached, ask the user to attach it. The sandbox usually has no network, so do not try to download one. Without a logo the builder falls back to a text wordmark and says so.
3. `content.json`, the per-product prose (see schema below). On a **regenerate with a new spec**, reuse the previous content.json and only add entries for new endpoints. Warnings from the builder list exactly what is missing.

## Workflow
1. Create a working dir. Copy this skill's `scripts/fl_theme.py` and `scripts/build_api_pdf.py` into it. Ensure a Python 3.10+ interpreter with `reportlab` installed is available (see venv note above).
2. Read the spec: list paths, methods, tags, servers, `info.version`. Identify resource areas and the main workflow.
3. Write or update `content.json` (first run: draft all of it by reading the spec; later runs: diff operations against existing `endpoints` keys and fill only gaps). Even a minimal `content.json` (just `meta`/`overview`) works -- every undocumented field falls back to `"Not documented yet."` and the builder prints a `WARNING:` line for it rather than failing.
4. Build both PDFs:
   `<venv>/bin/python build_api_pdf.py --spec openapi.json --content content.json --mode overview --logo logo.png --out Overview.pdf`
   `<venv>/bin/python build_api_pdf.py --spec openapi.json --content content.json --mode detailed --logo logo.png --out Detailed.pdf`
   Add `--strict` to fail on any fallback text. Read every `WARNING:` line and fix content.json until none remain (or tell the user which items are undocumented).
5. QA (do not skip):
   - `pdfinfo` page counts; `pdftoppm -r 60 -png` then look at the cover, one overview page, one detailed page with a request body, and the last page.
   - `pdftotext -layout` and grep for orphaned labels (a `Responses`/`Parameters` label as the last line of a page) and for leaked internal wording (`CONFIRMED`, `skill`, `XHR`, `browser`, `UI`, internal service names).
   - If the cover callout or stat boxes look unequal, render at 150 dpi and measure the gap above and below the text with PIL; tune `STAT_PAD`/`CALL_PAD` in fl_theme.py until equal.
6. Deliver both PDFs to the user with a one-line description each. Do not recap the steps.

## Wording rules (important)
- Anything the spec does not document is written as **"not documented yet"** (e.g. `Response shape: not documented yet.`). Never guess or invent fields.
- Reverse-engineered or agent-oriented specs often hold internal notes (confirmation status, tool/skill names, UI/browser/XHR remarks, bug notes, caveats). Never print them. Replace them with a short customer-facing description in content.json. The builder replaces matching spec text with `Not documented yet.` and warns.
- No "unofficial spec" disclaimers, no "Notes & caveats" section, no mention of server-side bugs, unless the user asks.
- Descriptions are one or two plain sentences. Use `backticks` for code and `**bold**` sparingly.

## content.json schema
```json
{
  "meta": {"company": "FilterLabs", "product": "Ubiquity API", "site": "filterlabs.ai"},
  "overview": {
    "intro": "2-4 sentences on what the API does.",
    "stats_extra": [["3", "service families"]],
    "servers": {"https://api.example.com": "What this base URL is for"},
    "authentication": "How tokens are obtained, sent and refreshed.",
    "families": [["/v1/…", "Service name", "What it handles"]],
    "conventions": [{"overview": true, "text": "Cross-cutting rule"}, {"overview": false, "text": "Detail only for the long PDF"}],
    "status_codes": [["200", "Meaning in this API"]]
  },
  "workflow": {
    "title": "Core workflow", "lead": "One paragraph.",
    "steps": [["1", "POST", "/path", "What it does", "Returns", "Used by"]],
    "sections": [{"overview": true, "heading": "Polling", "text": "…"}]
  },
  "reference_note": "Optional sentence under the endpoint-reference heading (detailed only).",
  "groups": [
    {"name": "Pipelines", "blurb": "One line.",
     "match": [{"prefix": "/v1/pipelines", "exclude": ["/runs"]}, {"exact": "/v1/x"}, {"contains": "/pipelines/"}]}
  ],
  "param_notes": {"limit": "Page size, 1 to 100."},
  "endpoints": {
    "GET /v1/pipelines/{id}": {
      "desc": "One-sentence description.",
      "notes": ["Optional extra paragraph(s) shown under the heading."],
      "fields": {"name": "Override text for a parameter or body field (dotted path like data.id)."},
      "responses": {"200": {"text": "What it returns.", "shape": "{\n  \"id\": \"<uuid>\"\n}"},
                    "404": {"text": "Not found."}},
      "example": "Optional literal request example (overrides the generated one).",
      "example_drop": ["fields to omit from the generated example"]
    }
  }
}
```
Notes: group `match` rules are tried in order of groups; an endpoint goes to the first group that matches. Unmatched endpoints go to an `Other` group with a warning. If `groups` is omitted, the builder groups by first tag. Response `shape` blocks use JSON-like text; `<placeholder>` and `...` are highlighted. Endpoint keys are `METHOD /path` exactly as in the spec (method uppercase).

## Customising the brand
Palette lives in `HEX`, `METHOD`, `CODE` at the top of fl_theme.py. If you change a colour, the import-time check will raise on any pair under 4.5:1: adjust until it passes (e.g. PUT amber had to be darkened to `#9A6412`). Keep backgrounds light and low-contrast (`band #F4F4F5`, `codebg #F6F6F7`) with dark text; header fill is `#5B6B80` with white text.

## Using this for the Ubiquity onboarding spec specifically
The spec at `ubiquity-onboarding/references/openapi.json` is reverse-engineered and full of internal recon notes (`CONFIRMED`, `see ubiquity-*`, XHR/browser/Angular remarks) -- exactly the class of content the `BAD` regex in `build_api_pdf.py` is designed to strip. Always build from a copy of that file (never edit it to "clean it up" for the PDF -- the internal notes are load-bearing for other ubiquity-* skills) and let the builder's `clean()` pass do the redaction automatically; just verify the WARNING list and QA pass per Step 5 above before delivering.
