"""Helpers for turning a free-form story into a storyboard.

Kept dependency-free (no torch/LLM) so the fallback logic is unit-testable. The
key job: when the LLM's JSON storyboard step fails, build a storyboard that is
still ABOUT THE TOPIC (derived from the generated story) rather than canned,
unrelated filler.
"""
import re

_SPEAKERS = ["Sarah", "Adam", "Sarah", "Adam", "George", "Sarah", "Adam"]

#: How many words reliably fit in CLIP's 77-token window. Calibrated against the
#: real tokenizer rather than estimated: commas and hyphenated/technical words
#: split into several tokens each, so descriptive prompts run about 1.6 tokens
#: per word. 44 was the largest budget that kept short, medium and long scenes
#: all under 77 tokens -- anything higher and the long ones silently overflow.
_CLIP_WORD_BUDGET = 44

#: Words reserved for the style tail before the scene gets to claim any. These
#: are the terms that decide whether the result looks like a photograph, so they
#: are budgeted first rather than appended and hoped for.
_STYLE_WORD_RESERVE = 20

#: However long the scene description is, keep at least this much of it -- the
#: style is worthless if the image is no longer of the right thing.
_MIN_SCENE_WORDS = 12


def _clip_terms(text, max_words):
    """Keep whole comma-separated terms from ``text`` up to a word budget."""
    kept, used = [], 0
    for term in (t.strip() for t in text.split(",")):
        if not term:
            continue
        cost = len(term.split())
        if used + cost > max_words and kept:
            break
        kept.append(term)
        used += cost
    return ", ".join(kept), used


def compose_image_prompt(subject="", scene="", style="", word_budget=_CLIP_WORD_BUDGET):
    """Assemble subject + scene + style into a prompt CLIP will not gut.

    Diffusion text encoders hard-truncate at 77 tokens, and the old assembly
    order appended the style last -- so on any long scene description the
    realism keywords were the first thing silently discarded, which is exactly
    the part that decides whether the output reads as a photograph. Measured on
    a realistic long scene, the old order kept 1 of 6 realism cues.

    So the style budget is *reserved first* rather than given the leftovers, and
    the scene description is trimmed to fit around it. The subject is never cut
    -- it is what keeps the same character recognisable across scenes.
    """
    subject = (subject or "").strip()
    scene = (scene or "").strip()
    style = (style or "").strip()

    if not style:
        return ", ".join(p for p in (subject, scene) if p)

    # The style reserve is a floor, not a cap: when subject and scene are short
    # there is room to spare and the full style should survive intact.
    subject_words = len(subject.split())
    style_budget = max(_STYLE_WORD_RESERVE,
                       word_budget - subject_words - len(scene.split()))
    style_kept, style_words = _clip_terms(style, max_words=style_budget)

    scene_budget = max(_MIN_SCENE_WORDS, word_budget - style_words - subject_words)
    scene_kept, scene_words = _clip_terms(scene, max_words=scene_budget)
    # _clip_terms always keeps its first term whole, so a scene written as one
    # long comma-less clause slips through untrimmed. Cut it by words instead.
    if scene_words > scene_budget:
        scene_kept = " ".join(scene_kept.split()[:scene_budget])

    return ", ".join(p for p in (subject, scene_kept, style_kept) if p)

_TOPIC_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "why", "how", "what", "who", "when", "where",
    "is", "are", "was", "were", "this", "that", "these", "those", "for", "with", "from",
    "about", "into", "your", "you", "they", "their", "his", "her", "its", "our",
    "actually", "really", "new", "best", "top", "video", "shorts", "facts",
}


def topic_keywords(text):
    """Significant lowercase words from a topic/trend title (for similarity checks)."""
    return {w for w in re.findall(r"[a-z0-9']+", (text or "").lower())
            if len(w) > 3 and w not in _TOPIC_STOPWORDS}


def topics_overlap(a, b):
    """True if two topics share a significant keyword (i.e. likely the same subject)."""
    ka, kb = topic_keywords(a), topic_keywords(b)
    return bool(ka & kb)


def filter_fresh_trends(trends, used_topics):
    """Drop trends that overlap any already-used topic, to avoid repeats.

    ``trends`` is a list of dicts with a 'title'. Returns a new filtered list.
    """
    used = list(used_topics or [])
    fresh = []
    for t in trends or []:
        title = t.get("title", "") if isinstance(t, dict) else str(t)
        if not any(topics_overlap(title, u) for u in used):
            fresh.append(t)
    return fresh


def split_text_into_scenes(text, n=7):
    """Split a story into exactly ``n`` narration chunks, preserving the text."""
    text = (text or "").strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        sentences = [text or "An incredible story."]

    # Too few: split the longest piece (on comma, else mid-word) until we reach n.
    guard = 0
    while len(sentences) < n and guard < 100:
        guard += 1
        idx = max(range(len(sentences)), key=lambda i: len(sentences[i]))
        longest = sentences[idx]
        if "," in longest:
            a, b = longest.split(",", 1)
            sentences[idx:idx + 1] = [a.strip(), b.strip()]
        elif " " in longest:
            words = longest.split()
            mid = len(words) // 2
            sentences[idx:idx + 1] = [" ".join(words[:mid]), " ".join(words[mid:])]
        else:
            break

    # Too many: distribute sentences across n buckets, keeping order.
    if len(sentences) > n:
        buckets = [[] for _ in range(n)]
        total = len(sentences)
        for i, s in enumerate(sentences):
            buckets[min(i * n // total, n - 1)].append(s)
        sentences = [" ".join(b).strip() for b in buckets if b]

    # Pad if still short (e.g. a 1-word story).
    while len(sentences) < n:
        sentences.append("Subscribe for more!")

    return sentences[:n]


def build_storyboard_from_story(story_text, topic, n=7):
    """Build a complete, topic-relevant storyboard dict from a story string."""
    topic = (topic or "Incredible Facts").strip()
    narrations = split_text_into_scenes(story_text, n)
    scenes = [
        {
            "speaker": _SPEAKERS[i % len(_SPEAKERS)],
            "narration": nar,
            "visual_prompt": f"a cinematic scene visually depicting: {nar}",
        }
        for i, nar in enumerate(narrations)
    ]
    return {
        "topic": topic,
        "background_music_style": "Cinematic",
        "global_visual_style": "realistic vertical 9:16, cinematic lighting, dramatic mood, high detail",
        "global_subject_focus": topic,
        "scenes": scenes,
        "youtube_metadata": {
            "title": (topic[:90] + " #shorts"),
            "description": f"{topic}. #shorts #facts #viral",
            "tags": ["shorts", "facts", "viral"],
        },
        "instagram_metadata": {"caption": f"{topic} \U0001f92f #reels #viral #facts"},
    }


def normalize_scene_count(scenes, story_text, n=7):
    """Force a storyboard's scene list to exactly ``n`` entries (trim or pad)."""
    scenes = list(scenes or [])
    if len(scenes) > n:
        return scenes[:n]
    if len(scenes) < n:
        filler = split_text_into_scenes(story_text, n)[len(scenes):]
        for nar in filler:
            scenes.append({
                "speaker": "Sarah",
                "narration": nar,
                "visual_prompt": f"a cinematic scene visually depicting: {nar}",
            })
    return scenes[:n]
