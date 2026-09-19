# esky 🧊

**A cold box for your agents' memory. Self-hosted, on your own network.**

A self-hosted MCP memory server for the local network. Any MCP-speaking agent
— Claude Code, Codex, the OpenAI Agents SDK — can read and write durable
memory over HTTP, with each context kept in its own database.

Agents start every session cold. esky is the box on the network they all
reach into: put a fact in from the laptop, take it out from the desktop, and
it is still there next week.

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
git clone <repo-url> esky
cd esky
cp .env.example .env
```

Edit `.env`. The ones that matter:

```ini
ESKY_BIND=127.0.0.1   # 127.0.0.1 = this machine only.
                      # Set to your LAN IP to allow other machines.
ESKY_PORT=8011
ESKY_UID=1000         # your host user — `id -u`
ESKY_GID=1000         # your host group — `id -g`
```

`ESKY_UID`/`ESKY_GID` make the container run as you, so the SQLite files in
`./data` are yours to open rather than root's. Leave them unset and the
container runs as root, which is how you end up unable to read your own
database from the host.

Leave `ESKY_BIND` on `127.0.0.1` until you have issued a token (next
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
docker compose exec esky esky profile create personal
docker compose exec esky esky token issue personal
```

The token prints **once** and is not recoverable — only its SHA-256 hash is
stored. Copy it now. If you lose it, issue a new one; that invalidates the
old.

> Run `token issue` in a plain terminal, not inside an AI chat session. Tokens
> pasted into a transcript should be treated as burned and reissued.

Confirm it works:

```bash
TOKEN=esky_...
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8011/api/profiles
# -> {"profiles":["personal"]}
```

That returns only the profile your token grants. If it lists the profile you
expect and nothing else, isolation is working.

## Connect Claude Code

### On the same machine

```bash
claude mcp add -s user --transport http esky \
  http://127.0.0.1:8011/mcp/personal \
  --header "Authorization: Bearer $TOKEN"
```

`-s user` registers it in your user config so it is available in every
project. Drop it to add the server to the current project only.

`esky` there is just the local alias for the server — call it anything you
prefer. It shows up in `/mcp`; the tool names (`memory_search` and friends)
are fixed either way.

**If you have already set `ESKY_BIND` to a LAN address, use that address
here too, not `127.0.0.1`.** Docker publishes the port on one interface only,
so binding to `192.168.0.7` makes loopback unreachable — a local client gets a
connection refused that looks nothing like a config error.

The server is only picked up by **new** sessions. Restart Claude, then run
`/mcp` to confirm.

### From another machine on the LAN

First expose the port on the host. In `.env` on the **server**:

```ini
ESKY_BIND=192.168.0.7    # the server's LAN address
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
claude mcp add -s user --transport http esky \
  http://192.168.0.7:8011/mcp/personal \
  --header "Authorization: Bearer $TOKEN"
```

Start a new session and run `/mcp` — `esky` should show as connected, with five
tools. Test it with *"search your memory for X"*, or *"remember that I prefer
X"*.

### Multiple accounts or machines

Give each its own profile and token:

```bash
docker compose exec esky esky profile create work
docker compose exec esky esky token issue work
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
    "esky": {
      "type": "http",
      "url": "http://192.168.0.7:8011/mcp/personal",
      "headers": { "Authorization": "Bearer esky_..." }
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
docker compose exec esky esky token issue personal

# on every machine connected to that profile
claude mcp remove -s user esky
claude mcp add -s user --transport http esky \
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
| `./data/*.db` owned by `root`, unreadable from the host | Set `ESKY_UID`/`ESKY_GID` in `.env`, then fix the existing files once: `docker run --rm -v "$PWD/data:/data" alpine chown -R $(id -u):$(id -g) /data` |
| `Connection refused` from another machine | `ESKY_BIND` is still `127.0.0.1`. Set it to the LAN IP and `docker compose up -d`. |
| Connection times out from another machine | Host firewall. Check `sudo ufw status`. |
| `/mcp` shows the server but no tools | Token rejected at connect. Test the same token with the `/api/profiles` curl above. |
| Tool descriptions look out of date | Clients cache them at session start. Restart the Claude session. |

Server-side checks:

```bash
docker compose ps                                   # running and healthy?
docker compose logs --tail=50 esky                  # errors?
docker compose exec esky esky profile list          # which profiles exist
docker compose exec esky esky token status work     # is a token issued
curl -s http://127.0.0.1:8011/health                # needs no token
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

## The query log

Every search is recorded — the query, the best hit, and two counts:
`matched_count`, how many facts the search found, and `returned_count`, how many
you were handed once `limit` was applied. Both are needed: a `returned_count` of
2 means nothing on its own, because it reads the same whether the store held two
facts or two hundred.

A search with `matched_count: 0` is the interesting case. It is the only record
of something you expected memory to know and it did not, and that evidence does
not exist unless it is captured as it happens.

```bash
curl -H "Authorization: Bearer $ESKY_TOKEN" \
  http://192.168.0.7:8011/api/personal/queries?limit=20
```

```json
{"profile": "personal",
 "queries": [{"query": "how do we deploy", "tags": [],
              "matched_count": 0, "returned_count": 0,
              "top_uid": null, "created_at": "2026-09-19T04:56:15+00:00"}]}
```

`limit` defaults to 50 and accepts 1–500; anything else is a `400`, because a
negative `LIMIT` means "no limit" to SQLite and would quietly defeat the cap.
Rows written before `matched_count` existed carry `null` for it rather than a
guess.

The log is per profile and behind the same token as everything else, so the
`work` log is not readable with the `personal` token. It is REST-only and not
an MCP tool: it is for you reviewing the store, and every tool description
costs context in every agent session.

## CLI

| Command | Purpose |
|---|---|
| `esky profile create <name>` | Create a profile database |
| `esky profile list` | List profiles |
| `esky token issue <profile>` | Issue a token, invalidating any previous one |
| `esky token status <profile>` | Whether a token has been issued, and when |
| `esky profile migrate <name>` | Bring a profile up to the current schema |
| `esky profile reindex <name>` | Recompute every embedding after an embedding change |
| `esky serve` | Run the server |

Run them via `docker compose exec esky <command>`.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `ESKY_BIND` | `127.0.0.1` | Host interface the port publishes on |
| `ESKY_PORT` | `8080` | Published port |
| `ESKY_UID` | `0` | Host UID the containers run as; set to `id -u` |
| `ESKY_GID` | `0` | Host GID the containers run as; set to `id -g` |
| `ESKY_DATA_DIR` | `/data` | Where profile databases live |
| `ESKY_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | 384-dim; changing this needs a reindex |
| `ESKY_RRF_K` | `60` | Reciprocal rank fusion constant |
| `ESKY_MAX_DISTANCE` | `0.9` | Relevance floor for vector hits |

`ESKY_MAX_DISTANCE` is worth understanding: vector KNN returns its nearest
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

## The name

An esky is what Australians call a cool box — the one everybody brings to the
shared thing, that keeps what you put in it. It is a **code name**: chosen
because it describes the job better than `ai-mem` did, not because it is a
brand. If this ever goes past the LAN it gets revisited.

Prior to 2026-09-06 the project was `ai-mem`, and every environment variable
carried an `AI_MEM_` prefix. Those are gone — only `ESKY_*` is read, and a
stale `.env` will start the server on `127.0.0.1:8080` instead of your LAN
address.

Tokens issued before the rename begin with `aimem_` rather than `esky_`. They
keep working — only the whole string's hash is ever compared, and the prefix
carries no meaning — so reissue for tidiness, not out of necessity.
