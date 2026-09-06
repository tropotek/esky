import pytest

from ai_mem.profiles import InvalidProfileName, ProfileRegistry, UnknownProfile


@pytest.fixture
def registry(tmp_path):
    return ProfileRegistry(tmp_path)


def test_unknown_profile_raises(registry):
    with pytest.raises(UnknownProfile):
        registry.connect("work")


def test_connect_never_creates_a_file(registry, tmp_path):
    with pytest.raises(UnknownProfile):
        registry.connect("wrok")
    assert list(tmp_path.iterdir()) == []


def test_create_then_connect(registry):
    registry.create("work")
    conn = registry.connect("work")
    assert conn.execute("SELECT count(*) FROM facts").fetchone()[0] == 0


def test_list_returns_created_profiles(registry):
    registry.create("work")
    registry.create("personal")
    assert registry.list() == ["personal", "work"]


def test_create_is_idempotent(registry):
    registry.create("work")
    registry.create("work")
    assert registry.list() == ["work"]


@pytest.mark.parametrize("name", ["../etc", "a/b", "", "Work!", "x" * 65, "."])
def test_rejects_unsafe_names(registry, name):
    with pytest.raises(InvalidProfileName):
        registry.create(name)


def test_exists_safe_returns_false_for_invalid_names(registry):
    assert registry.exists_safe("../etc") is False
