# Esky 🧊

*A cold box for your agents' memory. Self-hosted, on your own network.*

Esky is a self-hosted MCP memory server for the local network. Any MCP-speaking
agent — Claude Code, Codex, the OpenAI Agents SDK — can read and write durable
memory over HTTP, with each context kept in its own database.

Agents start every session cold. Esky is the box on the network they all
reach into: put a fact in from the laptop, take it out from the desktop, and
it is still there next week.

Nothing leaves your network. Embeddings run in-process on ONNX; there is no
API key and no outbound call.

## Documentation

| Guide | Covers |
|---|---|
| [Connecting an agent](connecting.md) | Same machine and across the LAN, the standing instruction that makes memory get used, multiple profiles, other MCP clients |
| [Tools and facts](tools.md) | The five tools, fact kinds, the query log |
| [Operations](operations.md) | CLI, configuration, rotating a token, troubleshooting |
| [Security](security.md) | The token model, why unknown profiles return 401, HTTPS via a reverse proxy, backups |
| [Development](development.md) | Running the tests, rebuilding the containers |

Installing for the first time? Start with the [README on GitHub](https://github.com/tropotek/esky#readme).
