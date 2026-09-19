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
docker compose run --rm test pytest -q                    # full suite
docker compose run --rm test pytest tests/test_search.py -v
docker compose run --rm test pytest tests/test_facts.py::test_write_returns_fact_with_uid -v
docker compose build test                                 # only when deps change
docker compose up -d                                      # run the server
docker compose exec esky esky profile list
docker compose exec esky esky profile create <name>
docker compose exec esky esky token issue <profile>       # rotation is reissue
docker compose exec esky esky token status <profile>
docker compose exec esky esky profile migrate <name>      # after a schema bump
```

`pyproject.toml` sets `addopts = -m 'not slow'`, but nothing is marked `slow`
yet — `test_embedding.py` downloads the real model on every run. Mark it if
that becomes annoying. `docker-compose-live.yml` is the deployed variant;
`docker-compose.yml` is the one to use locally.

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

**Two HTTP surfaces, two auth shapes.** `/health` is unauthenticated on
purpose (the compose healthcheck needs it, and it reveals nothing).
`/api/profiles` scans every profile and reports only the one the presented
token grants; `/api/{profile}/stats` authorises that one profile. Everything
under `/mcp/` is authorised by `ProfileDispatcher` before it reaches a tool.

**Schema changes are numbered steps in `db/schema.py`.** `_V1` is the full
schema and must stay re-runnable; later steps are one-way and apply only
below their version. FTS5 has no `ALTER`, so gaining a column means dropping
and rebuilding `facts_fts` from `facts` — safe, since it is derived data. The
vector index cannot be rebuilt in SQL (embeddings come from Python), so a
migration must never assume it can. Bump `SCHEMA_VERSION` and run
`esky profile migrate` against every existing profile.

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
- **The `kind` vocabulary lives in `facts.KINDS`** and is repeated in the
  `memory_write` tool docstring, which is what an agent actually reads.
  Adding a kind means changing both, or agents never use it.
- **Profile names must match `^[a-z0-9][a-z0-9_-]{0,63}$`** — one safe path
  segment, since the name becomes a filename. `exists_safe` turns an invalid
  name into "no" rather than a 500, so the HTTP path never leaks the
  difference.
- **Vector search needs its distance floor.** KNN returns k neighbours however
  unrelated, so without `ESKY_MAX_DISTANCE` a nonsense query hands the agent
  confident-looking facts. Measured L2 over unit-normalised `bge-small`:
  related 0.54–0.74, unrelated 0.88–1.00.

## Testing

Tests run against SQLite files under `ESKY_DATA_DIR=/tmp/esky-data` in the
container, never `./data`.

`tests/conftest.py` provides a `FakeEmbedder` — a deterministic bag-of-words
hash. Retrieval tests assert ranking, which only needs "similar text produces
similar vector", and the fake makes that reproducible and fast. Only
`test_embedding.py` loads the real model. The fake hashes tokens, so it is
only deterministic with `PYTHONHASHSEED=0` — set in `docker-compose.yml`, and
the reason a bare `pytest` on the host would give flaky rankings even if a
local environment existed.

The end-to-end HTTP test caught a routing bug that every unit test missed. When
changing `app.py`, verify against a running container, not just the suite.
