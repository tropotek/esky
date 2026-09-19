# Esky 🧊

**A cold box for your agents' memory. Self-hosted, on your own network.**

A self-hosted MCP memory server for the local network. Any MCP-speaking agent
— Claude Code, Codex, the OpenAI Agents SDK — can read and write durable
memory over HTTP, with each context kept in its own database.

Agents start every session cold. Esky is the box on the network they all
reach into: put a fact in from the laptop, take it out from the desktop, and
it is still there next week.

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

Esky serves plain HTTP and issues no certificates: it is built for a network
you control. If you want HTTPS, or you want to reach it from outside, put a
reverse proxy in front or extend your private network — see
[security](docs/security.md#traffic-is-not-encrypted).

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

## Connect an agent

On the same machine:

```bash
claude mcp add -s user --transport http esky \
  http://127.0.0.1:8011/mcp/personal \
  --header "Authorization: Bearer $TOKEN"
```

Restart the client — `esky` should show as connected, with five tools (`/mcp`
in Claude Code).

**That is not the last step.** An agent with the tools connected still will
not use them on its own; it needs an instruction in your client's global
standing-instructions file — `~/.claude/CLAUDE.md` for Claude Code, `AGENTS.md`
for most others — saying to search before assuming and write when it learns
something durable. Without it the store is written to and never read from,
which looks exactly like a server that is broken.

→ **[Connecting an agent](docs/connecting.md)** — the LAN setup, the snippet
to paste and where each client keeps it, and other MCP clients.

## Browse what is in there

Esky itself has no interface beyond the tools and the REST endpoints.
[**eskyClient**](https://github.com/tropotek/eskyClient) is a separate
read-only web app that points at a running server: it lists memories newest
first, searches them, shows one as raw Markdown or rendered, and charts what
the store holds alongside what has been asked of it.

It runs in its own container and needs only the profile's URL and bearer
token — the same pair an agent uses. Nothing it does can change the store.

## Documentation

| Page | Covers |
|---|---|
| [Connecting an agent](docs/connecting.md) | Same machine and across the LAN, the standing instruction that makes memory get used, multiple profiles, other MCP clients |
| [Tools and facts](docs/tools.md) | The five tools, fact kinds, the query log |
| [Operations](docs/operations.md) | CLI, configuration, rotating a token, troubleshooting |
| [Security](docs/security.md) | The token model, why unknown profiles return 401, HTTPS via a reverse proxy, backups |
| [Development](docs/development.md) | Running the tests, rebuilding the containers |

## The name

An esky is what Australians call a cool box — the one everybody brings to the
shared thing, that keeps what you put in it. It is a **code name**, chosen
because it describes the job, not a brand. If this ever goes past the LAN it
gets revisited.


