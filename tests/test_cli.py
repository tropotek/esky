import pytest

from ai_mem.cli import main


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_MEM_DATA_DIR", str(tmp_path))
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


from ai_mem.auth import TOKEN_PREFIX


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
