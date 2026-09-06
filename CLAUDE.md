# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted MCP memory server for the LAN. Agents read and write durable
memory over streamable HTTP; each context is a separate SQLite file.

## Project state

- **Phase 1 (curated layer) — done.** Profiles, `facts`, FTS5 + sqlite-vec,
  RRF search, five MCP tools, CLI, Docker.
- **Phase 1.5 (per-profile bearer tokens) — done.** Deployed and in use from
  two machines.
- **Phase 2 (capture) — not started.** `sessions` / `observations`, ingest
  endpoint, `SessionStart` recall digest, Claude Code hooks, retention pruning.
- **Phase 3 (distillation) — not started.** llama.cpp nightly batch,
  `candidates` airlock, `memory_review` tool, GPU-guarded cron script.

## Design documents

**`_notes/` is gitignored — read it before planning anything.**

- `_notes/docs/specs/2026-09-06-esky-design.md` — the design. §13 is the
  phase breakdown, §14 the deliberately deferred decisions.
- `_notes/docs/plans/` — implementation plans, one per phase.
- `_notes/research/` — research and future ideas that are not yet committed
  work. `retrieval-scaling.md` covers how search degrades as the store grows;
  `ideas-backlog.md` holds loose ends and open questions.

Specs and plans go in `_notes/docs/`, research and speculative ideas in
`_notes/research/`, never in a committed `docs/`. Skip the
"commit the design doc" step that the brainstorming and writing-plans skills
ask for; the folder is deliberately untracked.

## Commands

Everything runs in Docker. There is no local Python environment.

```bash
docker compose run --rm test pytest -q                    # full suite (103 tests)
docker compose run --rm test pytest tests/test_search.py -v
docker compose run --rm test pytest tests/test_facts.py::test_write_returns_fact_with_uid -v
docker compose build test                                 # only when deps change
docker compose up -d                                      # run the server
docker compose exec esky esky profile create <name>
docker compose exec esky esky token issue <profile>
```

Source is bind-mounted into the dev container, so edits apply without a
rebuild.

## Architecture

**One ASGI app, two surfaces** (`app.py`). MCP at `/mcp/{profile}` is what
agents talk to and is kept to five tools, because every tool description costs
context in every session. REST at `/api/…` is for hooks, cron and ops. Phase 2
adds ingest and recall to the REST side, not the MCP side.

**Profile routing is an ASGI wrapper, not Starlette routing.** `Mount` does
not support path parameters, so `ProfileDispatcher` strips the leading
segment, authorises it, and binds it to a ContextVar that `mcp_server.py`
reads. Starlette leaves the full path in `scope["path"]` and records the mount
prefix in `root_path`; the dispatcher handles both conventions.

**Two inference paths, deliberately.** Embeddings are in-process
(`fastembed`/ONNX) because they sit on the write path and a write must not
fail because a service is down. Phase 3's distillation is external and
asynchronous, where an outage costs only latency.

## Invariants

Breaking these silently breaks the guarantees the design rests on:

- **Profiles are never auto-created.** A typo must not spawn `wrok.db`.
  Creation is CLI-only and never reachable over HTTP.
- **Every auth failure returns an identical 401** — missing token, wrong
  token, another profile's token, un-issued profile, nonexistent profile. A
  distinct 404 would make the endpoint a profile-name oracle.
- **Curated facts are never hard-deleted.** `memory_forget` sets
  `retired_at`; a text change via `memory_update` retires and supersedes
  rather than mutating.
- **FTS and vector indexes are maintained explicitly in `FactsRepo`**, not by
  triggers. The vector index needs an embedding computed in Python, so
  splitting the work between triggers and code would leave two places to get
  it wrong.
- **`EMBED_DIM` lives only in `config.py`** and must match the `FLOAT[384]`
  in the DDL. Changing the embedding model requires a reindex.
- **Vector search needs its distance floor.** KNN returns k neighbours however
  unrelated, so without `ESKY_MAX_DISTANCE` a nonsense query hands the agent
  confident-looking facts. Measured L2 over unit-normalised `bge-small`:
  related 0.54–0.74, unrelated 0.88–1.00.

## Testing

`tests/conftest.py` provides a `FakeEmbedder` — a deterministic bag-of-words
hash. Retrieval tests assert ranking, which only needs "similar text produces
similar vector", and the fake makes that reproducible and fast. Only
`test_embedding.py` loads the real model.

The end-to-end HTTP test caught a routing bug that every unit test missed. When
changing `app.py`, verify against a running container, not just the suite.
