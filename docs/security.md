# Security

Every profile is gated by its own bearer token. A token grants **exactly one
profile** — a leaked `work` token cannot read `personal`, and revoking one
profile leaves the others alone.

The server **fails closed**: a profile with no token issued rejects every
request. There is no anonymous mode and no localhost exemption.

Only a SHA-256 hash is stored, in the profile's own database. Backing up
`work.db` carries its token; `rm work.db` revokes it. Rotation is reissue —
there is no grace period, the old token stops working immediately. See
[rotating a token](operations.md#rotating-a-token).

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

## Backups

The token lives inside the file it protects. A profile database is therefore
both the memory and the credential — back it up somewhere you would be willing
to keep a password, and remember that restoring an old copy restores the token
that came with it.

---

Next: [operations](operations.md) · [connecting an agent](connecting.md)
