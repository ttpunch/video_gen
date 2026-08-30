"""Deterministic pre-flight checker for generated scripts/storyboards.

Runs BEFORE any TTS / image generation / render so bad scripts are caught in
milliseconds and regenerated, instead of wasting compute on a broken video.
Validates against the viral rules baked into the prompts, and enforces
photorealistic image styling.

No LLM, no torch - pure and unit-testable.

Issues are split into:
  * HARD  - regenerate the script (off-topic, repeats, wrong length, fallback...).
  * SOFT  - auto-fixable in place (missing CTA, non-realistic style).
"""
import re

CTA_WORDS = {"follow", "subscribe", "comment", "like", "share", "more", "watch", "save", "tap"}

# Anything that makes an image look non-photographic.
NON_REALISTIC = [
    "cartoon", "anime", "manga", "illustration", "illustrated", "3d render", "3d-render",
    "cgi", "painting", "drawing", "sketch", "watercolor", "cel-shaded", "cel shaded",
    "pixar", "comic", "vector", "low poly", "low-poly", "claymation", "render",
]

# Concrete photographic direction beats stacked superlatives. Terms like "8k"
# and "ultra-realistic" are not camera facts and push diffusion models toward
# the over-processed, plastic-skinned look that reads instantly as AI; naming a
# real focal length, aperture and film stock anchors it to actual photography.
REALISM_KEYWORDS = (
    "photorealistic, candid documentary photograph, shot on 35mm, 50mm lens at "
    "f/2.0, natural window light, true-to-life skin texture with visible pores, "
    "subtle skin imperfections, realistic proportions, sharp focus on the eyes, "
    "natural colour, subtle film grain"
)

# Non-photoreal style presets. Selecting one of these tells the validator to
# stop forcing photorealism (and stop scrubbing cartoon/drawing words) and to
# inject the chosen descriptor as the global visual style instead.
STICKMAN_KEYWORDS = (
    "simple stick figure animation, classic stickman, black stick figure with a "
    "round circle head and straight thin line limbs, bold clean black lines, "
    "minimalist, plain solid white background, 2D flat, no shading, no gradients, "
    "no photorealism, 'Animator vs Animation' style, hand-drawn line art"
)

ART_STYLE_PRESETS = {
    "Photorealistic": REALISM_KEYWORDS,
    "Stickman Animation": STICKMAN_KEYWORDS,
}

# Markers of the canned/template fallback content.
FALLBACK_MARKERS = ["mysterious mechanical box", "deep beneath the ocean"]

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "why", "how", "what", "who", "when", "where",
    "is", "are", "was", "were", "this", "that", "these", "those", "for", "with", "from",
    "about", "into", "your", "you", "they", "their", "his", "her", "its", "our",
}


def _words(s):
    return re.findall(r"[a-z0-9']+", (s or "").lower())


def _norm(s):
    return " ".join(_words(s))


def validate_script(data, topic, n_scenes=7, min_words=40, max_words=95,
                    art_style="Photorealistic"):
    """Return ``(hard_issues, soft_issues)`` for a generated script dict.

    ``art_style`` selects the target visual style. For the default
    ``"Photorealistic"`` the photorealism check applies; any other preset (e.g.
    ``"Stickman Animation"``) intentionally skips it so the non-photoreal look
    is preserved.
    """
    hard, soft = [], []
    scenes = data.get("scenes") or []
    narrs = [(s.get("narration") or "").strip() for s in scenes]

    if len(scenes) != n_scenes:
        hard.append(f"expected {n_scenes} scenes, got {len(scenes)}")
    if any(not nr for nr in narrs):
        hard.append("a scene has empty narration")

    # The opening line decides whether the viewer keeps watching or swipes,
    # typically within 1-3 seconds -- research puts the workable spoken-hook
    # window at roughly 8-14 words. A longer opener has already lost the
    # decision by the time it finishes; this was previously unchecked, so a
    # rambling first line could reach render undetected.
    if narrs:
        hook_word_count = len(_words(narrs[0]))
        if hook_word_count > 16:
            hard.append(f"hook (scene 1) is {hook_word_count} words; "
                       "must be roughly 8-14 to land inside the 3-second decision window")

    total_words = len(_words(" ".join(narrs)))
    if total_words < min_words:
        hard.append(f"script too short ({total_words} words; need >= {min_words})")
    elif total_words > max_words:
        hard.append(f"script too long ({total_words} words; max {max_words})")

    norms = [_norm(nr) for nr in narrs if nr]
    if len(set(norms)) < len(norms):
        hard.append("duplicate narration lines")
    # One line fully contained in another => fragmented title-splitting.
    if any(a != b and a and a in b for a in norms for b in norms):
        hard.append("overlapping/fragmented narration lines")

    blob = _norm(" ".join(narrs) + " " + str(data.get("global_subject_focus", "")))
    if any(m in blob for m in FALLBACK_MARKERS):
        hard.append("looks like canned fallback content")

    topic_words = [w for w in _words(topic) if len(w) > 3 and w not in STOPWORDS]
    if topic_words and not any(tw in blob for tw in topic_words):
        hard.append("content does not reference the topic (off-topic)")

    vps = [(s.get("visual_prompt") or "").strip() for s in scenes]
    if any(len(vp) < 5 for vp in vps):
        hard.append("a visual prompt is empty or too short")

    # --- soft (auto-fixable) ---
    if narrs and not (set(_words(narrs[-1])) & CTA_WORDS):
        soft.append("missing call-to-action in final scene")
    if art_style == "Photorealistic" and _is_non_realistic(data.get("global_visual_style", "")):
        soft.append("visual style is not photorealistic")

    return hard, soft


