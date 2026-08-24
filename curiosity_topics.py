"""Curated evergreen "curiosity-gap" topics for the viral pipeline.

This is the single source of truth shared by:
  * the auto-agent scheduler (``viral_agent.py``) as an alternative topic source
  * the frontend "Curiosity Topics" card (served via ``GET /api/curiosity-topics``)

Each topic opens a loop the viewer feels compelled to close — the kind of angle
that reliably trends on YouTube Shorts. The ``hook`` is passed into the script
drafter and web-grounding steps as context so the generated video actually leans
into the curiosity angle rather than just the bare title.
"""

import random

CURIOSITY_TOPICS = [
    # Space & Cosmos
    {"category": "Space", "emoji": "🌌", "title": "What's really inside a black hole", "hook": "Nothing that falls in ever comes back — and time itself breaks down."},
    {"category": "Space", "emoji": "🌌", "title": "The hidden ocean beneath Jupiter's moon Europa", "hook": "More water than all of Earth's oceans, sealed under miles of ice."},
    {"category": "Space", "emoji": "🌌", "title": "What you'd see at the edge of the universe", "hook": "Spoiler: there may be no edge at all."},
    {"category": "Space", "emoji": "🌌", "title": "The star so big it makes the Sun look invisible", "hook": "UY Scuti could swallow billions of Suns whole."},
    {"category": "Space", "emoji": "🌌", "title": "Why the Moon is slowly escaping Earth", "hook": "It drifts 3.8 cm farther away every single year."},

    # Deep Ocean
    {"category": "Deep Ocean", "emoji": "🌊", "title": "The creatures at the bottom of the Mariana Trench", "hook": "Life thrives seven miles down, where sunlight has never reached."},
    {"category": "Deep Ocean", "emoji": "🌊", "title": "What's hiding in the ocean's midnight zone", "hook": "95% of the ocean has never been seen by human eyes."},
    {"category": "Deep Ocean", "emoji": "🌊", "title": "The underwater waterfall you can actually see", "hook": "Mauritius hides an optical illusion of an ocean falling off a cliff."},
    {"category": "Deep Ocean", "emoji": "🌊", "title": "Why we've mapped Mars better than our own seafloor", "hook": "We know the red planet's surface in sharper detail than Earth's."},

    # Unsolved Mysteries
    {"category": "Mysteries", "emoji": "🕵️", "title": "The ships that vanished in the Bermuda Triangle", "hook": "Decades of disappearances — and not a single wreck ever found."},
    {"category": "Mysteries", "emoji": "🕵️", "title": "The radio signal from space we still can't explain", "hook": "The 'Wow!' signal lasted 72 seconds and never repeated."},
    {"category": "Mysteries", "emoji": "🕵️", "title": "The ancient computer 2,000 years ahead of its time", "hook": "The Antikythera mechanism predicted eclipses before clocks existed."},
    {"category": "Mysteries", "emoji": "🕵️", "title": "The lost city that might actually be Atlantis", "hook": "Real ruins keep dragging the legend back to life."},

    # Human Body & Mind
    {"category": "Body & Mind", "emoji": "🧠", "title": "What happens in the seconds after you die", "hook": "The brain may stay active far longer than anyone believed."},
    {"category": "Body & Mind", "emoji": "🧠", "title": "Why you forget your dreams within minutes", "hook": "Your brain is wired to erase them on purpose."},
    {"category": "Body & Mind", "emoji": "🧠", "title": "The organ scientists only just discovered inside you", "hook": "Hiding in plain sight for centuries until 2018."},
    {"category": "Body & Mind", "emoji": "🧠", "title": "Why you can't tickle yourself", "hook": "Your brain cancels the sensation before it even happens."},

    # Ancient World
    {"category": "Ancient World", "emoji": "🏛️", "title": "How the pyramids were really built", "hook": "New evidence overturns almost everything you were taught."},
    {"category": "Ancient World", "emoji": "🏛️", "title": "The Roman concrete that heals its own cracks", "hook": "Stronger after 2,000 years than the cement we pour today."},
    {"category": "Ancient World", "emoji": "🏛️", "title": "The 12,000-year-old temple that rewrites history", "hook": "Göbekli Tepe was built before farming was even invented."},
    {"category": "Ancient World", "emoji": "🏛️", "title": "The library that held all of humanity's knowledge", "hook": "And the fire that erased it from history forever."},

    # What If
    {"category": "What If", "emoji": "⚡", "title": "What if the Earth stopped spinning for 5 seconds", "hook": "The consequences would be catastrophic and instant."},
    {"category": "What If", "emoji": "⚡", "title": "What if you fell into a hole through the Earth", "hook": "Physics gives a far stranger answer than you'd expect."},
    {"category": "What If", "emoji": "⚡", "title": "What if the Sun disappeared right now", "hook": "You wouldn't even notice for eight whole minutes."},
    {"category": "What If", "emoji": "⚡", "title": "What if every human jumped at the exact same time", "hook": "The Earth barely flinches — here's the math."},

    # Hidden Micro World
    {"category": "Micro World", "emoji": "🔬", "title": "The animal that can survive in outer space", "hook": "Tardigrades are basically impossible to kill."},
    {"category": "Micro World", "emoji": "🔬", "title": "How many bacteria are living on your phone", "hook": "More than you'd find on a public toilet seat."},
    {"category": "Micro World", "emoji": "🔬", "title": "What a single drop of pond water really contains", "hook": "An entire alien-looking universe you can't see."},

    # Future & Tech
    {"category": "Future & Tech", "emoji": "🤖", "title": "The AI that taught itself to do the impossible", "hook": "And the researchers still can't fully explain how."},
    {"category": "Future & Tech", "emoji": "🤖", "title": "Why scientists want to bring back the woolly mammoth", "hook": "De-extinction is far closer than you think."},
    {"category": "Future & Tech", "emoji": "🤖", "title": "The material thinner than paper, stronger than steel", "hook": "Graphene could quietly rebuild the entire world."},
]


def get_categories():
    """Return ["All", <unique categories in first-seen order>]."""
    seen = []
    for t in CURIOSITY_TOPICS:
        if t["category"] not in seen:
            seen.append(t["category"])
    return ["All"] + seen


def select_curiosity_topic(exclude_topics=None, category="All"):
    """Pick one curiosity topic, honoring an optional category filter and
    avoiding recently-used titles.

    Returns the topic dict ({category, emoji, title, hook}) or ``None`` if the
    library is empty. Falls back to the full (unfiltered-by-recency) pool if
    every candidate in the category has been used recently.
    """
    exclude = {str(t).strip().lower() for t in (exclude_topics or [])}

    if category and category not in ("All", ""):
        pool = [t for t in CURIOSITY_TOPICS if t["category"] == category]
    else:
        pool = list(CURIOSITY_TOPICS)

    if not pool:
        pool = list(CURIOSITY_TOPICS)
    if not pool:
        return None

    fresh = [t for t in pool if t["title"].strip().lower() not in exclude]
    return random.choice(fresh or pool)
