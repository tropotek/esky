import pytest

from esky.db.connection import open_db
from esky.db.schema import SCHEMA_VERSION, migrate


@pytest.fixture
def conn(tmp_path):
    c = open_db(tmp_path / "t.db")
    migrate(c)
    yield c
    c.close()


def test_sqlite_vec_extension_loads(conn):
    (version,) = conn.execute("SELECT vec_version()").fetchone()
    assert version


def test_tables_exist(conn):
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    assert {"facts", "facts_fts", "facts_vec", "meta"} <= names


def test_vec_table_accepts_384_dims(conn):
    import sqlite_vec
    conn.execute("INSERT INTO facts_vec(fact_id, embedding) VALUES (?, ?)",
                 (1, sqlite_vec.serialize_float32([0.1] * 384)))
    assert conn.execute("SELECT count(*) FROM facts_vec").fetchone()[0] == 1


def test_vec_table_rejects_wrong_dims(conn):
    import sqlite_vec
    with pytest.raises(Exception):
        conn.execute("INSERT INTO facts_vec(fact_id, embedding) VALUES (?, ?)",
                     (2, sqlite_vec.serialize_float32([0.1] * 128)))


def test_migrate_is_idempotent(conn):
    migrate(conn)
    migrate(conn)
    assert conn.execute("SELECT value FROM meta WHERE key='schema_version'"
                        ).fetchone()[0] == str(SCHEMA_VERSION)


def test_wal_mode_enabled(conn):
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_v1_database_gains_a_title_column_and_rebuilt_fts(tmp_path):
    """A profile written before v2 must migrate in place: the column appears,
    the FTS table is rebuilt with it, and live rows are back in the index."""
    import sqlite_vec

    from esky.db.schema import _V1

    c = open_db(tmp_path / "old.db")
    c.executescript(_V1)
    c.execute("INSERT INTO meta(key, value) VALUES('schema_version', '1')")
    c.execute(
        "INSERT INTO facts(uid, text, kind, tags, source, created_at, updated_at) "
        "VALUES ('u1', 'the server listens on 8080', 'project', '[\"infra\"]', "
        "'human', 'now', 'now')")
    c.execute("INSERT INTO facts_fts(rowid, text, tags) "
              "VALUES (1, 'the server listens on 8080', 'infra')")
    c.execute("INSERT INTO facts_vec(fact_id, embedding) VALUES (?, ?)",
              (1, sqlite_vec.serialize_float32([0.1] * 384)))
    c.commit()

    migrate(c)

    assert "title" in {r[1] for r in c.execute("PRAGMA table_info(facts)")}
    assert "title" in {r[1] for r in c.execute("PRAGMA table_info(facts_fts)")}
    assert c.execute("SELECT count(*) FROM facts_fts WHERE facts_fts "
                     "MATCH '\"8080\"'").fetchone()[0] == 1
    assert c.execute("SELECT count(*) FROM facts_vec").fetchone()[0] == 1
    c.close()
