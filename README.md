# ai-mem

A self-hosted MCP memory server for the local network. Any MCP-speaking agent
— Claude Code, Codex, OpenAI Agents SDK — can read and write durable memory
over HTTP, with each context kept in its own database.

**Phase 1** ships the curated layer: facts you and your agents record
deliberately, retrieved by hybrid keyword + semantic search. Automatic
transcript capture (Phase 2) and overnight distillation (Phase 3) come later.

## Why profiles are separate files

Each profile is its own SQLite database, selected by URL path:

```
http://box:8080/mcp/work      ->  /data/work.db
http://box:8080/mcp/personal  ->  /data/personal.db
```

Isolation is physical, not a tag you have to remember to filter on. An agent
pointed at `work` cannot see `personal` even if it asks, and deleting a
context is deleting a file. Unknown profiles return 404 and are never
auto-created — a typo must not silently swallow a week of memories.

## Running it

```bash
docker compose up -d
docker compose exec ai-mem ai-mem profile create work
docker compose exec ai-mem ai-mem profile list
```

Connect an agent:

```bash
claude mcp add --transport http mem-work http://<host>:8080/mcp/work
```

Give each Claude account its own profile URL, and they keep separate memories.

## Security

Every profile is gated by its own bearer token. A token grants **exactly one
profile** — a leaked `work` token cannot read `personal`, and revoking one
profile leaves the others alone.

The server **fails closed**: a profile with no token issued rejects every
request. There is no anonymous mode and no localhost exemption.

```bash
docker compose exec ai-mem ai-mem token issue work
docker compose exec ai-mem ai-mem token status work
```

The token is printed once and never recoverable — only its SHA-256 hash is
stored, in the profile's own database. Issuing again invalidates the previous
token; that is how you rotate. Deleting `work.db` revokes its token with it.

Connect an agent:

```bash
claude mcp add -s user --transport http mem-work \
  http://192.168.0.7:8011/mcp/work \
  --header "Authorization: Bearer aimem_..."
```

With tokens in place, `AI_MEM_BIND` may be set to a LAN address.

Two behaviours that look odd until you know why:

- **Unknown profiles return 401, not 404.** A distinct 404 would let anyone on
  the network enumerate which profiles exist without holding a token. Missing
  token, wrong token, another profile's token and a nonexistent profile all
  return an identical `401 {"error": "unauthorized"}`.
- **`/health` needs no token.** The compose healthcheck depends on it and it
  reveals nothing. Everything else, including `/api/profiles`, requires one.

`/api/profiles` returns only the profile your token grants, which makes it a
convenient way to confirm a token works from another machine:

```bash
curl -H "Authorization: Bearer $TOKEN" http://192.168.0.7:8011/api/profiles
```

## Tools

| Tool | Purpose |
|---|---|
| `memory_search` | Hybrid BM25 + vector search over curated facts |
| `memory_write` | Record a durable fact (`user`, `preference`, `project`, `reference`, `decision`) |
| `memory_update` | Amend a fact; a text change supersedes rather than overwrites |
| `memory_forget` | Retire a fact — soft, never destroyed |
| `memory_recent` | Recently written or updated facts |

## CLI

| Command | Purpose |
|---|---|
| `ai-mem profile create <name>` | Create a profile database |
| `ai-mem profile list` | List profiles |
| `ai-mem token issue <profile>` | Issue a token, invalidating any previous one |
| `ai-mem token status <profile>` | Whether a token has been issued, and when |
| `ai-mem serve` | Run the server |

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `AI_MEM_DATA_DIR` | `/data` | Where profile databases live |
| `AI_MEM_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | 384-dim; changing this needs a reindex |
| `AI_MEM_RRF_K` | `60` | Reciprocal rank fusion constant |
| `AI_MEM_MAX_DISTANCE` | `0.9` | Relevance floor for vector hits |
| `AI_MEM_BIND` | `127.0.0.1` | Host interface the port publishes on |
| `AI_MEM_PORT` | `8080` | Published port |

`AI_MEM_MAX_DISTANCE` is worth understanding: vector KNN returns its nearest
neighbours however unrelated they are, so without a floor a nonsense query
still hands the agent confident-looking facts. Measured L2 distances over
unit-normalised `bge-small` vectors put related queries at 0.54–0.74 and
unrelated at 0.88–1.00. Raise it if recall looks too tight, lower it if
searches return noise.

## Development

Everything runs in Docker; no local Python needed.

```bash
docker compose run --rm test pytest -q          # full suite
docker compose run --rm test pytest tests/test_search.py -v
```

Source is bind-mounted into the dev container, so edits apply without
rebuilding. Rebuild only when dependencies change:

```bash
docker compose build test
```
