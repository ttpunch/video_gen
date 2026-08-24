import script_utils as su


def test_split_exact_sentence_count():
    story = "One. Two. Three. Four. Five. Six. Seven."
    scenes = su.split_text_into_scenes(story, 7)
    assert len(scenes) == 7
    assert scenes[0] == "One."


def test_split_pads_when_too_few_sentences():
    scenes = su.split_text_into_scenes("A short story about a goalkeeper.", 7)
    assert len(scenes) == 7
    # No empty scenes.
    assert all(s.strip() for s in scenes)


def test_split_merges_when_too_many_sentences():
    story = " ".join(f"Sentence {i}." for i in range(20))
    scenes = su.split_text_into_scenes(story, 7)
    assert len(scenes) == 7
    # Order preserved: first bucket starts with Sentence 0.
    assert scenes[0].startswith("Sentence 0")


def test_split_handles_empty():
    scenes = su.split_text_into_scenes("", 7)
    assert len(scenes) == 7


def test_build_storyboard_is_topic_relevant():
    story = ("He was born in America but chose Japan. Goalkeeper Zion Suzuki is shocking "
             "the football world. Every save silences the doubters. He is rewriting the game.")
    sb = su.build_storyboard_from_story(story, "Zion Suzuki goalkeeper")
    assert len(sb["scenes"]) == 7
    # The fallback must carry the real topic, not canned filler.
    assert "Zion Suzuki" in sb["global_subject_focus"]
    assert "Zion Suzuki" in sb["topic"]
    # Narration comes from the actual story, not "mysterious mechanical box".
    joined = " ".join(s["narration"] for s in sb["scenes"]).lower()
    assert "mechanical box" not in joined
    assert "goalkeeper" in joined or "japan" in joined


def test_normalize_scene_count_trims():
    scenes = [{"narration": f"s{i}"} for i in range(10)]
    out = su.normalize_scene_count(scenes, "story", 7)
    assert len(out) == 7


def test_normalize_scene_count_pads():
    scenes = [{"narration": "only one", "speaker": "Sarah", "visual_prompt": "x"}]
    out = su.normalize_scene_count(scenes, "One. Two. Three. Four. Five. Six. Seven.", 7)
    assert len(out) == 7
    assert all("narration" in s and "visual_prompt" in s for s in out)


def test_topics_overlap_detects_same_subject():
    assert su.topics_overlap("Why Flamingos Are Pink", "flamingos spotted in india") is True
    assert su.topics_overlap("Zion Suzuki goalkeeper", "Apple launches new iPhone") is False


def test_topic_keywords_drops_stopwords():
    kw = su.topic_keywords("Why the new video about flamingos")
    assert "flamingos" in kw
    assert "the" not in kw and "why" not in kw and "video" not in kw


def test_filter_fresh_trends_removes_used():
    trends = [{"title": "Flamingos in India"}, {"title": "SpaceX Starship launch"}, {"title": "Octopus intelligence"}]
    used = ["Why Flamingos Are Pink"]
    fresh = su.filter_fresh_trends(trends, used)
    titles = [t["title"] for t in fresh]
    assert "Flamingos in India" not in titles
    assert "SpaceX Starship launch" in titles
    assert "Octopus intelligence" in titles


def test_filter_fresh_trends_empty_used_keeps_all():
    trends = [{"title": "A"}, {"title": "B"}]
    assert len(su.filter_fresh_trends(trends, [])) == 2
