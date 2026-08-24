"""Build ASS subtitles from real, audio-aligned word timestamps.

The legacy ``generate_ass_subtitles`` in backend.py estimates each word's timing
by splitting a scene's duration proportionally to word length, which drifts out
of sync with the actual voice. Given true word timestamps (from Whisper), this
module produces captions that highlight each word exactly when it is spoken,
while preserving the existing "Viral Pop" look.

Kept dependency-free so it can be unit-tested without torch/whisper.
"""

# 80ms pop up to 120%, settle back to 100% — matches the legacy look.
ANIM_TAGS = r"{\fscx80\fscy80\t(0,80,\fscx120\fscy120)\t(80,150,\fscx100\fscy100)}"

#: "Soft Pill" geometry, mirroring the look MoneyPrinterTurbo uses: a rounded,
#: semi-transparent plate that hugs the text rather than spanning the frame.
# ASS alpha runs backwards from PIL's: 00 is fully opaque, FF invisible.
# MoneyPrinterTurbo draws its plate at PIL alpha 140 (55% opaque), so the
# equivalent ASS byte is 255-140 = 115 = 0x73. At 0x80 (50%) the plate was
# measurably too weak to carry white text over busy footage like a coral reef.
PILL_ALPHA = "73"
PILL_PAD_X_RATIO = 0.45        # horizontal padding, as a fraction of font size
PILL_PAD_Y_RATIO = 0.30
PILL_RADIUS_RATIO = 0.40       # corner radius; MPT uses 0.4 * font size
PILL_LINE_HEIGHT_RATIO = 1.20

#: Fonts to try when resolving a style's font name to a real file for measuring.
_FONT_SEARCH_DIRS = (
    "/System/Library/Fonts/Supplemental",
    "/System/Library/Fonts",
    "/Library/Fonts",
    "/usr/share/fonts/truetype/dejavu",
)


def resolve_font_file(font_name: str):
    """Best-effort map an ASS font *name* to a font *file* for measurement.

    Returns None when nothing matches: the pill needs a real text width, and
    guessing one would produce a plate that visibly does not fit the text, so
    callers fall back to the outline-only look instead.
    """
    import os
    candidates = [f"{font_name} Bold.ttf", f"{font_name}.ttf",
                  f"{font_name}-Bold.ttf", f"{font_name}.ttc"]
    for directory in _FONT_SEARCH_DIRS:
        for cand in candidates:
            p = os.path.join(directory, cand)
            if os.path.exists(p):
                return p
    for directory in _FONT_SEARCH_DIRS:
        for fallback in ("Arial Bold.ttf", "Arial.ttf", "Helvetica.ttc",
                         "DejaVuSans-Bold.ttf"):
            p = os.path.join(directory, fallback)
            if os.path.exists(p):
                return p
    return None


def measure_text_width(text: str, font_file: str, font_size: int):
    """Pixel width of ``text``, or None if it cannot be measured."""
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(font_file, font_size)
        box = font.getbbox(text)
        return int(box[2] - box[0])
    except Exception:
        return None


