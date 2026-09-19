# Connecting an agent

Registering the server is half the setup. The other half is telling your agent
to use it — see [Tell your agent to use it](#tell-your-agent-to-use-it) below,
without which the store is written to but never read from.

These examples use `personal` as the profile and `$TOKEN` as its bearer token.
See [Set up a profile](../README.md#set-up-a-profile) for both.

## Same machine

Claude Code registers a server from the command line:

```bash
claude mcp add -s user --transport http esky \
  http://127.0.0.1:8011/mcp/personal \
  --header "Authorization: Bearer $TOKEN"
```

`-s user` registers it in your user config so it is available in every
project. Drop it to add the server to the current project only.

`esky` there is just the local alias for the server — call it anything you
prefer. It shows up in `/mcp`; the tool names (`memory_search` and friends)
are fixed either way. Keeping the same alias on every machine saves
reconciling two names for one server later.

**If you have already set `ESKY_BIND` to a LAN address, use that address
here too, not `127.0.0.1`.** Docker publishes the port on one interface only,
so binding to `192.168.1.10` makes loopback unreachable — a local client gets a
connection refused that looks nothing like a config error.

Other clients take the same three values — URL, header, alias — from a JSON
config file instead; see [Other MCP clients](#other-mcp-clients).

The server is only picked up by **new** sessions. Restart the client, then
confirm it is connected (`/mcp` in Claude Code).

## From another machine on the LAN

First expose the port on the host. In `.env` on the **server**:

```ini
ESKY_BIND=192.168.1.10    # the server's LAN address
```

```bash
docker compose up -d
```

If the host runs a firewall, allow the port from your subnet only:

```bash
sudo ufw allow from 192.168.1.0/24 to any port 8011 proto tcp
```

From the **client** machine, verify reachability before involving an agent:

```bash
curl -m 5 -H "Authorization: Bearer $TOKEN" \
  http://192.168.1.10:8011/api/profiles
```

Once that returns your profile, add the server:

```bash
claude mcp add -s user --transport http esky \
  http://192.168.1.10:8011/mcp/personal \
  --header "Authorization: Bearer $TOKEN"
```

Start a new session — `esky` should show as connected, with five tools. Test
it with *"search your memory for X"*, or *"remember that I prefer X"*.

## Tell your agent to use it

**A connected server that nobody calls looks exactly like a broken one.**
Phase 1 gives an agent tools, not reflexes: it searches memory when you ask, or
when its instructions tell it to, and otherwise records facts it will never
read back. Automatic recall at session start is Phase 2.

Until then, put this in whichever file your client loads as standing
instructions, at the **global** level so it applies in every project and not
just the one you set the server up in:

```markdown
## Memory

Before assuming anything about how I work, what a project uses, or why a past
decision was made, call `memory_search`. When you learn something durable that
would be useful in a future session, call `memory_write`.

Durable means it outlives this conversation. Do not write transient task state,
or anything the repository already records.
```

The last paragraph matters as much as the first. Without it an agent writes
down what it did this afternoon, and a store full of session narration is worth
less than an empty one — you stop trusting what comes out of it.

Where that file lives depends on the client:

| Client | Global instruction file |
|---|---|
| Claude Code | `~/.claude/CLAUDE.md` |
| opencode | `~/.config/opencode/AGENTS.md`, falling back to `~/.claude/CLAUDE.md` if that does not exist |
| Codex | `AGENTS.md`, in the repository or in its config directory |
| Anything else | its own standing-instructions file, or the system prompt |

The wording is not special; what matters is that something instructs the agent
to search before assuming and write when it learns.

Do this on **every machine** that connects. The instruction lives on the client,
not on the server, so a second machine is silent until it gets its own copy. If
you run more than one config directory for the same client (a separate work
profile, say), each has its own file and each needs the snippet.

## Through a reverse proxy

If you have put a proxy in front for HTTPS (see
[traffic is not encrypted](security.md#traffic-is-not-encrypted)), nothing
changes except the URL — the profile path and the header are the same:

```bash
claude mcp add -s user --transport http esky \
  https://esky.example.com/mcp/personal \
  --header "Authorization: Bearer $TOKEN"
```

Check it from the client the same way, before involving an agent:

```bash
curl -m 5 -H "Authorization: Bearer $TOKEN" \
  https://esky.example.com/api/profiles
```

A `401` here when the same token works against the plain address means the
proxy is dropping the `Authorization` header, not that the token is wrong.

This only works with a certificate your client already trusts, which is what
Caddy's automatic issuance gives you. A self-signed certificate is rejected by
default and every client machine has to be told to trust it separately — if you
are reaching for one of those, a private network like Tailscale is less work
and ends up more secure.

## Multiple accounts or machines

Give each its own profile and token:

```bash
docker compose exec esky esky profile create work
docker compose exec esky esky token issue work
```

Point that client at `/mcp/work`. Two accounts on one machine, or a laptop and
a desktop, can share a profile by sharing its token, or stay
separate by having their own. The server enforces the boundary; the agent
cannot cross it by asking.

## Other MCP clients

Any client that speaks MCP streamable HTTP with a custom header works. The
endpoint is `http://<host>:<port>/mcp/<profile>` and the header is
`Authorization: Bearer <token>`. For clients configured by JSON:

```json
{
  "mcpServers": {
    "esky": {
      "type": "http",
      "url": "http://192.168.1.10:8011/mcp/personal",
      "headers": { "Authorization": "Bearer esky_..." }
    }
  }
}
```

---

Next: [the five tools and what a fact looks like](tools.md) ·
[troubleshooting a connection](operations.md#troubleshooting)
