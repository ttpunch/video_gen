"""Style-aware validation: non-photoreal art styles (e.g. stickman) must NOT be
forced back to photorealism, while the default Photorealistic path stays intact.
"""
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
        "scenes": [{"speaker": "Sarah", "narration": n, "visual_prompt": f"a scene of {n}"} for n in narrs],
    }


def test_stickman_style_not_flagged_non_realistic():
    d = _good_script()
    d["global_visual_style"] = "simple stick figure drawing, black line art"
    hard, soft = sv.validate_script(d, "Why flamingos are pink", art_style="Stickman Animation")
    assert hard == []
    assert not any("photorealistic" in s for s in soft)


def test_enforce_art_style_injects_stickman_descriptor():
    d = _good_script()
    d["scenes"][0]["visual_prompt"] = "a sketch drawing of a flamingo"
    sv.autofix(d, art_style="Stickman Animation")
    style = d["global_visual_style"].lower()
    assert "stick figure" in style or "stickman" in style
    # Non-realistic words in scene prompts must NOT be scrubbed for this style.
    assert "drawing" in d["scenes"][0]["visual_prompt"].lower() or "sketch" in d["scenes"][0]["visual_prompt"].lower()


def test_photorealistic_path_unchanged():
    d = _good_script()
    d["global_visual_style"] = "cartoon, anime, cel-shaded"
    d["scenes"][0]["visual_prompt"] = "an anime illustration of a flamingo"
    sv.autofix(d)  # default art_style == "Photorealistic"
    style = d["global_visual_style"].lower()
    assert "photorealistic" in style
    assert "cartoon" not in style and "anime" not in style
    assert "anime" not in d["scenes"][0]["visual_prompt"].lower()
