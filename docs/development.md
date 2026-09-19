# Development

Everything runs in Docker; no local Python environment is needed or supported.

```bash
docker compose run --rm test pytest -q          # full suite
docker compose run --rm test pytest tests/test_search.py -v
```

Source is bind-mounted into the dev container, so edits apply without
rebuilding. Rebuild only when dependencies change:

```bash
docker compose build test
```

The `esky` service runs the **baked image**, not the source tree — only `./data`
is mounted. Code changes need a rebuild before they take effect there:

```bash
docker compose build esky && docker compose up -d esky
```

Tests run against SQLite files under `ESKY_DATA_DIR=/tmp/esky-data` in the
container, never `./data`.

Design documents live in `_notes/docs/` and are gitignored. This `docs/` folder
is the user-facing documentation and is tracked.

---

Next: [tools](tools.md) · [security](security.md)
