---
name: ubiquity-ubi-chat
description: Use to chat with Ubiquity's Ubi bot about feed artifacts.
---

# Ubiquity: Ubi chat (feed Q&A assistant)

Covers chatting with "Ubi", the assistant that analyzes a pipeline's feed
artifacts and answers questions about them (distinct from the discovery-time
Ubi chat bubble covered in `ubiquity-pipeline-creation`, which only parses
the initial search query -- this is the standing per-feed chat on the
Understand tab, gated behind "Enable Ubi", see `ubiquity-understand-layer`).
Requires a valid Bearer token -- see `ubiquity-auth`.

## Listing chat sessions
```
GET /api/understand/chat/sessions?keycloak_user_id=<url-encoded email>&limit=50&offset=0&feed_id=<feed_id>
  -> [] when none exist yet
```
Sessions are scoped per `(user, feed)` pair -- a given feed can have
multiple chat threads per user, like separate conversations.

## Starting a new chat / sending a message
UI entry point: "New Chat" button, plus three canned starter prompts shown
in the empty state:
- "Summarize the recent artifacts from my feed, highlighting key themes and
  important findings."
- "List the main themes and topics that appear in the recent artifacts."
- "Analyze and evaluate the overall tone and sentiment of the recent
  artifacts."

These read as generic prompt templates (not API-sourced) rather than
server-driven suggestions, but treat that as unconfirmed. The actual
send-message endpoint was **not yet captured on the wire** -- the feed was
still "Collecting data..." during recon (Understand tab is gated until the
feed has artifacts, see `ubiquity-understand-layer`), so "New Chat" never
produced a live network call to inspect. Expect something like:
```
POST /api/understand/chat/sessions                 # create a session for (feed_id, user)
POST /api/understand/chat/sessions/<session_id>/messages   # send a message, body: {"message": "<text>"}
```
possibly with a streaming (SSE or chunked) response given the chat-UI
pattern, similar to most LLM-backed chat products -- confirm response
`Content-Type` when you capture it (if `text/event-stream`, use `fetch`
with a streamed reader, not a one-shot `await resp.json()`).

## Artifacts backing the chat
```
GET /api/understand/artifacts/count/<feed_id>   -> {count, feed_id}
POST /api/understand/artifacts/preview
  {"feed_id": <feed_id>, "filter_state": {}, "limit": 1000}
```
See `ubiquity-understand-layer` for the confirmed request shape and the
"Collection `<email>` doesn't exist" 500 you'll get before any artifacts
have actually been ingested (discovering sources is not the same as
ingesting their content -- that's a separate, later step). Ubi's answers
are presumably grounded in these ingested artifacts (the feed's collected
articles/posts/datasets) -- i.e. "querying the data feed api" mentioned in
the broader Ubiquity task maps to this `understand` service family
(`artifacts/*`) plus the raw entities listing in `ubiquity-entity-review`.

## How to finish this skill
Once a pipeline has artifacts (post-discovery, with Ubi enabled -- see
`ubiquity-understand-layer`), open the Understand tab with `browser_exec`,
install the fetch/XHR interceptor (pattern in `ubiquity-entity-review`),
click "New Chat", send a message (e.g. one of the canned prompts above),
and capture:
1. The session-create request/response (does "New Chat" even call the
   server, or is a session only created lazily on first message?).
2. The send-message request body and response shape (streaming or not).
3. How to list/replay a prior session's message history (likely
   `GET /api/understand/chat/sessions/<session_id>/messages` or messages
   embedded directly in the session list response -- not yet confirmed).
Patch this file with the confirmed schema afterward.