def _is_non_realistic(style):
    s = (style or "").lower()
    has_realism = any(k in s for k in ("photoreal", "realistic", "photograph", "lifelike", "dslr"))
    has_bad = any(b in s for b in NON_REALISTIC)
    return has_bad or not has_realism


def enforce_realism(data):
    """Force the storyboard toward photorealism (style + per-scene visual prompts)."""
    style = (data.get("global_visual_style") or "").strip()
    low = style.lower()
    # Drop any non-photographic descriptors from the global style.
    cleaned = style
    for bad in NON_REALISTIC:
        cleaned = re.sub(re.escape(bad), "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*,\s*,+", ", ", cleaned).strip(" ,")
    # Always lead with realism keywords.
    if any(b in low for b in NON_REALISTIC) or not cleaned:
        data["global_visual_style"] = REALISM_KEYWORDS
    elif not any(k in low for k in ("photoreal", "realistic", "photograph", "lifelike", "dslr")):
        data["global_visual_style"] = f"{REALISM_KEYWORDS}, {cleaned}"
    else:
        data["global_visual_style"] = cleaned

    # Scrub non-realistic words from each scene's visual prompt.
    for s in data.get("scenes", []):
        vp = s.get("visual_prompt") or ""
        if any(b in vp.lower() for b in NON_REALISTIC):
            for bad in NON_REALISTIC:
                vp = re.sub(re.escape(bad), "realistic", vp, flags=re.I)
            s["visual_prompt"] = re.sub(r"\s*,\s*,+", ", ", vp).strip(" ,")
    return data


def enforce_art_style(data, art_style):
    """Apply a non-photoreal style preset: lead the global visual style with the
    chosen descriptor and leave scene visual prompts untouched (no realism
    scrubbing), so the stylized look survives to image generation."""
    descriptor = ART_STYLE_PRESETS.get(art_style, "").strip()
    existing = (data.get("global_visual_style") or "").strip()
    if descriptor and existing and descriptor.lower() not in existing.lower():
        data["global_visual_style"] = f"{descriptor}, {existing}"
    elif descriptor:
        data["global_visual_style"] = descriptor
    return data


def ensure_cta(data):
    """Append a short CTA to the last scene if one is missing."""
    scenes = data.get("scenes") or []
    if not scenes:
        return data
    last = scenes[-1]
    if not (set(_words(last.get("narration", ""))) & CTA_WORDS):
        text = (last.get("narration") or "").strip()
        last["narration"] = (text + " Subscribe for more!").strip()
    return data


def autofix(data, art_style="Photorealistic"):
    """Apply all soft fixes in place and return the data.

    For the default ``"Photorealistic"`` style this enforces realism; for any
    other preset it injects that style's descriptor instead. CTA is always
    ensured.
    """
    if art_style == "Photorealistic":
        enforce_realism(data)
    else:
        enforce_art_style(data, art_style)
    ensure_cta(data)
    return data
