#!/usr/bin/env python3
"""
Ubiquity entity review helper.

Fetches a feed's discovered entities + current votes, renders a flat table,
applies votes, and (given a completed review) suggests Agent
Settings / discovery_config changes based on vote patterns.

Auth: reads access_token from ~/.hermes/secrets/filterlabs_tokens.json
(see filterlabs_auth.py / ubiquity-auth skill). Refresh it first if stale:
    python3 filterlabs_auth.py --status
    python3 filterlabs_auth.py        # refreshes if needed

Usage:
    python3 entity_review.py list --feed-id 1663 --pipeline-id 2fed2023-...
    python3 entity_review.py page --feed-id 1663 --pipeline-id 2fed2023-... --page 0 --page-size 5
    python3 entity_review.py vote --pipeline-id 2fed2023-... --entity-id 26628 --vote-type dislike
    python3 entity_review.py remove --feed-id 1663 --entity-id 26628
    python3 entity_review.py suggest --feed-id 1663 --pipeline-id 2fed2023-...

`list` and `page` both support --sort-by {credibility,name,id}, --reverse
(highest-first instead of lowest-first), and --only-unvoted (hide anything
already liked/disliked/flagged, to focus a review pass on fresh entities).
`page` additionally shows each entity's AI notes (a plain-language render
of the discovery agent's structured credibility/quality/local_focus/type
assessment -- there is no free-text "reasoning" field in the API, this is
the closest equivalent) and its full list of source URLs.
"""
import argparse
import base64
import json
import sys
import textwrap
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib import request, error, parse

BASE_URL = "https://ubiquity.filterlabs.ai"
TOKENS_PATH = Path.home() / ".hermes/secrets/filterlabs_tokens.json"
# Session cache (frozen entity order for a review pass) -- not a secret,
# just scratch state, kept near the tokens dir purely for convenience.
SESSION_DIR = Path.home() / ".hermes/cache/entity_review_sessions"


def _load_token():
    data = json.loads(TOKENS_PATH.read_text())
    return data["access_token"]


def _user_uuid(token):
    payload_b64 = token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded))
    return payload["sub"]


def _call(method, path, token, body=None):
    url = BASE_URL + path
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    # The API's edge/WAF (observed error code 1010) rejects requests without
    # a browser-like User-Agent -- always set one or you'll get a 403.
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    )
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode(errors="replace")


def fetch_entities(token, feed_id, limit=500):
    status, data = _call(
        "GET",
        f"/api/locations/api/v1/feeds/{feed_id}/entities"
        f"?limit={limit}&offset=0&q=&order_by=vote&order=asc&type=all",
        token,
    )
    if status != 200:
        raise RuntimeError(f"entities fetch failed: {status} {data}")
    return data["entities"], data.get("total"), data.get("source_count"), data.get("dataset_count")


def fetch_votes(token, pipeline_id, limit=1000):
    status, data = _call(
        "GET", f"/api/locations/v1/entity-votes/pipeline/{pipeline_id}?limit={limit}", token
    )
    if status != 200:
        raise RuntimeError(f"votes fetch failed: {status} {data}")
    return data  # list of vote objects


def fetch_evaluation_log(token, url):
    """Fetch the discovery agent's full narrative evaluation for one source
    URL. CONFIRMED endpoint:
        GET /api/locations/api/v1/source-evaluation-logs/by-url?url=<url>
    Returns the free-text `evaluation_details.evaluation_notes` the agent
    wrote when it evaluated this source (strengths/limitations/recommended
    use), plus matching_location and dataset_confidence/format/provider
    fields. Returns None if no log exists for this exact URL (e.g. the
    entity's `url` field is empty, or the source was added by some other
    path that didn't go through evaluation)."""
    if not url:
        return None
    status, data = _call(
        "GET",
        "/api/locations/api/v1/source-evaluation-logs/by-url?url=" + parse.quote(url, safe=""),
        token,
    )
    if status != 200 or not data:
        return None
    return data


