import pytest

from ai_mem.config import EMBED_DIM
from ai_mem.embedding import Embedder


@pytest.fixture(scope="module")
def embedder():
    return Embedder("BAAI/bge-small-en-v1.5")


def test_dim_matches_config(embedder):
    assert embedder.dim == EMBED_DIM


def test_encode_returns_one_vector_per_text(embedder):
    vecs = embedder.encode(["hello world", "goodbye"])
    assert len(vecs) == 2
    assert all(len(v) == EMBED_DIM for v in vecs)


def test_encode_empty_list_returns_empty(embedder):
    assert embedder.encode([]) == []


def test_similar_texts_score_closer_than_unrelated(embedder):
    a, b, c = embedder.encode([
        "the deployment pipeline uses docker compose",
        "we ship with docker compose",
        "the cat sat on the mat",
    ])

    def dot(x, y):
        return sum(i * j for i, j in zip(x, y))

    assert dot(a, b) > dot(a, c)
