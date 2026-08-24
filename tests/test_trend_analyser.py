"""Topic recommendations must be fresh, diverse, and fail loudly.

The regression this file exists for: the previous recommender passed
already-used topics to the LLM as a soft "don't pick these" instruction. The
model complied literally and returned *reworded* versions of the same subject,
so the library accumulated five near-identical ocean topics:

    95% of the Ocean Remains Unseen
    We Know More About Mars Than Our Ocean Floor
    We've Explored Less Than 5% of the Ocean
    We've Barely Scratched Our Own Ocean
    Deep Ocean Wonders

It also swallowed every failure and fell back to raw Google Trends headlines,
so a dead LLM surfaced "lindsay clancy trial live" as a curated recommendation.
"""
import pytest

import trend_analyser as ta

OCEAN_HISTORY = [
    "95% of the Ocean Remains Unseen",
    "We Know More About Mars Than Our Ocean Floor",
    "We've Explored Less Than 5% of the Ocean",
    "We've Barely Scratched Our Own Ocean",
    "Deep Ocean Wonders",
]


# --------------------------------------------------------------------------
# Novelty filtering
# --------------------------------------------------------------------------

@pytest.mark.parametrize("reworded", [
    "The Ocean Nobody Has Ever Seen",
    "Why Our Ocean Floor Stays Unmapped",
    "Secrets Of The Deep Ocean",
])
def test_reworded_duplicates_are_rejected(reworded):
    """Textually different, semantically identical -- the exact failure mode."""
    assert not ta.is_novel(reworded, OCEAN_HISTORY)


def test_genuinely_different_subject_is_accepted():
    assert ta.is_novel("Why Your Brain Deletes Dreams", OCEAN_HISTORY)


def test_duplicates_within_a_single_batch_are_rejected():
    """One LLM response must not contribute two topics on the same subject."""
    accepted = ["What Lives In Volcanic Vents"]
    assert not ta.is_novel("The Volcanic Vents Nobody Explores", [], accepted)


def test_empty_title_is_never_novel():
    assert not ta.is_novel("", OCEAN_HISTORY)
    assert not ta.is_novel(None, OCEAN_HISTORY)


def test_novelty_holds_with_no_history():
    assert ta.is_novel("Anything At All", [])


# --------------------------------------------------------------------------
# analyse()
# --------------------------------------------------------------------------

def _fake_ideas(titles):
    return [{"title": t, "hook": "h", "niche": "science", "rpm_tier": "High"}
            for t in titles]


def test_analyse_filters_history_before_returning(monkeypatch):
    monkeypatch.setattr(ta, "gather_signals", lambda geo: {})
    monkeypatch.setattr(ta, "generate_ideas", lambda *a, **k: _fake_ideas([
        "Secrets Of The Deep Ocean",        # duplicate of history
        "Why Volcanoes Glow Blue",          # novel
        "The Ocean We Never Mapped",        # duplicate of history
    ]))
    recs = ta.analyse(count=3, used_topics=OCEAN_HISTORY, max_attempts=1)
    titles = [r["title"] for r in recs]
    assert titles == ["Why Volcanoes Glow Blue"]


def test_analyse_deduplicates_within_the_batch(monkeypatch):
    monkeypatch.setattr(ta, "gather_signals", lambda geo: {})
    monkeypatch.setattr(ta, "generate_ideas", lambda *a, **k: _fake_ideas([
        "Why Volcanoes Glow Blue",
        "The Blue Volcanoes Of Indonesia",   # same subject as the first
        "How Bees Navigate By Light",
    ]))
    recs = ta.analyse(count=3, used_topics=[], max_attempts=1)
    titles = [r["title"] for r in recs]
    assert titles == ["Why Volcanoes Glow Blue", "How Bees Navigate By Light"]


def test_analyse_raises_instead_of_returning_raw_trends(monkeypatch):
    """The old code silently surfaced news headlines as 'recommendations'."""
    monkeypatch.setattr(ta, "gather_signals", lambda geo: {})

    def boom(*a, **k):
        raise RuntimeError("Ollama HTTP 429: quota exhausted")

    monkeypatch.setattr(ta, "generate_ideas", boom)
    with pytest.raises(RuntimeError, match="quota exhausted"):
        ta.analyse(count=3, max_attempts=2)


