"""Image prompts must fit CLIP's 77-token window with the realism cues intact.

Diffusion text encoders truncate silently. The old assembly put the style last,
so on long scene descriptions the realism keywords -- the part that decides
whether the output looks like a photograph -- were the first thing discarded.
"""
import pytest

import script_utils
from script_validator import REALISM_KEYWORDS

SUBJECT_LONG = ("an athletic deep-sea explorer in a battered orange pressure suit "
                "with a scratched brass helmet and heavy reinforced gloves")
SCENE_LONG = ("drifting weightless through absolute darkness, headlamp cutting a "
              "narrow cone of light through the water, face lit harshly from below, "
              "one arm reaching toward something enormous and unseen in the gloom")


def test_style_survives_even_on_a_very_long_scene():
    prompt = script_utils.compose_image_prompt(SUBJECT_LONG, SCENE_LONG, REALISM_KEYWORDS)
    assert "photorealistic" in prompt
    # More than just the first style term must make it through.
    assert prompt.count(",") > 4


def test_subject_is_never_dropped():
    """The subject is what keeps the same character recognisable across scenes."""
    prompt = script_utils.compose_image_prompt(SUBJECT_LONG, SCENE_LONG, REALISM_KEYWORDS)
    assert prompt.startswith(SUBJECT_LONG)


def test_some_of_the_scene_always_survives():
    """Style is worthless if the image is no longer of the right thing."""
    prompt = script_utils.compose_image_prompt(SUBJECT_LONG, SCENE_LONG, REALISM_KEYWORDS)
    assert "drifting weightless" in prompt


def test_short_prompts_are_passed_through_whole():
    subject, scene = "a lone astronaut", "floating above the earth"
    prompt = script_utils.compose_image_prompt(subject, scene, "photorealistic, sharp focus")
    assert prompt == "a lone astronaut, floating above the earth, photorealistic, sharp focus"


@pytest.mark.parametrize("subject,scene", [
    ("", ""),
    ("subject only", ""),
    ("", "scene only"),
    (SUBJECT_LONG, SCENE_LONG),
])
def test_composed_prompt_stays_within_the_word_budget(subject, scene):
    prompt = script_utils.compose_image_prompt(subject, scene, REALISM_KEYWORDS)
    assert len(prompt.split()) <= script_utils._CLIP_WORD_BUDGET + 4


def test_missing_style_still_produces_a_usable_prompt():
    assert script_utils.compose_image_prompt("a cat", "on a roof", "") == "a cat, on a roof"


def test_everything_empty_gives_an_empty_prompt():
    assert script_utils.compose_image_prompt("", "", "") == ""


def test_scene_without_commas_is_still_trimmed():
    """A single long clause cannot be term-trimmed, so it needs a word cut."""
    scene = " ".join(["word"] * 80)
    prompt = script_utils.compose_image_prompt("subject", scene, REALISM_KEYWORDS)
    assert "photorealistic" in prompt
    assert len(prompt.split()) < 80


def test_style_reserve_is_a_floor_not_a_cap():
    """When the scene is short there is room to spare and the whole style fits."""
    style = ", ".join(f"term{i}" for i in range(10))
    prompt = script_utils.compose_image_prompt("a cat", "on a mat", style)
    assert "term9" in prompt


@pytest.mark.skipif(
    pytest.importorskip("transformers", reason="transformers not installed") is None,
    reason="needs the real tokenizer")
def test_real_clip_tokenizer_does_not_truncate_a_long_prompt():
    """The budget is calibrated in words but the limit is in tokens -- so the
    calibration is checked against the actual tokenizer."""
    from transformers import CLIPTokenizer
    tok = CLIPTokenizer.from_pretrained("openai/clip-vit-large-patch14")

    for subject, scene in (
        ("a lone astronaut", "floating above the earth"),
        ("a weathered fisherman in a yellow raincoat",
         "standing on a storm-lashed pier at dawn holding a lantern"),
        (SUBJECT_LONG, SCENE_LONG),
    ):
        prompt = script_utils.compose_image_prompt(subject, scene, REALISM_KEYWORDS)
        n = len(tok(prompt).input_ids)
        assert n <= 77, f"{n} tokens, CLIP would truncate: {prompt!r}"