def _split_notes_sections(notes):
    """Split the agent's evaluation_notes into labelled sections if it
    follows the observed STRENGTHS:/LIMITATIONS:/RECOMMENDED USE: pattern.
    Returns a dict {lede, strengths, limitations, recommended_use,
    other} with any section not found left as None. `lede` is the opening
    sentence (why it's valid/invalid), `other` catches trailing text like
    a SUPPLEMENT WITH / ACKNOWLEDGE clause that doesn't fit a known label."""
    import re

    if not notes:
        return {}
    labels = ["STRENGTHS", "LIMITATIONS", "RECOMMENDED USE", "SUPPLEMENT WITH", "ACKNOWLEDGE"]
    pattern = r"(" + "|".join(labels) + r"):\s*"
    pieces = re.split(pattern, notes)
    # pieces[0] is the lede before any label; then alternating label, text
    lede = pieces[0].strip()
    sections = {"lede": lede}
    key_map = {
        "STRENGTHS": "strengths",
        "LIMITATIONS": "limitations",
        "RECOMMENDED USE": "recommended_use",
        "SUPPLEMENT WITH": "supplement_with",
        "ACKNOWLEDGE": "acknowledge",
    }
    i = 1
    while i < len(pieces) - 1:
        label = pieces[i]
        text = pieces[i + 1].strip().rstrip(".")
        sections[key_map.get(label, label.lower())] = text
        i += 2
    return sections


def _session_path(feed_id, pipeline_id):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return SESSION_DIR / f"{feed_id}_{pipeline_id}.json"


def start_session(feed_id, pipeline_id, sort_by="credibility", reverse=False, only_unvoted=False):
    """Snapshot the current entity order (and an empty staged-votes queue)
    into a session file, so that:
    (a) voting mid-review does NOT shift what 'page N' means later, and
    (b) votes aren't pushed to the API one at a time while reviewing --
        they're queued here and pushed together via `apply` once the whole
        pass is done, matching a natural "review everything, then commit"
        workflow instead of mutating live state page by page.
    Call this ONCE at the start of a review pass."""
    token = _load_token()
    entities, total, source_count, dataset_count = fetch_entities(token, feed_id)
    votes = fetch_votes(token, pipeline_id)
    rows = build_review_table(entities, votes)
    if only_unvoted:
        rows = [r for r in rows if not r["votes"]]
    rows = sort_rows(rows, sort_by=sort_by, reverse=reverse)
    ids = [r["id"] for r in rows]
    path = _session_path(feed_id, pipeline_id)
    path.write_text(json.dumps({
        "feed_id": feed_id, "pipeline_id": pipeline_id, "ids": ids,
        "queued_votes": {}, "queued_removals": [],
    }))
    return ids, path


