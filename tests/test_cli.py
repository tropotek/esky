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
