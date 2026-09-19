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

## Traffic is not encrypted

Esky speaks plain HTTP and that is deliberate. It generates no certificates and
terminates no TLS, because on a network you own there is nothing between the
client and the server, and every install that needs more than that already runs
a reverse proxy better at it than Esky would be.

The exposure is worth naming precisely. The bearer token is sent on every
request, so anyone who can watch the wire — a compromised machine, shared
WiFi, a switch port — can copy it and use it. The query log records searches,
not authentications, so a stolen token is used invisibly. The token is the
thing worth stealing, not any single fact, because it keeps working.

**This is built for a network you control.** Keep `ESKY_BIND` on a LAN address
and firewall the port to your own subnet, and that is the end of it.

### If you want HTTPS

Put a reverse proxy in front. It owns the certificate, its renewal and its
private key; Esky needs no configuration for it and no code in it. With Caddy
that is one block:

```caddyfile
esky.example.com {
    reverse_proxy 192.168.1.10:8011
}
```

Then bind Esky where only the proxy can reach it, and point clients at the
proxy's `https://` URL instead — see
[connecting through a proxy](connecting.md#through-a-reverse-proxy).

Two things to get right, whichever proxy you use:

- **Do not leave the plain port published as well.** A server reachable both
  ways lets a client that never got the new URL keep sending its token in
  cleartext, working perfectly and protecting nothing.
- **Forward the `Authorization` header.** Caddy and nginx both do by default,
  but a proxy that strips it turns every request into an identical 401, which
  reads exactly like a bad token.

### Reaching it from outside your network

The best answer is usually not to publish it. WireGuard or Tailscale puts the
remote machine on your private network, and Esky keeps talking plain HTTP to a
private address — nothing to expose, nothing to renew.

If it must be genuinely public, the proxy above is the minimum and not the
whole job. Tokens have no expiry and no audit trail, `/health` answers without
one, and a profile database in a backup is a live credential. None of that
matters on a LAN. All of it matters on the internet.

## Backups

The token lives inside the file it protects. A profile database is therefore
both the memory and the credential — back it up somewhere you would be willing
to keep a password, and remember that restoring an old copy restores the token
that came with it.

---

Next: [operations](operations.md) · [connecting an agent](connecting.md)