def load_session(feed_id, pipeline_id):
    path = _session_path(feed_id, pipeline_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_session(feed_id, pipeline_id, data):
    _session_path(feed_id, pipeline_id).write_text(json.dumps(data))


def queue_vote(feed_id, pipeline_id, entity_id, vote_type):
    """Stage a vote decision in the session file WITHOUT calling the API
    yet. `vote_type=None` clears any queued vote for that entity (undo a
    staged decision before applying)."""
    data = load_session(feed_id, pipeline_id)
    if not data:
        raise RuntimeError("No session found -- run `start` first.")
    key = str(entity_id)
    if vote_type is None:
        data["queued_votes"].pop(key, None)
    else:
        data["queued_votes"][key] = vote_type
    save_session(feed_id, pipeline_id, data)
    return data["queued_votes"]


def queue_removal(feed_id, pipeline_id, entity_id, remove=True):
    data = load_session(feed_id, pipeline_id)
    if not data:
        raise RuntimeError("No session found -- run `start` first.")
    s = set(data.get("queued_removals", []))
    if remove:
        s.add(entity_id)
    else:
        s.discard(entity_id)
    data["queued_removals"] = sorted(s)
    save_session(feed_id, pipeline_id, data)
    return data["queued_removals"]


def apply_session(feed_id, pipeline_id):
    """Push every queued vote + removal to the live API in one pass, then
    report results per entity. Successfully-applied queued votes/removals
    are REMOVED from the queue afterward (the frozen entity order itself
    is untouched) so a later `apply` call never re-sends an action that
    already landed -- re-sending a vote:toggle is NOT a no-op, it flips
    the vote back off. Failed actions (e.g. an expired token) are left
    queued so you can fix the problem and retry."""
    token = _load_token()
    data = load_session(feed_id, pipeline_id)
    if not data:
        raise RuntimeError("No session found -- run `start` first.")
    results = []
    remaining_votes = {}
    for entity_id_str, vote_type in data.get("queued_votes", {}).items():
        status, resp = vote(token, pipeline_id, int(entity_id_str), vote_type)
        ok = status in (200, 201)
        results.append({"entity_id": int(entity_id_str), "action": f"vote:{vote_type}",
                         "status": status, "ok": ok})
        if not ok:
            remaining_votes[entity_id_str] = vote_type
    remaining_removals = []
    for entity_id in data.get("queued_removals", []):
        status, resp = remove_entity(token, feed_id, entity_id)
        ok = status == 200
        results.append({"entity_id": entity_id, "action": "remove",
                         "status": status, "ok": ok})
        if not ok:
            remaining_removals.append(entity_id)
    data["queued_votes"] = remaining_votes
    data["queued_removals"] = remaining_removals
    save_session(feed_id, pipeline_id, data)
    return results


def _ai_notes(meta):
    """Render the discovery agent's structured per-entity assessment as a
    short plain-language note. There is NO free-text "reasoning" field in
    the API -- the agent's judgment is captured only as these four
    structured fields (credibility_score, quality, local_focus, type).
    This renders them as one readable sentence, which is the closest thing
    to an "AI reasoning" note the data actually supports."""
    cred = meta.get("credibility_score")
    quality = meta.get("quality")
    local_focus = meta.get("local_focus")
    etype = meta.get("type")
    parts = []
    if cred is not None:
        parts.append(f"credibility {cred:.2f}")
    if quality:
        parts.append(f"quality={quality}")
    if local_focus:
        parts.append(f"local focus={local_focus}")
    if etype:
        parts.append(f"type={etype}")
    desc = meta.get("description")
    note = "; ".join(parts) if parts else "no assessment recorded"
    if desc:
        note += f" -- {desc}"
    return note


def build_review_table(entities, votes, token=None, fetch_notes=False, max_workers=8):
    """Merge entities + votes into one row per entity.

    Returns a list of dicts: id, name, type, credibility, language,
    local_focus, quality, source_count, votes (list of vote_type strings
    currently active for THIS entity), ai_notes (plain-language rendering
    of the discovery agent's structured assessment), urls (list of source
    URLs for this entity), eval (parsed sections of the free-text
    evaluation_notes from source-evaluation-logs, or None).

    Pass fetch_notes=True + a token to also fetch each row's full
    evaluation log (parallelized -- do this AFTER narrowing to one page's
    worth of rows, not for an entire 178-entity feed, to keep it fast).
    """
    votes_by_entity = {}
    for v in votes:
        votes_by_entity.setdefault(v["entity_id"], []).append(v["vote_type"])

    rows = []
    for e in entities:
        meta = e.get("metadata") or {}
        rows.append(
            {
                "id": e["id"],
                "name": e["name"],
                "type": meta.get("type"),
                "credibility": meta.get("credibility_score"),
                "language": meta.get("language"),
                "local_focus": meta.get("local_focus"),
                "quality": meta.get("quality"),
                "url": meta.get("url"),
                "source_count": e.get("source_count"),
                "urls": [s.get("url_to_scan") for s in (e.get("sources") or [])],
                "votes": sorted(votes_by_entity.get(e["id"], [])),
                "ai_notes": _ai_notes(meta),
                "eval": None,
            }
        )

    if fetch_notes and token:
        def _fill(row):
            log = fetch_evaluation_log(token, row["url"])
            if log:
                notes = (log.get("evaluation_details") or {}).get("evaluation_notes")
                row["eval"] = _split_notes_sections(notes)
                row["eval_matching_location"] = (log.get("evaluation_details") or {}).get("matching_location")
            return row

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            rows = list(pool.map(_fill, rows))

    return rows


def sort_rows(rows, sort_by="credibility", reverse=False):
    key_fns = {
        "credibility": lambda r: r["credibility"] if r["credibility"] is not None else -1,
        "name": lambda r: (r["name"] or "").lower(),
        "id": lambda r: r["id"],
    }
    key_fn = key_fns.get(sort_by, key_fns["credibility"])
    return sorted(rows, key=key_fn, reverse=reverse)


def print_table(rows):
    print(f"{'ID':<8} {'VOTES':<14} {'CRED':<5} {'TYPE':<12} {'LANG':<5} {'NAME'}")
    for r in rows:
        votes = ",".join(r["votes"]) or "-"
        cred = f"{r['credibility']:.2f}" if isinstance(r["credibility"], (int, float)) else "-"
        print(f"{r['id']:<8} {votes:<14} {cred:<5} {str(r['type']):<12} {str(r['language']):<5} {r['name']}")


def _wrap(text, width=88, indent="      "):
    if not text:
        return ""
    return textwrap.fill(text, width=width, initial_indent=indent, subsequent_indent=indent)


def _vote_status(r):
    votes = "/".join(v.upper() for v in r["votes"]) or "unvoted"
    if r.get("queued"):
        votes += " (queued)"
    return votes


def print_page_table(rows, page, page_size, total_rows, col_width=50):
    """Render one page of entities as a STANDARD markdown table (one `|
    a | b | c |` row per entity, single physical line each). Hermes's TUI
    renderer (agent/markdown_tables.py, ui-tui/.../markdown.tsx) does its
    own column-width measurement and per-cell word-wrapping at render
    time, and falls back to a vertical key:value layout automatically if
    a row is too tall/wide for the terminal -- it does NOT interpret
    manual box-drawing or '<br>' as a line break (both show up as literal
    text, which is why earlier attempts at this looked broken). So: emit
    plain cells, let the renderer wrap them. Pipe characters inside a
    cell's text are escaped as '\\|' per CommonMark table syntax so they
    don't get mistaken for a column boundary. `col_width` is unused here
    (kept for call-signature compatibility) -- wrapping is the renderer's
    job now, not this function's."""
    start = page * page_size
    end = min(start + page_size, len(rows))
    total_pages = max(1, (len(rows) + page_size - 1) // page_size)
    print(f"━━━ Page {page + 1}/{total_pages} · entities {start + 1}-{end} of {len(rows)} filtered "
          f"({total_rows} total in feed) ━━━\n")

    def esc(text):
        return str(text).replace("|", "\\|").replace("\n", " ")

    print("| ID | Name | Source URLs | Type | Notes | Vote status |")
    print("|---|---|---|---|---|---|")
    for r in rows[start:end]:
        urls = r["urls"] or ([r["url"]] if r["url"] else [])
        urls_text = ", ".join(urls) if urls else "-"

        ev = r.get("eval") or {}
        if ev.get("lede") or ev.get("strengths") or ev.get("limitations") or ev.get("recommended_use"):
            parts = []
            if ev.get("lede"):
                parts.append(ev["lede"])
            if ev.get("strengths"):
                parts.append(f"STRENGTHS: {ev['strengths']}.")
            if ev.get("limitations"):
                parts.append(f"CONCERNS: {ev['limitations']}.")
            if ev.get("recommended_use"):
                parts.append(f"USE AS: {ev['recommended_use']}.")
            notes_text = " ".join(parts)
        else:
            notes_text = r.get("ai_notes") or "-"

        print(f"| {r['id']} | {esc(r['name'])} | {esc(urls_text)} | {esc(r['type'] or '?')} | "
              f"{esc(notes_text)} | {esc(_vote_status(r))} |")
    print()
    if end < len(rows):
        print(f"-- {len(rows) - end} more entities. Next: --page {page + 1} --page-size {page_size}")


def print_page(rows, page, page_size, total_rows):
    """Render one page of entities as compact, scannable cards: a one-line
    header (id/name/credibility/vote), then a short VERDICT line, then
    STRENGTHS/CONCERNS pulled from the evaluation log's free-text notes
    (when available), then source links. Falls back to the structured
    ai_notes summary when no evaluation log exists for a row's URL."""
    start = page * page_size
    end = min(start + page_size, len(rows))
    total_pages = max(1, (len(rows) + page_size - 1) // page_size)
    print(f"━━━ Page {page + 1}/{total_pages} · entities {start + 1}-{end} of {len(rows)} filtered "
          f"({total_rows} total in feed) ━━━\n")
    for r in rows[start:end]:
        votes = _vote_status(r)
        cred = f"{r['credibility']:.2f}" if isinstance(r["credibility"], (int, float)) else "?"
        header = f"[{r['id']}] {r['name']}  (cred {cred}, {r['type'] or '?'}, {votes})"
        print(header)
        print("  " + "-" * (min(len(header), 88)))

        ev = r.get("eval") or {}
        if ev.get("lede"):
            print(f"  VERDICT:   {ev['lede']}")
        elif r.get("ai_notes"):
            print(f"  AI notes:  {r['ai_notes']}")

        if ev.get("strengths"):
            print("  STRENGTHS:")
            print(_wrap(ev["strengths"]))
        if ev.get("limitations"):
            print("  CONCERNS:")
            print(_wrap(ev["limitations"]))
        if ev.get("recommended_use"):
            print("  USE AS:")
            print(_wrap(ev["recommended_use"]))

        if r["url"]:
            print(f"  URL: {r['url']}")
        extra = len(r["urls"]) - (1 if r["url"] in r["urls"] else 0)
        if extra > 0:
            print(f"  (+{extra} more source URL{'s' if extra != 1 else ''} on this entity)")
        print()
    if end < len(rows):
        print(f"-- {len(rows) - end} more entities. Next: --page {page + 1} --page-size {page_size}")


def vote(token, pipeline_id, entity_id, vote_type):
    user_uuid = _user_uuid(token)
    status, data = _call(
        "POST",
        "/api/locations/v1/entity-votes/toggle",
        token,
        {
            "entity_id": entity_id,
            "pipeline_id": pipeline_id,
            "keycloak_user_id": user_uuid,
            "vote_type": vote_type,
        },
    )
    return status, data


def remove_entity(token, feed_id, entity_id):
    status, data = _call(
        "DELETE", f"/api/locations/api/v1/feeds/{feed_id}/entities/{entity_id}", token
    )
    return status, data


def suggest_updates(rows):
    """Compare metadata distributions between liked/disliked entities and
    print plain-language suggestions + candidate agent_config/discovery_config
    values. Pure heuristic, no API calls -- human reviews before applying."""
    liked = [r for r in rows if "like" in r["votes"]]
    disliked = [r for r in rows if "dislike" in r["votes"]]
    flagged = [r for r in rows if "flag" in r["votes"]]

    if not liked and not disliked:
        print("No votes recorded yet -- vote on some entities first, then re-run suggest.")
        return

    print(f"Reviewed: {len(liked)} liked, {len(disliked)} disliked, {len(flagged)} flagged "
          f"(out of {len(rows)} total entities)\n")

    def dist(group, field):
        return Counter(r[field] for r in group if r.get(field) is not None)

    for field, ui_hint in [
        ("type", "search_generation.focus_types"),
        ("language", "search_generation.language_preference"),
        ("local_focus", "evaluation.local_focus_priority"),
        ("quality", "evaluation.quality_standards"),
    ]:
        liked_dist = dist(liked, field)
        disliked_dist = dist(disliked, field)
        if not liked_dist and not disliked_dist:
            continue
        print(f"-- {field} --")
        print(f"   liked:    {dict(liked_dist)}")
        print(f"   disliked: {dict(disliked_dist)}")
        # simple heuristic: a value disliked >= 2x as often (proportionally) as liked
        all_values = set(liked_dist) | set(disliked_dist)
        for val in all_values:
            l = liked_dist.get(val, 0)
            d = disliked_dist.get(val, 0)
            if d >= 2 and d >= 2 * max(l, 1):
                print(f"   SUGGEST: entities of {field}='{val}' are disproportionately disliked "
                      f"({d} dislikes vs {l} likes) -- consider adjusting agent_config.{ui_hint} "
                      f"to de-emphasize/exclude '{val}'.")
            if l >= 2 and l >= 2 * max(d, 1):
                print(f"   SUGGEST: entities of {field}='{val}' are disproportionately liked "
                      f"({l} likes vs {d} dislikes) -- consider adjusting agent_config.{ui_hint} "
                      f"to favor '{val}'.")
        print()

    if liked:
        avg_liked_cred = sum(r["credibility"] for r in liked if r["credibility"] is not None) / max(
            1, sum(1 for r in liked if r["credibility"] is not None)
        )
        print(f"Average credibility_score of liked entities: {avg_liked_cred:.2f}")
    if disliked:
        avg_disliked_cred = sum(
            r["credibility"] for r in disliked if r["credibility"] is not None
        ) / max(1, sum(1 for r in disliked if r["credibility"] is not None))
        print(f"Average credibility_score of disliked entities: {avg_disliked_cred:.2f}")
        if liked and avg_disliked_cred < avg_liked_cred - 0.05:
            print(
                "SUGGEST: disliked entities skew lower credibility than liked ones -- "
                f"consider raising agent_config.evaluation.credibility_threshold above "
                f"~{avg_disliked_cred:.2f} to filter them out at discovery time."
            )

    print(
        "\nNote: the NEXT discovery job run (see ubiquity-discovery-jobs) automatically "
        "includes a vote_context block listing every liked/disliked entity by name+type, "
        "so even without changing Agent Settings, voting already biases future discovery. "
        "These suggestions are for TUNING agent_config further, not required to make votes count."
    )


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--feed-id", type=int, required=True)
    p_list.add_argument("--pipeline-id", required=True)
    p_list.add_argument("--sort-by", choices=["credibility", "name", "id"], default="credibility")
    p_list.add_argument("--reverse", action="store_true", help="highest-first instead of lowest-first")
    p_list.add_argument("--only-unvoted", action="store_true")

    p_page = sub.add_parser("page", help="view N entities at a time, with AI notes + source URLs")
    p_page.add_argument("--feed-id", type=int, required=True)
    p_page.add_argument("--pipeline-id", required=True)
    p_page.add_argument("--page", type=int, default=0, help="0-indexed page number")
    p_page.add_argument("--page-size", type=int, default=5)
    p_page.add_argument("--sort-by", choices=["credibility", "name", "id"], default="credibility")
    p_page.add_argument("--reverse", action="store_true", help="highest-first instead of lowest-first")
    p_page.add_argument("--only-unvoted", action="store_true")
    p_page.add_argument(
        "--with-notes",
        action="store_true",
        default=True,
        help="fetch full evaluation-log notes for this page's rows (default on; use --no-with-notes to skip)",
    )
    p_page.add_argument("--no-with-notes", dest="with_notes", action="store_false")
    p_page.add_argument(
        "--table",
        action="store_true",
        help="render as a plain-text grid table (ID/Name/Source URLs/Type/Notes/Vote status) "
        "with full untruncated multi-line cells instead of long-form cards",
    )
    p_page.add_argument(
        "--col-width", type=int, default=50,
        help="wrap width for Name/Notes columns in --table mode (default 50; URLs are never wrapped)",
    )

    p_start = sub.add_parser(
        "start",
        help="freeze entity order for a review pass -- run this ONCE before paging, "
        "so later votes don't shift what 'page N' means",
    )
    p_start.add_argument("--feed-id", type=int, required=True)
    p_start.add_argument("--pipeline-id", required=True)
    p_start.add_argument("--sort-by", choices=["credibility", "name", "id"], default="credibility")
    p_start.add_argument("--reverse", action="store_true")
    p_start.add_argument("--only-unvoted", action="store_true")

    p_vote = sub.add_parser("vote", help="apply a vote IMMEDIATELY (bypasses the queue/apply flow)")
    p_vote.add_argument("--pipeline-id", required=True)
    p_vote.add_argument("--entity-id", type=int, required=True)
    p_vote.add_argument("--vote-type", choices=["like", "dislike", "flag"], required=True)

    p_queue = sub.add_parser(
        "queue", help="stage a vote in the session WITHOUT calling the API yet (use with start/page/apply)"
    )
    p_queue.add_argument("--feed-id", type=int, required=True)
    p_queue.add_argument("--pipeline-id", required=True)
    p_queue.add_argument("--entity-id", type=int, required=True)
    p_queue.add_argument(
        "--vote-type", choices=["like", "dislike", "flag", "clear"], required=True,
        help="'clear' removes any staged vote for this entity without applying anything",
    )

    p_queue_remove = sub.add_parser("queue-remove", help="stage an entity removal for the next `apply`")
    p_queue_remove.add_argument("--feed-id", type=int, required=True)
    p_queue_remove.add_argument("--pipeline-id", required=True)
    p_queue_remove.add_argument("--entity-id", type=int, required=True)
    p_queue_remove.add_argument("--undo", action="store_true", help="un-queue a previously staged removal")

    p_apply = sub.add_parser("apply", help="push all queued votes/removals from the session to the live API")
    p_apply.add_argument("--feed-id", type=int, required=True)
    p_apply.add_argument("--pipeline-id", required=True)

    p_remove = sub.add_parser("remove", help="remove an entity IMMEDIATELY (bypasses the queue/apply flow)")
    p_remove.add_argument("--feed-id", type=int, required=True)
    p_remove.add_argument("--entity-id", type=int, required=True)

    p_suggest = sub.add_parser("suggest")
    p_suggest.add_argument("--feed-id", type=int, required=True)
    p_suggest.add_argument("--pipeline-id", required=True)

    args = ap.parse_args()
    token = _load_token()

    if args.cmd == "list":
        entities, total, source_count, dataset_count = fetch_entities(token, args.feed_id)
        votes = fetch_votes(token, args.pipeline_id)
        rows = build_review_table(entities, votes)
        if args.only_unvoted:
            rows = [r for r in rows if not r["votes"]]
        rows = sort_rows(rows, sort_by=args.sort_by, reverse=args.reverse)
        print(f"Feed {args.feed_id}: {total} entities ({source_count} sources, {dataset_count} datasets)\n")
        print_table(rows)

    elif args.cmd == "start":
        ids, path = start_session(
            args.feed_id, args.pipeline_id,
            sort_by=args.sort_by, reverse=args.reverse, only_unvoted=args.only_unvoted,
        )
        print(f"Review session started: {len(ids)} entities frozen in order, saved to {path}")
        print("Now run `page --page 0 ...` -- the order stays fixed across votes until you "
              "run `start` again (e.g. to pick up newly-discovered entities).")

    elif args.cmd == "page":
        entities, total, source_count, dataset_count = fetch_entities(token, args.feed_id)
        votes = fetch_votes(token, args.pipeline_id)
        rows = build_review_table(entities, votes)
        rows_by_id = {r["id"]: r for r in rows}

        session = load_session(args.feed_id, args.pipeline_id)
        if session:
            queued_votes = session.get("queued_votes", {})
            queued_removals = set(session.get("queued_removals", []))
            ordered = [rows_by_id[i] for i in session["ids"]
                       if i in rows_by_id and i not in queued_removals]
            for r in ordered:
                qv = queued_votes.get(str(r["id"]))
                if qv:
                    r["votes"] = sorted(set(r["votes"]) | {qv})
                    r["queued"] = True
            if args.only_unvoted:
                ordered = [r for r in ordered if not r["votes"]]
        else:
            print("(no frozen session found for this feed/pipeline -- run `start` first for a "
                  "stable review order where votes don't reshuffle later pages; falling back to "
                  "a live re-sort for this call)\n")
            ordered = rows
            if args.only_unvoted:
                ordered = [r for r in ordered if not r["votes"]]
            ordered = sort_rows(ordered, sort_by=args.sort_by, reverse=args.reverse)

        if args.with_notes:
            start = args.page * args.page_size
            end = min(start + args.page_size, len(ordered))

            def _fill(row):
                log = fetch_evaluation_log(token, row["url"])
                if log:
                    notes = (log.get("evaluation_details") or {}).get("evaluation_notes")
                    row["eval"] = _split_notes_sections(notes)
                return row

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(_fill, ordered[start:end]))
        if args.table:
            print_page_table(ordered, args.page, args.page_size, total, col_width=args.col_width)
        else:
            print_page(ordered, args.page, args.page_size, total)

    elif args.cmd == "queue":
        vote_type = None if args.vote_type == "clear" else args.vote_type
        queued = queue_vote(args.feed_id, args.pipeline_id, args.entity_id, vote_type)
        print(f"Queued (not yet applied): entity {args.entity_id} -> "
              f"{vote_type or 'CLEARED'}. Current queue: {queued}")
        print("Run `apply --feed-id ... --pipeline-id ...` when you're done reviewing to push "
              "all queued votes/removals to the API at once.")

    elif args.cmd == "queue-remove":
        queued = queue_removal(args.feed_id, args.pipeline_id, args.entity_id, remove=not args.undo)
        verb = "un-queued" if args.undo else "queued for removal"
        print(f"Entity {args.entity_id} {verb}. Currently queued removals: {queued}")

    elif args.cmd == "apply":
        results = apply_session(args.feed_id, args.pipeline_id)
        if not results:
            print("Nothing queued -- nothing to apply.")
        for r in results:
            mark = "OK" if r["ok"] else "FAILED"
            print(f"[{mark}] entity {r['entity_id']}: {r['action']} (status {r['status']})")
        print(f"\nApplied {sum(1 for r in results if r['ok'])}/{len(results)} queued actions.")

    elif args.cmd == "vote":
        status, data = vote(token, args.pipeline_id, args.entity_id, args.vote_type)
        print(status, json.dumps(data, indent=2))

    elif args.cmd == "remove":
        status, data = remove_entity(token, args.feed_id, args.entity_id)
        print(status, json.dumps(data, indent=2))

    elif args.cmd == "suggest":
        entities, *_ = fetch_entities(token, args.feed_id)
        votes = fetch_votes(token, args.pipeline_id)
        rows = build_review_table(entities, votes)
        suggest_updates(rows)


if __name__ == "__main__":
    sys.exit(main())
