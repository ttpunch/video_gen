import captions


WORDS = [
    {"word": "Did", "start": 0.0, "end": 0.30},
    {"word": "you", "start": 0.30, "end": 0.55},
    {"word": "know", "start": 0.55, "end": 0.90},
    {"word": "space", "start": 1.20, "end": 1.70},  # note the pause before "space"
]


def test_chunk_words_groups_by_size():
    chunks = captions.chunk_words(WORDS, words_per_chunk=3)
    assert len(chunks) == 2
    assert [w["word"] for w in chunks[0]] == ["Did", "you", "know"]
    assert [w["word"] for w in chunks[1]] == ["space"]


def test_events_use_real_timestamps():
    events = captions.build_dialogue_events(WORDS, words_per_chunk=3)
    # 4 words -> 4 dialogue lines.
    assert len(events) == 4
    # First word starts at 0:00:00.00
    assert "0:00:00.00" in events[0]
    # Within the chunk, the first word holds until the second word begins (0.30s).
    assert "0:00:00.30" in events[0]


def test_highlight_color_is_embedded():
    events = captions.build_dialogue_events(WORDS, highlight_color="&H00FF00&")
    assert any("&H00FF00&" in e for e in events)


def test_viral_pop_applies_pop_animation_on_chunk_entry():
    events = captions.build_dialogue_events(WORDS, style_mode="Viral Pop")
    # The pop animation tag appears on the first word of each chunk.
    assert events[0].count("\\t(") >= 1


def test_build_ass_has_header_and_events():
    doc = captions.build_ass(WORDS, font_name="Trebuchet MS", font_size=80)
    assert "[Script Info]" in doc
    assert "PlayResX: 1080" in doc
    assert "[Events]" in doc
    assert "Trebuchet MS" in doc
    assert doc.count("Dialogue:") == 4


def test_empty_words_yield_no_events():
    assert captions.build_dialogue_events([]) == []
    assert captions.build_dialogue_events([{"word": "  ", "start": 0, "end": 1}]) == []


def test_write_ass_from_words(tmp_path):
    out = tmp_path / "subs.ass"
    assert captions.write_ass_from_words(WORDS, str(out)) is True
    assert "Dialogue:" in out.read_text()


# --------------------------------------------------------------------------
# "Soft Pill" caption style
# --------------------------------------------------------------------------
#
# A rounded translucent plate behind the words, so captions stay readable over
# bright or busy footage where an outline alone disappears. Two things make
# this non-obvious to get right: ASS has no rounded-rectangle primitive (the
# corners are Beziers), and the plate must be emitted once per *chunk* on a
# lower layer -- drawing it per word would stack translucent plates and darken
# the overlaps, which is exactly what the BorderStyle=3 approach did.

def _pill_events(out):
    return [l for l in out.splitlines() if l.startswith("Dialogue:") and ",Pill," in l]


def _text_events(out):
    return [l for l in out.splitlines() if l.startswith("Dialogue:") and ",Default," in l]


WORDS_3 = [
    {"word": "Ninety", "start": 0.0, "end": 0.4},
    {"word": "five", "start": 0.4, "end": 0.8},
    {"word": "percent", "start": 0.8, "end": 1.4},
]


def test_soft_pill_emits_one_plate_per_chunk_not_per_word():
    """Per-word plates would overlap and darken at the seams."""
    out = captions.build_ass(WORDS_3, style_mode="Soft Pill", words_per_chunk=3)
    assert len(_pill_events(out)) == 1
    assert len(_text_events(out)) == 3, "word-by-word highlighting must survive"


def test_soft_pill_plate_sits_behind_the_text():
    out = captions.build_ass(WORDS_3, style_mode="Soft Pill")
    assert _pill_events(out)[0].startswith("Dialogue: 0,"), "plate must be layer 0"
    for line in _text_events(out):
        assert line.startswith("Dialogue: 1,"), "text must be layer 1, above the plate"


def test_soft_pill_plate_spans_the_whole_chunk():
    """It must not blink between words."""
    out = captions.build_ass(WORDS_3, style_mode="Soft Pill")
    pill = _pill_events(out)[0].split(",")
    assert pill[1] == captions.format_ass_time(0.0)
    assert pill[2] == captions.format_ass_time(1.4)


def test_other_styles_draw_no_plate():
    for mode in ("Viral Pop", "Standard"):
        out = captions.build_ass(WORDS_3, style_mode=mode)
        assert not _pill_events(out), f"{mode} should not draw a plate"
        assert "Style: Pill," not in out


def test_rounded_corners_use_beziers_not_chamfers():
    """Straight corner segments read as a bevel, not a radius."""
    path = captions.rounded_rect_drawing(400, 120, 24)
    assert path.count(" b ") == 4, "expected a Bezier at each corner"
    assert path.startswith("m ")


def test_radius_is_clamped_to_the_box():
    """A radius larger than half the box would invert the path."""
    path = captions.rounded_rect_drawing(40, 20, 999)
    assert path.count(" b ") == 4
    # Every coordinate must stay inside the box.
    nums = [int(t) for t in path.replace("m", " ").replace("l", " ").replace("b", " ").split()]
    assert max(nums) <= 40


def test_plate_is_clamped_to_the_frame():
    font = captions.resolve_font_file("Arial")
    if not font:
        import pytest
        pytest.skip("no measurable font on this machine")
    x, y, w, h, _r = captions.pill_geometry("x" * 300, font, 72, 700)
    assert x >= 0 and x + w <= 1080, "plate ran outside the 1080px frame"


def test_unmeasurable_font_degrades_to_no_plate(monkeypatch):
    """Guessing a width would draw a plate that visibly does not fit the text."""
    monkeypatch.setattr(captions, "resolve_font_file", lambda name: None)
    out = captions.build_ass(WORDS_3, style_mode="Soft Pill")
    assert not _pill_events(out)
    assert _text_events(out), "captions must still render without the plate"


def test_measurement_failure_degrades_to_no_plate(monkeypatch):
    monkeypatch.setattr(captions, "measure_text_width", lambda *a, **k: None)
    out = captions.build_ass(WORDS_3, style_mode="Soft Pill")
    assert not _pill_events(out)
    assert _text_events(out)
