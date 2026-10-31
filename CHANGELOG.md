# Changelog

## Unreleased

- Idle background polls no longer take the SQLite write lock: each poller (`process_one`, `review_one`, chat organization, backfill, relation enrichment, knowledge parsing) checks for pending work with a read-only query first. With many providers sharing one database this removes the lock convoy that starved real writers.
- Opening a database whose `user_version` is already current no longer starts a write transaction.
- `embed_one` selects candidates in a read snapshot, so the embedding call is not made inside a write transaction.
- Background polling now backs off with jitter (`gramem/polling.py`) and failure logs are rate limited to one summary a minute after the first traceback.

## 2.5.0

First public release.

- Sourced, versioned memories with Always / Relevant / Historical recall inside a token budget.
- Disable, forget, re-enable and re-authorize that propagate to originals, derived facts, profiles and the graph.
- Owner / Contact / Group scopes with per-profile isolation and verified account linking.
- Knowledge library for PDF, DOCX, text and images with OCR, versions, export and ZIP.
- Chat archive with transcripts, summaries, topic timelines and assistant audio.
- Memory network (facts, files, chats, audio, topics, events) backed by an optional FalkorDB graph.
- Standalone `gramem` CLI, native Hermes Agent memory provider, and an optional admin console.
