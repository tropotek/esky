import pytest

from esky.facts import FactsRepo
from esky.search import _vector_ranking, hybrid_search, hybrid_search_detailed


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


# --- exact-ID step --------------------------------------------------------
# A bare ticket number carries no meaning for the embedder, and FTS splits
# `sc-3469` into `sc` OR `3469`, so a common prefix drowns the rare number.


@pytest.fixture
def tickets(conn, embedder):
    repo = FactsRepo(conn, embedder)
    for i in range(6):
        repo.write(f"sc-10{i} admin tiers map to the sc catalogue", "project", [])
    wanted = repo.write("login redirect times out on SSO", "project",
                        ["sc-3469"])
    in_text = repo.write("fixed in PR #123 for the importer", "project", [])
    near = repo.write("older follow-up in #1234 about caching", "project", [])
    return conn, embedder, wanted, in_text, near


def test_ticket_id_in_tags_ranks_first(tickets):
    conn, emb, wanted, *_ = tickets
    assert hybrid_search(conn, emb, "sc-3469")[0].uid == wanted.uid


def test_ticket_id_in_text_ranks_first(conn, embedder):
    repo = FactsRepo(conn, embedder)
    for i in range(6):
        repo.write(f"sc-10{i} admin tiers map to the sc catalogue", "project", [])
    wanted = repo.write("sc-3469 login redirect times out", "project", [])
    assert hybrid_search(conn, embedder, "sc-3469")[0].uid == wanted.uid


def test_ticket_id_match_is_case_insensitive(tickets):
    conn, emb, wanted, *_ = tickets
    assert hybrid_search(conn, emb, "SC-3469")[0].uid == wanted.uid


def test_hash_number_matches_literally(tickets):
    conn, emb, _, in_text, _ = tickets
    assert hybrid_search(conn, emb, "#123")[0].uid == in_text.uid


def test_hash_number_does_not_match_a_longer_number(tickets):
    conn, emb, _, in_text, near = tickets
    result = hybrid_search_detailed(conn, emb, "#123")
    assert result.exact_count == 1
    assert result.hits[0].uid == in_text.uid


def test_ticket_id_does_not_match_a_longer_number(conn, embedder):
    FactsRepo(conn, embedder).write("sc-34690 something else", "project", [])
    assert hybrid_search_detailed(conn, embedder, "sc-3469").exact_count == 0


def test_a_uid_resolves_to_its_fact(conn, embedder):
    repo = FactsRepo(conn, embedder)
    repo.write("unrelated filler fact", "project", [])
    wanted = repo.write("the one we want", "project", [])
    hits = hybrid_search(conn, embedder, wanted.uid)
    assert hits[0].uid == wanted.uid


def test_no_exact_match_falls_through_to_the_normal_search(seeded):
    conn, emb = seeded
    result = hybrid_search_detailed(conn, emb, "docker compose sc-9999")
    assert result.exact_count == 0
    assert result.hits[0].text.startswith("the deployment uses docker compose")


def test_exact_matches_respect_the_tag_filter(conn, embedder):
    repo = FactsRepo(conn, embedder)
    repo.write("sc-3469 in the work store", "project", ["work"])
    repo.write("sc-3469 in the home store", "project", ["home"])
    hits = hybrid_search(conn, embedder, "sc-3469", tags=["home"])
    assert [h.text for h in hits] == ["sc-3469 in the home store"]


def test_retired_facts_are_not_exact_matches(conn, embedder):
    repo = FactsRepo(conn, embedder)
    old = repo.write("sc-3469 old understanding", "project", [])
    repo.retire(old.uid)
    assert hybrid_search_detailed(conn, embedder, "sc-3469").exact_count == 0


def test_detailed_result_reports_the_top_vector_distance(conn, embedder):
    """Terse fact: FakeEmbedder is a bag of words, so a long one falls past the
    distance floor for reasons unrelated to what is under test."""
    FactsRepo(conn, embedder).write("docker compose", "project", [])
    result = hybrid_search_detailed(conn, embedder, "docker compose")
    assert result.top_distance is not None
    assert result.top_distance <= 0.9


def test_detailed_result_has_no_distance_for_a_miss(seeded):
    conn, emb = seeded
    result = hybrid_search_detailed(conn, emb, "zzzznonexistenttoken")
    assert result.hits == []
    assert result.top_distance is None
