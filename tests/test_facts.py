import pytest

from ai_mem.facts import FactNotFound, FactsRepo, InvalidKind


@pytest.fixture
def repo(conn, embedder):
    return FactsRepo(conn, embedder)


def test_write_returns_fact_with_uid(repo):
    f = repo.write("prefers tabs", "preference", ["style"])
    assert f.uid
    assert f.text == "prefers tabs"
    assert f.tags == ["style"]
    assert f.source == "human"
    assert f.retired_at is None


def test_write_rejects_unknown_kind(repo):
    with pytest.raises(InvalidKind):
        repo.write("x", "nonsense", [])


def test_write_populates_both_indexes(repo, conn):
    repo.write("docker compose deployment", "project", [])
    assert conn.execute("SELECT count(*) FROM facts_fts").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM facts_vec").fetchone()[0] == 1


def test_get_roundtrips(repo):
    written = repo.write("a durable fact", "reference", ["a", "b"])
    assert repo.get(written.uid).text == "a durable fact"


def test_get_missing_returns_none(repo):
    assert repo.get("nope") is None


def test_update_text_supersedes_and_reindexes(repo, conn):
    original = repo.write("port is 8080", "project", [])
    updated = repo.update(original.uid, text="port is 9090")
    assert updated.uid != original.uid
    assert updated.supersedes == original.uid
    assert repo.get(original.uid).retired_at is not None
    rows = [r[0] for r in conn.execute("SELECT text FROM facts_fts")]
    assert rows == ["port is 9090"]


def test_update_tags_only_keeps_same_uid(repo):
    original = repo.write("port is 8080", "project", ["net"])
    updated = repo.update(original.uid, tags=["net", "infra"])
    assert updated.uid == original.uid
    assert updated.tags == ["net", "infra"]


def test_update_missing_raises(repo):
    with pytest.raises(FactNotFound):
        repo.update("nope", text="x")


def test_retire_is_soft_and_deindexes(repo, conn):
    f = repo.write("temporary", "project", [])
    repo.retire(f.uid)
    assert repo.get(f.uid).retired_at is not None
    assert conn.execute("SELECT count(*) FROM facts").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM facts_fts").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM facts_vec").fetchone()[0] == 0


def test_retire_missing_raises(repo):
    with pytest.raises(FactNotFound):
        repo.retire("nope")


def test_recent_excludes_retired_and_orders_newest_first(repo):
    a = repo.write("first", "project", [])
    repo.write("second", "project", [])
    repo.retire(a.uid)
    assert [f.text for f in repo.recent()] == ["second"]


def test_recent_filters_by_kind(repo):
    repo.write("a pref", "preference", [])
    repo.write("a proj", "project", [])
    assert [f.text for f in repo.recent(kind="preference")] == ["a pref"]
