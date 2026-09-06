from pathlib import Path

from esky.config import EMBED_DIM, load_settings


def test_embed_dim_is_384():
    assert EMBED_DIM == 384


def test_defaults_when_env_absent(monkeypatch):
    for key in ("ESKY_DATA_DIR", "ESKY_EMBED_MODEL", "ESKY_RRF_K",
                "ESKY_HOST", "ESKY_PORT"):
        monkeypatch.delenv(key, raising=False)
    s = load_settings()
    assert s.data_dir == Path("/data")
    assert s.embed_model == "BAAI/bge-small-en-v1.5"
    assert s.rrf_k == 60
    assert s.port == 8080


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("ESKY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ESKY_RRF_K", "10")
    s = load_settings()
    assert s.data_dir == tmp_path
    assert s.rrf_k == 10


def test_max_distance_default_and_override(monkeypatch):
    monkeypatch.delenv("ESKY_MAX_DISTANCE", raising=False)
    assert load_settings().max_distance == 0.9
    monkeypatch.setenv("ESKY_MAX_DISTANCE", "1.5")
    assert load_settings().max_distance == 1.5
