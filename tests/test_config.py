from pathlib import Path

from ai_mem.config import EMBED_DIM, load_settings


def test_embed_dim_is_384():
    assert EMBED_DIM == 384


def test_defaults_when_env_absent(monkeypatch):
    for key in ("AI_MEM_DATA_DIR", "AI_MEM_EMBED_MODEL", "AI_MEM_RRF_K",
                "AI_MEM_HOST", "AI_MEM_PORT"):
        monkeypatch.delenv(key, raising=False)
    s = load_settings()
    assert s.data_dir == Path("/data")
    assert s.embed_model == "BAAI/bge-small-en-v1.5"
    assert s.rrf_k == 60
    assert s.port == 8080


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_MEM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AI_MEM_RRF_K", "10")
    s = load_settings()
    assert s.data_dir == tmp_path
    assert s.rrf_k == 10
