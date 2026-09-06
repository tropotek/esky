# ai-mem

A self-hosted MCP memory server for the local network. Any MCP-speaking agent
— Claude Code, Codex, the OpenAI Agents SDK — can read and write durable
memory over HTTP, with each context kept in its own database.

**Phase 1** ships the curated layer: facts you and your agents record
deliberately, retrieved by hybrid keyword + semantic search. Automatic
transcript capture (Phase 2) and overnight distillation (Phase 3) come later.

Nothing leaves your network. Embeddings run in-process on ONNX; there is no
API key and no outbound call.

## Why profiles are separate files

Each profile is its own SQLite database, selected by URL path:

```
http://box:8011/mcp/work      ->  /data/work.db
http://box:8011/mcp/personal  ->  /data/personal.db
```

Isolation is physical, not a tag you have to remember to filter on. An agent
pointed at `work` cannot see `personal` even if it asks, and deleting a
context is deleting a file. Profiles are never auto-created — a typo must not
silently swallow a week of memories.

---

## Install

**Requirements:** Docker and Docker Compose. Nothing else — no local Python.

```bash
git clone <repo-url> ai-mem
cd ai-mem
cp .env.example .env
```

Edit `.env`. The two that matter:

```ini
AI_MEM_BIND=127.0.0.1   # 127.0.0.1 = this machine only.
                        # Set to your LAN IP to allow other machines.
AI_MEM_PORT=8011
```

Leave `AI_MEM_BIND` on `127.0.0.1` until you have issued a token (next
section). Then start it:

```bash
docker compose up -d
curl -s http://127.0.0.1:8011/health     # -> {"status":"ok"}
```

The first build downloads the embedding model into the image, so expect a few
minutes. Subsequent builds are cached.

## Set up a profile

Create one profile per context you want kept separate — `work`, `personal`,
whatever fits. Then issue its token.

```bash
docker compose exec ai-mem ai-mem profile create personal
docker compose exec ai-mem ai-mem token issue personal
```

The token prints **once** and is not recoverable — only its SHA-256 hash is
stored. Copy it now. If you lose it, issue a new one; that invalidates the
old.

> Run `token issue` in a plain terminal, not inside an AI chat session. Tokens
> pasted into a transcript should be treated as burned and reissued.

Confirm it works:

```bash
TOKEN=aimem_...
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8011/api/profiles
# -> {"profiles":["personal"]}
```

That returns only the profile your token grants. If it lists the profile you
expect and nothing else, isolation is working.

## Connect Claude Code

### On the same machine

```bash
claude mcp add -s user --transport http mem \
  http://127.0.0.1:8011/mcp/personal \
  --header "Authorization: Bearer $TOKEN"
```

`-s user` registers it in your user config so it is available in every
project. Drop it to add the server to the current project only.

**If you have already set `AI_MEM_BIND` to a LAN address, use that address
here too, not `127.0.0.1`.** Docker publishes the port on one interface only,
so binding to `192.168.0.7` makes loopback unreachable — a local client gets a
connection refused that looks nothing like a config error.

The server is only picked up by **new** sessions. Restart Claude, then run
`/mcp` to confirm.

### From another machine on the LAN

First expose the port on the host. In `.env` on the **server**:

```ini
AI_MEM_BIND=192.168.0.7    # the server's LAN address
```

```bash
docker compose up -d
```

If the host runs a firewall, allow the port from your subnet only:

```bash
sudo ufw allow from 192.168.0.0/24 to any port 8011 proto tcp
```

From the **client** machine, verify reachability before involving Claude:

```bash
curl -m 5 -H "Authorization: Bearer $TOKEN" \
  http://192.168.0.7:8011/api/profiles
```

Once that returns your profile, add the server:

```bash
claude mcp add -s user --transport http mem \
  http://192.168.0.7:8011/mcp/personal \
  --header "Authorization: Bearer $TOKEN"
```

Start a new session and run `/mcp` — `mem` should show as connected, with five
tools. Test it with *"search your memory for X"*, or *"remember that I prefer
X"*.

### Multiple accounts or machines

Give each its own profile and token:

```bash
docker compose exec ai-mem ai-mem profile create work
docker compose exec ai-mem ai-mem token issue work
```

Point that client at `/mcp/work`. Two Claude accounts on one machine, or a
laptop and a desktop, can share a profile by sharing its token, or stay
separate by having their own. The server enforces the boundary; the agent
cannot cross it by asking.

### Other MCP clients

Any client that speaks MCP streamable HTTP with a custom header works. The
endpoint is `http://<host>:<port>/mcp/<profile>` and the header is
`Authorization: Bearer <token>`. For clients configured by JSON:

```json
{
  "mcpServers": {
    "mem": {
      "type": "http",
      "url": "http://192.168.0.7:8011/mcp/personal",
      "headers": { "Authorization": "Bearer aimem_..." }
    }
  }
}
```

### What to expect

**Claude will not use memory on its own yet.** Phase 1 gives it tools, not
reflexes — it searches memory when you ask, or when a `CLAUDE.md` tells it to.
Automatic recall at session start is Phase 2.

To make it habitual in the meantime, add something like this to your
`CLAUDE.md`:

```markdown
Before assuming anything about how I work, what a project uses, or why a past
decision was made, call `memory_search`. When you learn something durable that
would be useful in a future session, call `memory_write`.
```

---

## Rotating a token