def rounded_rect_drawing(width: int, height: int, radius: int) -> str:
    """ASS \\p1 vector path for a rounded rectangle, origin at its top-left.

    ASS has no rounded-rect primitive, so the corners are cubic Beziers. The
    0.5523 control-point offset is the standard circular approximation; using
    straight corner segments instead reads as a chamfer rather than a radius.
    """
    width, height = int(width), int(height)
    radius = max(1, min(int(radius), width // 2, height // 2))
    c = int(round(radius * 0.5523))
    return (
        f"m {radius} 0 "
        f"l {width - radius} 0 b {width - radius + c} 0 {width} {radius - c} {width} {radius} "
        f"l {width} {height - radius} b {width} {height - radius + c} "
        f"{width - radius + c} {height} {width - radius} {height} "
        f"l {radius} {height} b {radius - c} {height} 0 {height - radius + c} 0 {height - radius} "
        f"l 0 {radius} b 0 {radius - c} {radius - c} 0 {radius} 0"
    )


def pill_geometry(text: str, font_file: str, font_size: int, margin_v: int,
                  play_res_x: int = 1080, play_res_y: int = 1920):
    """Return ``(x, y, w, h, radius)`` for the plate behind ``text``.

    Returns None when the text cannot be measured.
    """
    text_w = measure_text_width(text, font_file, font_size)
    if not text_w:
        return None
    pad_x = int(font_size * PILL_PAD_X_RATIO)
    pad_y = int(font_size * PILL_PAD_Y_RATIO)
    box_w = min(text_w + 2 * pad_x, play_res_x - 40)
    box_h = int(font_size * PILL_LINE_HEIGHT_RATIO) + 2 * pad_y
    box_x = (play_res_x - box_w) // 2
    # Alignment 2 puts the text's baseline block margin_v above the bottom edge.
    # Centre the plate on that block rather than on margin_v itself, or it sits
    # noticeably low relative to the glyphs.
    line_h = int(font_size * PILL_LINE_HEIGHT_RATIO)
    text_centre_y = play_res_y - margin_v - line_h // 2
    box_y = text_centre_y - box_h // 2
    return box_x, box_y, box_w, box_h, int(font_size * PILL_RADIUS_RATIO)


ASS_HEADER_INFO = [
    "[Script Info]",
    "Title: Viral Subtitles",
    "ScriptType: v4.00+",
    "PlayResX: 1080",
    "PlayResY: 1920",
    "WrapStyle: 0",
    "",
    "[V4+ Styles]",
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
    "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
]


def format_ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _style_lines(font_name, font_size, highlight_color, alignment, margin_v, style_mode):
    """Return every ``Style:`` line the document needs, in order."""
    if style_mode == "Soft Pill":
        # Light outline only: the plate supplies the contrast, so the heavy
        # 8px stroke used by Viral Pop would just look muddy on top of it.
        text = (f"Style: Default,{font_name},{font_size},&HFFFFFF,{highlight_color},"
                f"&H000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,{alignment},50,50,{margin_v},1")
        # \an7 (top-left) so \pos places the plate's corner exactly where the
        # geometry says, rather than centring the drawing on the point.
        pill = (f"Style: Pill,{font_name},{font_size},&H{PILL_ALPHA}000000,"
                f"&H{PILL_ALPHA}000000,&H{PILL_ALPHA}000000,&H00000000,"
                f"0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1")
        return [pill, text]
    if style_mode == "Viral Pop":
        return [(f"Style: Default,{font_name},{font_size + 15},&HFFFFFF,{highlight_color},"
                 f"&H000000,&H00000000,-1,0,0,0,100,100,0,0,1,8,2,{alignment},50,50,{margin_v},1")]
    return [(f"Style: Default,{font_name},{font_size},&HFFFFFF,{highlight_color},"
             f"&H000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,{alignment},50,50,{margin_v},1")]


def _style_line(font_name, font_size, highlight_color, alignment, margin_v, style_mode):
    """Backwards-compatible single-style accessor."""
    return _style_lines(font_name, font_size, highlight_color, alignment,
                        margin_v, style_mode)[-1]


def chunk_words(words, words_per_chunk=3):
    """Split a flat word list into display chunks."""
    return [words[i:i + words_per_chunk] for i in range(0, len(words), words_per_chunk)]


def build_dialogue_events(words, highlight_color="&H00FFFF&", style_mode="Viral Pop",
                          words_per_chunk=3, font_name="Arial", font_size=42,
                          margin_v=150):
    """Return a list of ASS ``Dialogue:`` lines for the given timestamped words.

    Each word is a mapping with ``word``, ``start`` and ``end`` (seconds). Within a
    chunk the line stays continuously on screen and the highlight advances word by
    word, so there is no flicker during pauses between words.
    """
    events = []
    pill_font = resolve_font_file(font_name) if style_mode == "Soft Pill" else None

    for chunk in chunk_words(words, words_per_chunk):
        chunk = [w for w in chunk if str(w.get("word", "")).strip()]
        if not chunk:
            continue
        chunk_end = chunk[-1]["end"]

        # One plate per chunk, held for the whole chunk, drawn on layer 0 so the
        # per-word text on layer 1 sits on top. Emitting it per *word* instead
        # would redraw overlapping translucent plates and darken the seams.
        if pill_font:
            phrase = " ".join(str(w["word"]).strip() for w in chunk)
            geom = pill_geometry(phrase, pill_font, font_size, margin_v)
            if geom:
                x, y, w, h, radius = geom
                events.append(
                    f"Dialogue: 0,{format_ass_time(chunk[0]['start'])},"
                    f"{format_ass_time(chunk_end)},Pill,,0,0,0,,"
                    f"{{\\pos({x},{y})\\p1}}{rounded_rect_drawing(w, h, radius)}{{\\p0}}"
                )
        for w_idx, w in enumerate(chunk):
            seg_start = w["start"]
            # Hold each word until the next begins; the last word holds to chunk end.
            seg_end = chunk[w_idx + 1]["start"] if w_idx + 1 < len(chunk) else chunk_end
            if seg_end <= seg_start:
                seg_end = seg_start + 0.05

            rendered = []
            for j, cw in enumerate(chunk):
                token = str(cw["word"]).strip()
                if j == w_idx:
                    rendered.append(f"{{\\c{highlight_color}\\b1}}{token}{{\\b0\\c&HFFFFFF&}}")
                else:
                    rendered.append(token)
            line_text = " ".join(rendered)

            if style_mode == "Viral Pop":
                if w_idx == 0:
                    line_text = f"{ANIM_TAGS}{{\\b1\\c&HFFFFFF&}}{line_text}"
                else:
                    line_text = f"{{\\b1\\c&HFFFFFF&\\fscx100\\fscy100}}{line_text}"
            else:
                line_text = f"{{\\c&HFFFFFF&}}{line_text}"

            layer = 1 if pill_font else 0
            events.append(
                f"Dialogue: {layer},{format_ass_time(seg_start)},{format_ass_time(seg_end)},"
                f"Default,,0,0,0,,{line_text}"
            )
    return events


def build_ass(words, font_name="Arial", font_size=42, margin_v=150, alignment=2,
              highlight_color="&H00FFFF&", style_mode="Viral Pop", words_per_chunk=3):
    """Return a full ASS document string for the given timestamped words."""
    lines = list(ASS_HEADER_INFO)
    lines += _style_lines(font_name, font_size, highlight_color, alignment,
                          margin_v, style_mode)
    lines += ["", "[Events]",
              "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    lines += build_dialogue_events(words, highlight_color, style_mode, words_per_chunk,
                                   font_name=font_name, font_size=font_size,
                                   margin_v=margin_v)
    return "\n".join(lines)


def write_ass_from_words(words, output_path, **kwargs):
    """Write a word-synced ASS subtitle file. Returns True on success."""
    content = build_ass(words, **kwargs)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True
