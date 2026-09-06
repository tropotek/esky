import os
from dataclasses import dataclass
from pathlib import Path

EMBED_DIM = 384
"""Dimension of bge-small/MiniLM-class embeddings. Must match the DDL FLOAT[384]."""


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    embed_model: str
    rrf_k: int
    host: str
    port: int


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.environ.get("AI_MEM_DATA_DIR", "/data")),
        embed_model=os.environ.get("AI_MEM_EMBED_MODEL", "BAAI/bge-small-en-v1.5"),
        rrf_k=int(os.environ.get("AI_MEM_RRF_K", "60")),
        host=os.environ.get("AI_MEM_HOST", "127.0.0.1"),
        port=int(os.environ.get("AI_MEM_PORT", "8080")),
    )