Issuing a new token invalidates the old one **immediately** — there is no
grace period — so every client using it stops working until you update it.
Rotate the server first, then each client:

```bash
# on the server
docker compose exec ai-mem ai-mem token issue personal

# on every machine connected to that profile
claude mcp remove -s user mem
claude mcp add -s user --transport http mem \
  http://192.168.0.7:8011/mcp/personal \
  --header "Authorization: Bearer <new-token>"
```

Run `token issue` in a plain terminal, not inside an AI chat session — a token
pasted into a transcript should be treated as burned. Rotating costs seconds,
which makes "reissue whenever a token has been near a chat window" a cheap
default.

`claude mcp list` reports `✔ Connected` or a `401`, so it doubles as a check
that a rotation landed. Clients pick up the new config on their **next**
session, not the current one.

Rotate when a token has been pasted somewhere it shouldn't, when a machine
that held it is decommissioned, or when you want to cut off one client without
disturbing the others — for that last case, give it its own profile instead,
since a profile's token is shared by everything pointed at it.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `curl` hangs, returns nothing | Malformed URL. `curl` reads `192.161` as the IP `192.0.0.161` and waits. Check the full address **and** the `:8011` port — without it, curl tries port 80. Always pass `-m 5`. |
| `{"error":"unauthorized"}` | Missing, wrong, or another profile's token; or no token issued for that profile; or the profile does not exist. All return an identical 401 by design — see Security. |
| `Connection refused` from another machine | `AI_MEM_BIND` is still `127.0.0.1`. Set it to the LAN IP and `docker compose up -d`. |
| Connection times out from another machine | Host firewall. Check `sudo ufw status`. |
| `/mcp` shows the server but no tools | Token rejected at connect. Test the same token with the `/api/profiles` curl above. |
| Tool descriptions look out of date | Clients cache them at session start. Restart the Claude session. |

Server-side checks:

```bash
docker compose ps                                    # running and healthy?
docker compose logs --tail=50 ai-mem                 # errors?
docker compose exec ai-mem ai-mem profile list       # which profiles exist
docker compose exec ai-mem ai-mem token status work  # is a token issued
curl -s http://127.0.0.1:8011/health                 # needs no token
```

---

## Tools

| Tool | Purpose |
|---|---|
| `memory_search` | Hybrid BM25 + vector search over curated facts |
| `memory_write` | Record a durable fact |
| `memory_update` | Amend a fact; a text change supersedes rather than overwrites |
| `memory_forget` | Retire a fact — soft, never destroyed |
| `memory_recent` | Recently written or updated facts |

Fact kinds:

| Kind | For |
|---|---|
| `user` | Who you are: role, expertise, context |
| `preference` | How you want work done |
| `project` | Goals, constraints, or state of ongoing work |
| `reference` | A pointer to something external: URL, ticket, dashboard |
| `research` | Findings you gathered, with the conclusion stated |
| `decision` | A choice made and the reasoning behind it |

`reference` points at where something lives; `research` carries the finding
itself.

## CLI

| Command | Purpose |
|---|---|
| `ai-mem profile create <name>` | Create a profile database |
| `ai-mem profile list` | List profiles |
| `ai-mem token issue <profile>` | Issue a token, invalidating any previous one |
| `ai-mem token status <profile>` | Whether a token has been issued, and when |
| `ai-mem serve` | Run the server |

Run them via `docker compose exec ai-mem <command>`.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `AI_MEM_BIND` | `127.0.0.1` | Host interface the port publishes on |
| `AI_MEM_PORT` | `8080` | Published port |
| `AI_MEM_DATA_DIR` | `/data` | Where profile databases live |
| `AI_MEM_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | 384-dim; changing this needs a reindex |
| `AI_MEM_RRF_K` | `60` | Reciprocal rank fusion constant |
| `AI_MEM_MAX_DISTANCE` | `0.9` | Relevance floor for vector hits |

`AI_MEM_MAX_DISTANCE` is worth understanding: vector KNN returns its nearest
neighbours however unrelated they are, so without a floor a nonsense query
still hands the agent confident-looking facts. Measured L2 distances over
unit-normalised `bge-small` vectors put related queries at 0.54–0.74 and
unrelated at 0.88–1.00. Raise it if recall looks too tight, lower it if
searches return noise.

## Security

Every profile is gated by its own bearer token. A token grants **exactly one
profile** — a leaked `work` token cannot read `personal`, and revoking one
profile leaves the others alone.

The server **fails closed**: a profile with no token issued rejects every
request. There is no anonymous mode and no localhost exemption.

Only a SHA-256 hash is stored, in the profile's own database. Backing up
`work.db` carries its token; `rm work.db` revokes it. Rotation is reissue —
there is no grace period, the old token stops working immediately.

Two behaviours that look odd until you know why:

- **Unknown profiles return 401, not 404.** A distinct 404 would let anyone on
  the network enumerate which profiles exist without holding a token. Missing
  token, wrong token, another profile's token and a nonexistent profile all
  return an identical `401 {"error": "unauthorized"}`.
- **`/health` needs no token.** The compose healthcheck depends on it and it
  reveals nothing. Everything else, including `/api/profiles`, requires one.

There is no rate limiting, deliberately: at 256 bits of entropy there is
nothing to guess, so throttling would add complexity against an attack that
cannot succeed.

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

Design documents live in `_notes/docs/` and are gitignored.
