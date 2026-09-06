from esky.auth import (
    TOKEN_PREFIX, extract_bearer, generate_token, hash_token, verify_token,
)


def test_generated_token_has_prefix_and_entropy():
    token = generate_token()
    assert token.startswith(TOKEN_PREFIX)
    assert len(token) == len(TOKEN_PREFIX) + 43


def test_generated_tokens_are_unique():
    assert len({generate_token() for _ in range(100)}) == 100


def test_hash_is_deterministic_and_not_the_token():
    token = generate_token()
    assert hash_token(token) == hash_token(token)
    assert token not in hash_token(token)
    assert len(hash_token(token)) == 64


def test_verify_accepts_matching_token():
    token = generate_token()
    assert verify_token(token, hash_token(token)) is True


def test_verify_rejects_wrong_token():
    assert verify_token(generate_token(), hash_token(generate_token())) is False


def test_verify_rejects_missing_inputs():
    token = generate_token()
    assert verify_token(None, hash_token(token)) is False
    assert verify_token("", hash_token(token)) is False
    assert verify_token(token, None) is False
    assert verify_token(None, None) is False


def test_extract_bearer_reads_the_scheme_case_insensitively():
    assert extract_bearer("Bearer abc123") == "abc123"
    assert extract_bearer("bearer abc123") == "abc123"
    assert extract_bearer("BEARER abc123") == "abc123"


def test_extract_bearer_rejects_other_schemes_and_junk():
    assert extract_bearer(None) is None
    assert extract_bearer("") is None
    assert extract_bearer("Basic abc123") is None
    assert extract_bearer("Bearer") is None
    assert extract_bearer("Bearer   ") is None
    assert extract_bearer("abc123") is None


from esky.auth import issue_token, read_token_hash, token_issued_at


def test_no_token_issued_reads_as_none(conn):
    assert read_token_hash(conn) is None
    assert token_issued_at(conn) is None


def test_issue_returns_plaintext_and_stores_only_the_hash(conn):
    token = issue_token(conn)
    assert token.startswith(TOKEN_PREFIX)

    stored = read_token_hash(conn)
    assert stored == hash_token(token)

    dump = " ".join(str(r) for r in conn.execute("SELECT key, value FROM meta"))
    assert token not in dump


def test_issue_records_a_timestamp(conn):
    issue_token(conn)
    assert token_issued_at(conn) is not None


def test_reissue_invalidates_the_previous_token(conn):
    first = issue_token(conn)
    second = issue_token(conn)
    assert first != second
    assert verify_token(first, read_token_hash(conn)) is False
    assert verify_token(second, read_token_hash(conn)) is True
