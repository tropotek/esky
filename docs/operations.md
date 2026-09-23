# Operations

Running the server day to day: the CLI, what you can configure, rotating a
token, and what to check when something is wrong.

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
  http://192.168.1.10:8011/mcp/personal \
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

## Troubleshooting

| Symptom | Cause |
|---|---|
| `curl` hangs, returns nothing | Malformed URL. `curl` reads `192.161` as the IP `192.0.0.161` and waits. Check the full address **and** the `:8011` port — without it, curl tries port 80. Always pass `-m 5`. |
| `{"error":"unauthorized"}` | Missing, wrong, or another profile's token; or no token issued for that profile; or the profile does not exist. All return an identical 401 by design — see [Security](security.md). |
| `./data/*.db` owned by `root`, unreadable from the host | Set `ESKY_UID`/`ESKY_GID` in `.env`, then fix the existing files once: `docker run --rm -v "$PWD/data:/data" alpine chown -R $(id -u):$(id -g) /data` |
| `Connection refused` from another machine | `ESKY_BIND` is still `127.0.0.1`. Set it to the LAN IP and `docker compose up -d`. |
| Connection times out from another machine | Host firewall. Check `sudo ufw status`. |
| `/mcp` shows the server but no tools | Token rejected at connect. Test the same token with the `/api/profiles` curl in [connecting](connecting.md#from-another-machine-on-the-lan). |
| Tool descriptions look out of date | Clients cache them at session start. Restart the Claude session. |
| Connected, but the agent never recalls anything | Expected without the instruction — see [Tell your agent to use it](connecting.md#tell-your-agent-to-use-it). |

Server-side checks:

```bash
docker compose ps                                   # running and healthy?
docker compose logs --tail=50 esky                  # errors?
docker compose exec esky esky profile list          # which profiles exist
docker compose exec esky esky token status work     # is a token issued
curl -s http://127.0.0.1:8011/health                # needs no token
```

---

Next: [security](security.md) · [connecting an agent](connecting.md)