def test_analyse_retries_when_a_batch_is_fully_duplicated(monkeypatch):
    """A strict filter can empty a batch; asking again beats loosening it."""
    monkeypatch.setattr(ta, "gather_signals", lambda geo: {})
    calls = {"n": 0}

    def sometimes(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _fake_ideas(["Secrets Of The Deep Ocean"])   # all duplicates
        return _fake_ideas(["How Bees Navigate By Light"])

    monkeypatch.setattr(ta, "generate_ideas", sometimes)
    recs = ta.analyse(count=1, used_topics=OCEAN_HISTORY, max_attempts=3)
    assert calls["n"] == 2
    assert recs[0]["title"] == "How Bees Navigate By Light"


def test_high_rpm_topics_are_ranked_first(monkeypatch):
    monkeypatch.setattr(ta, "gather_signals", lambda geo: {})
    monkeypatch.setattr(ta, "generate_ideas", lambda *a, **k: [
        {"title": "Low One", "hook": "h", "niche": "general", "rpm_tier": "Low"},
        {"title": "High One", "hook": "h", "niche": "finance", "rpm_tier": "High"},
        {"title": "Medium One", "hook": "h", "niche": "science", "rpm_tier": "Medium"},
    ])
    recs = ta.analyse(count=3, max_attempts=1)
    assert [r["rpm_tier"] for r in recs] == ["High", "Medium", "Low"]


# --------------------------------------------------------------------------
# Signal sources
# --------------------------------------------------------------------------

def test_gather_signals_survives_every_source_failing(monkeypatch):
    """A dead source must degrade grounding, not fail the recommendation."""
    monkeypatch.setattr(ta, "fetch_wikipedia_trending",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    signals = ta.gather_signals("US")
    assert signals["wikipedia"] == []


def test_wikipedia_drops_scaffolding_pages(monkeypatch):
    """The raw list is dominated by Main_Page and Special:/Wikipedia: entries."""
    class R:
        status_code = 200
        @staticmethod
        def json():
            return {"items": [{"articles": [
                {"article": "Main_Page", "views": 9_000_000},
                {"article": "Special:Search", "views": 800_000},
                {"article": "Wikipedia:Featured_pictures", "views": 700_000},
                {"article": "Mariana_Trench", "views": 50_000},
            ]}]}

    monkeypatch.setattr(ta.requests, "get", lambda *a, **k: R())
    out = ta.fetch_wikipedia_trending()
    assert [o["title"] for o in out] == ["Mariana Trench"]


# --------------------------------------------------------------------------
# Open-ended subject space
# --------------------------------------------------------------------------
#
# A constant list of domains caps what can ever be recommended -- the same
# "limited topics" problem as the old 31-entry curiosity library, one level up.
# Domains are therefore discovered per call, and the constant survives only as
# an emergency fallback for when the LLM is unreachable.

def test_fallback_domains_are_distinct():
    assert len(ta.FALLBACK_DOMAINS) == len(set(ta.FALLBACK_DOMAINS))


def test_generation_does_not_use_the_fallback_list_when_discovery_works(monkeypatch):
    """The hardcoded list must not silently become the working set."""
    discovered = ["undersea cable maintenance", "quilting techniques",
                  "coin minting", "salsa dance"]
    monkeypatch.setattr(ta, "discover_domains", lambda *a, **k: discovered)

    captured = {}

    class R:
        status_code = 200
        @staticmethod
        def json():
            return {"response": '{"topics":[{"title":"T","hook":"h",'
                                '"niche":"n","rpm_tier":"High"}]}'}

    def fake_post(url, json=None, timeout=None):
        captured["prompt"] = json["prompt"]
        return R()

    monkeypatch.setattr(ta.requests, "post", fake_post)
    ta.generate_ideas("m", count=4)

    for d in discovered:
        assert d in captured["prompt"], f"discovered domain {d!r} not used"
    for d in ta.FALLBACK_DOMAINS:
        assert d not in captured["prompt"], f"fallback domain {d!r} leaked in"


def test_discovery_falls_back_only_when_the_model_fails(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(ta.requests, "post", boom)
    areas = ta.discover_domains("m", 3)
    assert len(areas) == 3
    assert all(a in ta.FALLBACK_DOMAINS for a in areas)


def test_discovery_normalises_identifier_style_names(monkeypatch):
    class R:
        status_code = 200
        @staticmethod
        def json():
            return {"response": '{"areas":["stamp_collecting","wine_tasting"]}'}

    monkeypatch.setattr(ta.requests, "post", lambda *a, **k: R())
    assert ta.discover_domains("m", 2) == ["stamp collecting", "wine tasting"]


def test_exploration_seed_is_injected(monkeypatch):
    """Unseeded, an open 'invent subject areas' prompt converges on the same
    popular-science themes -- reintroducing the limit in a less visible form."""
    captured = {}

    class R:
        status_code = 200
        @staticmethod
        def json():
            return {"response": '{"areas":["a"]}'}

    def fake_post(url, json=None, timeout=None):
        captured["prompt"] = json["prompt"]
        return R()

    monkeypatch.setattr(ta.requests, "post", fake_post)
    ta.discover_domains("m", 1)
    assert any(seed in captured["prompt"] for seed in ta._EXPLORATION_SEEDS)


def test_focus_constrains_every_area(monkeypatch):
    captured = {}

    class R:
        status_code = 200
        @staticmethod
        def json():
            return {"response": '{"areas":["a"]}'}

    def fake_post(url, json=None, timeout=None):
        captured["prompt"] = json["prompt"]
        return R()

    monkeypatch.setattr(ta.requests, "post", fake_post)
    ta.discover_domains("m", 1, focus="cricket")
    assert "cricket" in captured["prompt"]
