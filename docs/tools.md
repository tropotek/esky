# Tools and facts

What an agent can do with the store. Five tools, deliberately — every tool
description costs context in every session, so the list stays short.

## The five tools

| Tool | Purpose |
|---|---|
| `memory_search` | Hybrid BM25 + vector search over curated facts |
| `memory_write` | Record a durable fact |
| `memory_update` | Amend a fact; a text change supersedes rather than overwrites |
| `memory_forget` | Retire a fact — soft, never destroyed |
| `memory_recent` | Recently written or updated facts |

Nothing is ever hard-deleted. `memory_forget` marks a fact retired and
`memory_update` supersedes it under a new id, so the record of what was once
believed survives the correction.

## Fact kinds

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

---

Next: [operations — CLI, configuration, tokens](operations.md) ·
[how isolation is enforced](security.md)
