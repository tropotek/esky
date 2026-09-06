import hashlib
import hmac
import secrets
import sqlite3
from datetime import UTC, datetime

TOKEN_PREFIX = "aimem_"

UNAUTHORIZED_BODY = {"error": "unauthorized"}

META_TOKEN_HASH = "token_hash"
META_TOKEN_ISSUED_AT = "token_issued_at"


def generate_token() -> str:
    """A 256-bit token from the OS CSPRNG, with a recognisable prefix.

    The prefix makes the string greppable in config files and identifiable if
    it turns up somewhere it should not. The profile name is deliberately not
    encoded in it: the server already knows the profile from the URL path, so
    the token needs to carry no information at all.
    """
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 hexdigest of a token.

    Not bcrypt or argon2, deliberately. Those defend low-entropy human-chosen
    passwords against offline dictionary search. These are 256-bit random
    strings: there is no dictionary and no feasible search, so a slow KDF
    would add latency to every request against an attack that cannot happen.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(presented: str | None, stored_hash: str | None) -> bool:
    """Timing-safe comparison. A missing token or an un-issued profile is a
    plain False — callers must not distinguish the two."""
    if not presented or not stored_hash:
        return False
    return hmac.compare_digest(hash_token(presented), stored_hash)


def extract_bearer(header: str | None) -> str | None:
    """Pull the token out of an `Authorization: Bearer <token>` header."""
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return value.strip() or None


def _read_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _write_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def read_token_hash(conn: sqlite3.Connection) -> str | None:
    return _read_meta(conn, META_TOKEN_HASH)


def token_issued_at(conn: sqlite3.Connection) -> str | None:
    return _read_meta(conn, META_TOKEN_ISSUED_AT)


def issue_token(conn: sqlite3.Connection) -> str:
    """Generate a token for this profile and store its hash.

    Any previously issued token stops working immediately — rotation is
    reissue. Returns the plaintext, which is the only time it exists outside
    the caller's hands.

    The token lives in the database it protects: the profile *is* the file, so
    backing it up carries the token and `rm work.db` revokes access. Only the
    hash is stored, so a stolen database file yields no usable token.
    """
    token = generate_token()
    _write_meta(conn, META_TOKEN_HASH, hash_token(token))
    _write_meta(conn, META_TOKEN_ISSUED_AT, datetime.now(UTC).isoformat())
    return token


def authorize(registry, profile: str, auth_header: str | None) -> bool:
    """May this Authorization header act on this profile?

    Returns a plain bool for every failure mode — absent header, wrong scheme,
    wrong profile's token, profile with no token issued, profile that does not
    exist. Callers must render all of them as the same 401, otherwise the
    response becomes an oracle for which profiles exist.
    """
    if not registry.exists_safe(profile):
        return False
    presented = extract_bearer(auth_header)
    if not presented:
        return False
    conn = registry.connect(profile)
    try:
        return verify_token(presented, read_token_hash(conn))
    finally:
        conn.close()


def header_value(scope, name: str) -> str | None:
    """Read one header out of a raw ASGI scope."""
    wanted = name.lower().encode("latin-1")
    for key, value in scope.get("headers", []):
        if key.lower() == wanted:
            return value.decode("latin-1")
    return None
