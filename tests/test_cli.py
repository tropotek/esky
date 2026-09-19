import pytest

from conftest import FakeEmbedder
from esky.cli import main
from esky.facts import FactsRepo
from esky.profiles import ProfileRegistry


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ESKY_DATA_DIR", str(tmp_path))
    return tmp_path


def test_profile_create_makes_a_database(data_dir):
    assert main(["profile", "create", "work"]) == 0
    assert (data_dir / "work.db").exists()


def test_profile_list_shows_created(data_dir, capsys):
    main(["profile", "create", "work"])
    capsys.readouterr()
    main(["profile", "list"])
    assert "work" in capsys.readouterr().out


def test_profile_create_rejects_bad_name(data_dir):
    assert main(["profile", "create", "../etc"]) == 2
    assert list(data_dir.glob("*.db")) == []


def test_profile_without_subcommand_returns_error():
    assert main(["profile"]) == 2


def test_no_command_returns_error():
    assert main([]) == 2


from esky.auth import TOKEN_PREFIX


def test_token_issue_prints_a_token_once(data_dir, capsys):
    main(["profile", "create", "work"])
    capsys.readouterr()
    assert main(["token", "issue", "work"]) == 0
    out = capsys.readouterr().out
    assert TOKEN_PREFIX in out


def test_token_issue_on_unknown_profile_errors(data_dir):
    assert main(["token", "issue", "nope"]) == 2


def test_token_issue_on_invalid_name_errors(data_dir):
    assert main(["token", "issue", "../etc"]) == 2


def test_token_status_reports_absence_then_presence(data_dir, capsys):
    main(["profile", "create", "work"])
    capsys.readouterr()

    main(["token", "status", "work"])
    assert "no token" in capsys.readouterr().out.lower()

    main(["token", "issue", "work"])
    capsys.readouterr()
    main(["token", "status", "work"])
    assert "issued" in capsys.readouterr().out.lower()


def test_token_status_never_prints_the_token(data_dir, capsys):
    main(["profile", "create", "work"])
    main(["token", "issue", "work"])
    token = [w for w in capsys.readouterr().out.split()
             if w.startswith(TOKEN_PREFIX)][0]
    main(["token", "status", "work"])
    assert token not in capsys.readouterr().out


def test_token_without_subcommand_returns_error():
    assert main(["token"]) == 2


def test_profile_migrate_brings_an_old_database_up_to_date(data_dir, capsys):
    """connect() does not migrate, so a profile created before a schema bump
    needs an explicit way up."""
    from esky.db.connection import open_db
    from esky.db.schema import _V1, SCHEMA_VERSION

    c = open_db(data_dir / "old.db")
    c.executescript(_V1)
    c.execute("INSERT INTO meta(key, value) VALUES('schema_version', '1')")
    c.commit()
    c.close()

    assert main(["profile", "migrate", "old"]) == 0
    c = open_db(data_dir / "old.db")
    assert c.execute("SELECT value FROM meta WHERE key='schema_version'"
                     ).fetchone()[0] == str(SCHEMA_VERSION)
    c.close()
    assert "old" in capsys.readouterr().out


def test_profile_migrate_on_unknown_profile_errors(data_dir):
    assert main(["profile", "migrate", "nope"]) == 2


def test_reindex_reports_how_many_facts_were_done(data_dir, monkeypatch, capsys):
    """The real model is never loaded in tests, so the CLI's embedder is
    swapped for the deterministic fake."""
    monkeypatch.setattr("esky.cli.Embedder", lambda name: FakeEmbedder())
    main(["profile", "create", "work"])
    conn = ProfileRegistry(data_dir).connect("work")
    FactsRepo(conn, FakeEmbedder()).write("a fact", "project", [])
    conn.close()

    assert main(["profile", "reindex", "work"]) == 0
    assert "1" in capsys.readouterr().out


def test_reindex_rejects_an_unknown_profile(data_dir, monkeypatch):
    monkeypatch.setattr("esky.cli.Embedder", lambda name: FakeEmbedder())
    assert main(["profile", "reindex", "nope"]) == 2
