import pytest

from esky.facts import FactsRepo
from esky.search import _vector_ranking, hybrid_search


@pytest.fixture
def seeded(conn, embedder):
    repo = FactsRepo(conn, embedder)
    repo.write("the deployment uses docker compose on the LAN", "project", ["infra"])
    repo.write("prefers tabs over spaces in PHP", "preference", ["style"])
    repo.write("the wiki runs on the ttek stack", "project", ["infra"])
    retired = repo.write("deployment used to use kubernetes", "project", ["infra"])
    repo.retire(retired.uid)
    return conn, embedder


def test_lexical_match_is_found(seeded):
    conn, emb = seeded
    hits = hybrid_search(conn, emb, "docker compose")
    assert hits[0].text.startswith("the deployment uses docker compose")


def test_retired_facts_never_returned(seeded):
    conn, emb = seeded
    assert all("kubernetes" not in h.text for h in hybrid_search(conn, emb, "kubernetes"))


def test_limit_is_respected(seeded):
    conn, emb = seeded
    assert len(hybrid_search(conn, emb, "docker compose tabs spaces", limit=2)) <= 2


def test_tag_filter_narrows_results(seeded):
    conn, emb = seeded
    query = "docker compose tabs spaces"
    unfiltered = {h.kind for h in hybrid_search(conn, emb, query)}
    assert {"project", "preference"} <= unfiltered

    hits = hybrid_search(conn, emb, query, tags=["style"])
    assert [h.kind for h in hits] == ["preference"]


def test_hits_are_labelled_with_layer(seeded):
    conn, emb = seeded
    assert all(h.layer == "facts" for h in hybrid_search(conn, emb, "docker"))


def test_hits_carry_updated_at(seeded):
    conn, emb = seeded
    hits = hybrid_search(conn, emb, "docker")
    assert hits
    assert all(h.updated_at for h in hits)


def test_scores_descend(seeded):
    conn, emb = seeded
    scores = [h.score for h in hybrid_search(conn, emb, "deployment infra")]
    assert scores == sorted(scores, reverse=True)


def test_empty_database_returns_empty(conn, embedder):
    assert hybrid_search(conn, embedder, "anything") == []


def test_query_matching_nothing_returns_empty(seeded):
    conn, emb = seeded
    assert hybrid_search(conn, emb, "zzzznonexistenttoken") == []


def test_punctuation_in_query_does_not_raise(seeded):
    conn, emb = seeded
    hybrid_search(conn, emb, 'what about "docker" AND (compose)?')


def test_vector_cutoff_excludes_unrelated_matches(seeded):
    conn, emb = seeded
    # Orthogonal to everything seeded, so beyond the default relevance floor.
    assert hybrid_search(conn, emb, "zzzznonexistenttoken") == []


def test_raising_max_distance_readmits_them(seeded):
    conn, emb = seeded
    assert hybrid_search(conn, emb, "zzzznonexistenttoken", max_distance=2.0)


def test_title_words_are_searchable(conn, embedder):
    repo = FactsRepo(conn, embedder)
    repo.write("it listens on 8080", "project", [], title="server port")
    hits = hybrid_search(conn, embedder, "server port")
    assert [h.title for h in hits] == ["server port"]


def test_hits_carry_a_null_title_when_unset(seeded):
    conn, emb = seeded
    assert all(h.title is None for h in hybrid_search(conn, emb, "docker compose"))


def test_title_is_visible_to_vector_search(conn, embedder):
    """A title carries topic words the text does not. Semantic search must see
    them, or a fact is only findable by the half of its content that is indexed.

    Kept terse because FakeEmbedder is a bag of words: every token the query
    does not share dilutes the match, so a long body would fall past the
    distance floor for reasons that have nothing to do with the title.
    """
    repo = FactsRepo(conn, embedder)
    repo.write("port 8080", "project", [], title="webserver harbour")
    assert _vector_ranking(conn, embedder, "webserver harbour", 10, 0.9)


def test_tag_filter_does_not_starve_the_result_set(conn, embedder):
    """Tags must narrow the rankings, not the already-truncated pool: a tagged
    fact that ranks outside the pool is still a tagged fact.
    """
    repo = FactsRepo(conn, embedder)
    for i in range(24):
        repo.write(f"alpha beta gamma delta record {i}", "project", ["bulk"])
    for i in range(2):
        repo.write(f"alpha {i} " + " ".join(f"filler{j}" for j in range(40)),
                   "project", ["wanted"])

    hits = hybrid_search(conn, embedder, "alpha", limit=2, tags=["wanted"])
    assert len(hits) == 2
