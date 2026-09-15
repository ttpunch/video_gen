import script_validator as sv


def _good_script():
    narrs = [
        "Flamingos aren't born pink at all.",
        "They actually hatch a dull gray color.",
        "The secret comes entirely from their diet.",
        "They eat brine shrimp packed with beta-carotene.",
        "Their liver breaks down that bright pigment.",
        "It slowly paints every single feather pink.",
        "Follow for more wild nature facts.",
    ]
    return {
        "topic": "Why flamingos are pink",
        "global_visual_style": "photorealistic, natural lighting, high detail",
        "global_subject_focus": "a vivid pink flamingo wading in a shallow lagoon",
        "scenes": [{"speaker": "Sarah", "narration": n, "visual_prompt": f"a realistic scene of {n}"} for n in narrs],
    }


def test_good_script_passes():
    hard, soft = sv.validate_script(_good_script(), "Why flamingos are pink")
    assert hard == []


def test_off_topic_is_hard():
    d = _good_script()
    for s in d["scenes"]:
        s["narration"] = "Deep space contains many mysterious objects today."
    d["global_subject_focus"] = "a galaxy"
    hard, _ = sv.validate_script(d, "Why flamingos are pink")
    assert any("off-topic" in h for h in hard)


def test_too_short_is_hard():
    d = _good_script()
    d["scenes"] = [{"narration": "Pink birds.", "visual_prompt": "a pink bird"} for _ in range(7)]
    hard, _ = sv.validate_script(d, "Why flamingos are pink")
    assert any("too short" in h for h in hard) or any("duplicate" in h for h in hard)


def test_duplicate_lines_is_hard():
    d = _good_script()
    d["scenes"][2]["narration"] = d["scenes"][1]["narration"]
    hard, _ = sv.validate_script(d, "Why flamingos are pink")
    assert any("duplicate" in h for h in hard)


def test_fragmented_overlap_is_hard():
    d = _good_script()
    d["scenes"][0]["narration"] = "Flamingos are pink"
    d["scenes"][1]["narration"] = "Flamingos are pink because of their diet and shrimp"
    hard, _ = sv.validate_script(d, "Why flamingos are pink")
    assert any("overlapping" in h or "fragmented" in h for h in hard)


def test_fallback_content_is_hard():
    d = _good_script()
    d["global_subject_focus"] = "a detailed mysterious mechanical box emitting golden light"
    d["scenes"][1]["narration"] = "Deep beneath the ocean strange anomalies exist."
    hard, _ = sv.validate_script(d, "Why flamingos are pink")
    assert any("fallback" in h for h in hard)


def test_missing_cta_is_soft_and_autofixed():
    d = _good_script()
    d["scenes"][-1]["narration"] = "And that is the whole story."
    hard, soft = sv.validate_script(d, "Why flamingos are pink")
    assert hard == []
    assert any("call-to-action" in s for s in soft)
    sv.ensure_cta(d)
    assert "subscribe" in d["scenes"][-1]["narration"].lower()


def test_non_realistic_style_is_soft_and_enforced():
    d = _good_script()
    d["global_visual_style"] = "cartoon, anime, cel-shaded, vibrant"
    hard, soft = sv.validate_script(d, "Why flamingos are pink")
    assert any("photorealistic" in s for s in soft)
    sv.enforce_realism(d)
    style = d["global_visual_style"].lower()
    assert "photorealistic" in style
    assert "cartoon" not in style and "anime" not in style


def test_enforce_realism_scrubs_scene_prompts():
    d = _good_script()
    d["scenes"][0]["visual_prompt"] = "an anime illustration of a flamingo"
    sv.enforce_realism(d)
    assert "anime" not in d["scenes"][0]["visual_prompt"].lower()
    assert "illustration" not in d["scenes"][0]["visual_prompt"].lower()


def test_autofix_makes_script_pass():
    d = _good_script()
    d["global_visual_style"] = "3d render, pixar style"
    d["scenes"][-1]["narration"] = "The end of the story."
    sv.autofix(d)
    hard, soft = sv.validate_script(d, "Why flamingos are pink")
    assert hard == [] and soft == []


# --------------------------------------------------------------------------
# Hook length (the opening line is the swipe-or-stay decision)
# --------------------------------------------------------------------------

def test_long_winded_hook_is_hard():
    d = _good_script()
    d["scenes"][0]["narration"] = (
        "So today I wanted to sit down and actually properly explain to you "
        "exactly why flamingos are famously known for being this particular shade of pink."
    )
    hard, _soft = sv.validate_script(d, "Why flamingos are pink")
    assert any("hook" in h.lower() for h in hard)


def test_punchy_hook_is_not_flagged():
    d = _good_script()
    d["scenes"][0]["narration"] = "Flamingos aren't actually born pink at all."  # 7 words
    hard, _soft = sv.validate_script(d, "Why flamingos are pink")
    assert not any("hook" in h.lower() for h in hard)


def test_very_short_hook_is_not_penalised():
    """Brevity is fine; only a rambling opener is the failure mode."""
    d = _good_script()
    d["scenes"][0]["narration"] = "This changes everything."  # 3 words
    hard, _soft = sv.validate_script(d, "Why flamingos are pink")
    assert not any("hook" in h.lower() for h in hard)


# --------------------------------------------------------------------------
# Mechanical fixes -- correcting hard issues without an LLM regeneration
# --------------------------------------------------------------------------

def test_mechanical_fix_trims_an_overlong_hook():
    d = _good_script()
    d["scenes"][0]["narration"] = (
        "So today I wanted to sit down and actually properly explain to you "
        "exactly why flamingos are famously known for being this particular shade of pink."
    )
    hard, _soft = sv.validate_script(d, "Why flamingos are pink")
    assert any("hook" in h for h in hard)

    fixed, remaining = sv.mechanically_fix_hard_issues(d, hard, min_words=40)

    assert not any("hook" in h for h in remaining)
    hard_after, _ = sv.validate_script(fixed, "Why flamingos are pink")
    assert not any("hook" in h for h in hard_after)


def test_mechanical_fix_swaps_a_duplicated_final_cta():
    d = _good_script()
    d["scenes"][-1]["narration"] = d["scenes"][0]["narration"]  # CTA duplicates the hook
    hard, _soft = sv.validate_script(d, "Why flamingos are pink")
    assert any("duplicate" in h for h in hard)

    fixed, remaining = sv.mechanically_fix_hard_issues(d, hard, min_words=40)

    assert not any("duplicate" in h for h in remaining)
    assert fixed["scenes"][-1]["narration"] == "Subscribe so you never miss one!"


def test_mechanical_fix_leaves_a_mid_script_duplicate_for_regeneration():
    """Only the CTA slot is safe to swap for a generic line -- a duplicate
    anywhere else needs real replacement content only the LLM can supply."""
    d = _good_script()
    d["scenes"][2]["narration"] = d["scenes"][1]["narration"]
    hard, _soft = sv.validate_script(d, "Why flamingos are pink")
    assert any("duplicate" in h for h in hard)

    _fixed, remaining = sv.mechanically_fix_hard_issues(d, hard, min_words=40)

    assert any("duplicate" in h for h in remaining)


def test_mechanical_fix_does_not_touch_unfixable_issues():
    d = _good_script()
    for s in d["scenes"]:
        s["narration"] = "Deep space contains many mysterious objects today."
    d["global_subject_focus"] = "a galaxy"
    hard, _soft = sv.validate_script(d, "Why flamingos are pink")
    assert any("off-topic" in h for h in hard)

    _fixed, remaining = sv.mechanically_fix_hard_issues(d, hard, min_words=40)

    assert remaining == hard
