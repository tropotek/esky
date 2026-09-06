import pytest

from ai_mem.config import EMBED_DIM
from ai_mem.db.connection import open_db
from ai_mem.db.schema import migrate


class FakeEmbedder:
    """Deterministic stand-in: hashes tokens into a fixed-width bag of words.

    Real embeddings make retrieval tests slow and non-deterministic. The search
    tests assert ranking behaviour, which only needs 'similar text -> similar
    vector', and this provides that reproducibly (with PYTHONHASHSEED=0, set in
    compose.yml).
    """

    dim = EMBED_DIM

    def encode(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * EMBED_DIM
            for token in t.lower().split():
                v[hash(token) % EMBED_DIM] += 1.0
            norm = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / norm for x in v])
        return out


@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest.fixture
def conn(tmp_path):
    c = open_db(tmp_path / "test.db")
    migrate(c)
    yield c
    c.close()
