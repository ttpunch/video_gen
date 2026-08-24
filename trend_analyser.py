"""Multi-source trend analysis and topic recommendation.

Replaces the previous approach of *ranking* ~10 scraped Google Trends headlines,
which produced two problems the user could see directly:

  * **Limited pool.** Google Trends returns news events -- criminal trials,
    sports scores, personal names -- which make weak curiosity shorts, and there
    are only ever ~10-20 of them. Combined with a 31-entry static curiosity
    library, the supply of usable ideas ran out fast.
  * **Repetition.** ``recommend_viral_topics`` passed already-used topics to the
    LLM as a soft "do not pick these" instruction. The model complied literally
    and re-worded the same subject, so the library accumulated
    "95% of the Ocean Remains Unseen", "We've Explored Less Than 5% of the
    Ocean", "We've Barely Scratched Our Own Ocean" and two more ocean variants.

So this module *generates* topics instead of only ranking scraped ones, and
enforces novelty with a hard keyword filter rather than trusting the prompt.
``script_utils.topics_overlap`` already detects every one of those ocean
duplicates; it simply was not wired into this path.
"""
import datetime
import json
import os
import random

import requests

from script_utils import topics_overlap

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

_UA = {"User-Agent": "video-gen-trend-analyser/1.0"}

#: Emergency fallback ONLY, used when domain discovery fails (LLM down).
#: These are deliberately not the working set: a fixed list caps what can ever
#: be suggested, which is the same "limited topics" problem as the old static
#: curiosity library, just one level up. Real domains are invented per call by
#: :func:`discover_domains` so the subject space stays open-ended.
FALLBACK_DOMAINS = [
    "space and astronomy", "the deep ocean", "ancient history and archaeology",
    "the human body and brain", "animals and nature", "physics and 'what if'",
    "microscopic life", "technology and AI", "psychology and behaviour",
    "geology and extreme places", "food science", "aviation and engineering",
    "mathematics and patterns", "weather and natural phenomena",
    "medicine and biology", "language and writing systems",
]

#: Random exploration seeds. Injecting one steers the model into a different
#: corner of its knowledge each call. Without a nudge like this, an open-ended
#: "invent subject areas" request converges on the same handful of popular
#: science themes every time -- the model's own bias becomes the new limit.
_EXPLORATION_SEEDS = [
    "everyday objects with hidden histories", "things that are older than you'd guess",
    "processes that happen too slowly to see", "professions almost nobody knows exist",
    "measurements and units with strange origins", "things that only happen at extreme scale",
    "accidents that turned into inventions", "rules of nature that feel wrong",
    "places humans cannot go", "skills that took centuries to develop",
    "systems that quietly run the modern world", "things that were normal and are now illegal",
    "the physics of ordinary moments", "what happens after something ends",
    "records that will probably never be broken", "connections between unrelated fields",
    "things that look designed but are not", "the origin of a word or symbol",
    "how something familiar is actually made", "phenomena visible only from space",
]


def fetch_wikipedia_trending(limit=25, days_back=2):
    """Most-viewed English Wikipedia articles: what people are actively curious about.

    Free and keyless. Filtered to drop the scaffolding pages and the celebrity /
    film churn that dominates the raw list and makes poor curiosity material.
    """
    day = datetime.date.today() - datetime.timedelta(days=days_back)
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
           f"en.wikipedia/all-access/{day.year}/{day.month:02d}/{day.day:02d}")
    skip_prefixes = ("Main_Page", "Special:", "Wikipedia:", "Portal:", "Category:",
                     "Help:", "Talk:", "File:", "Template:")
    try:
        resp = requests.get(url, headers=_UA, timeout=15)
        if resp.status_code != 200:
            return []
        articles = resp.json()["items"][0]["articles"]
    except Exception:
        return []

    out = []
    for a in articles:
        name = a.get("article", "")
        if not name or name.startswith(skip_prefixes):
            continue
        out.append({"title": name.replace("_", " "), "views": a.get("views", 0)})
        if len(out) >= limit:
            break
    return out


def gather_signals(geo="US"):
    """Collect what is currently drawing attention, from every free source.

    Every source is best-effort: a dead source must degrade the *grounding*, not
    fail the recommendation, because the LLM can still generate good evergreen
    topics from the domain list alone.
    """
    signals = {"trends": [], "wikipedia": []}
    try:
        from viral_agent import fetch_google_trends
        signals["trends"] = fetch_google_trends(geo) or []
    except Exception as e:
        print(f"[trend_analyser] Google Trends unavailable: {e}")
    try:
        signals["wikipedia"] = fetch_wikipedia_trending()
    except Exception as e:
        print(f"[trend_analyser] Wikipedia unavailable: {e}")
    return signals


def is_novel(title, used_topics, accepted=()):
    """True when ``title`` shares no significant keyword with prior or peer topics.

    This is the hard filter the prompt-only approach lacked. It is deliberately
    strict: a single shared significant keyword ("ocean") is enough to reject,
    because that is exactly the axis along which the duplicates accumulated.
    """
    if not title:
        return False
    for prior in list(used_topics or []) + list(accepted):
        if topics_overlap(title, prior):
            return False
    return True


def discover_domains(model, count, avoid_topics=None, focus="", timeout=120):
    """Ask the model to invent ``count`` distinct subject areas for this batch.

    Generating the domains instead of picking from a constant is what keeps the
    topic space open: any subject the model knows about is reachable, rather
    than only the sixteen someone thought of up front.

    A random exploration seed is injected because an unseeded "invent subject
    areas" prompt collapses onto the same popular-science themes on every call
    -- which would just reproduce the limitation in a less visible form.
    """
    seed = random.choice(_EXPLORATION_SEEDS)
    parts = [
        f"List exactly {count} WIDELY DIFFERENT subject areas suitable for "
        "short educational videos.",
        "",
        f"For inspiration this round, lean toward: {seed}.",
        "",
        "RULES:",
        "- Each area must come from a genuinely different field. No two may share a domain.",
        "- Be specific: 'how bridges resist wind' beats 'engineering'.",
        "- Range widely: not only popular science. Craft, industry, language, "
        "  art, agriculture, logistics, sport, music and daily life all qualify.",
        "- Avoid violence, crime, disasters, politics and medical advice.",
    ]
    if focus:
        parts += ["", f"All areas must relate to this interest: {focus}."]
    if avoid_topics:
        parts += ["", "Steer away from the subjects of these recent videos:",
                  "\n".join(f"- {t}" for t in list(avoid_topics)[:20])]
    parts += ["", 'Respond ONLY with JSON: {"areas":["...","..."]}']

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": model, "prompt": "\n".join(parts),
                  "stream": False, "format": "json"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        from search_helper import clean_json_response
        areas = json.loads(
            clean_json_response(resp.json().get("response", "").strip())
        ).get("areas")
        # Models sometimes return identifier-style names ("stamp_collecting"),
        # which read badly when interpolated into the topic prompt.
        areas = [str(a).replace("_", " ").strip() for a in (areas or []) if str(a).strip()]
        if areas:
            return areas[:count]
        raise RuntimeError("no areas returned")
    except Exception as e:
        # Falling back keeps recommendations working when the LLM is flaky; the
        # cost is a narrower subject space for that one call, not a failure.
        print(f"[trend_analyser] domain discovery failed ({e}); using fallback list")
        pool = list(FALLBACK_DOMAINS)
        random.shuffle(pool)
        return pool[:count]


def _build_prompt(domains, signals, used_topics, count, performance_hint=""):
    """Prompt the model to INVENT curiosity topics inside given domains.

    Two deliberate choices, both aimed at variety:
      * Domains are named explicitly and one topic is requested per domain, so
        the model cannot return five variations of whatever subject it likes.
      * Trend signals are supplied as optional *inspiration* rather than the
        candidate set, so a thin or news-heavy trend feed cannot drag every
        suggestion toward a court case or a cricket score.
    """
    trend_lines = "\n".join(
        f"- {t['title']}" for t in (signals.get("trends") or [])[:10]
    )
    wiki_lines = "\n".join(
        f"- {w['title']}" for w in (signals.get("wikipedia") or [])[:12]
    )

    parts = [
        "You are a viral content strategist for YouTube Shorts.",
        f"Invent exactly {count} ORIGINAL video topics, each built on a genuine "
        "curiosity gap -- a question the viewer feels compelled to see answered.",
        "",
        "REQUIREMENTS:",
        "- One topic per assigned subject area. Do NOT give two topics on the same subject.",
        "- Each must be a concrete, surprising, *verifiable* fact or phenomenon.",
        "- Phrase as a short hook-style title (max 10 words), not a news headline.",
        "- Must be visually illustrable with real stock footage.",
        "",
        "REJECT: violence, death, crime, disasters, war, politics, scandal, "
        "adult themes, and any medical or health advice.",
        "",
        "ASSIGNED SUBJECT AREAS (one topic each, in order):",
    ]
    parts += [f"{i + 1}. {d}" for i, d in enumerate(domains)]

    if trend_lines:
        parts += ["", "Currently trending (optional inspiration only -- ignore "
                      "anything that is a news event, a person, or a sports result):",
                  trend_lines]
    if wiki_lines:
        parts += ["", "Currently being looked up (optional inspiration only):", wiki_lines]

    if used_topics:
        parts += ["", "ALREADY COVERED -- pick clearly different SUBJECTS, not "
                      "reworded versions of these:",
                  "\n".join(f"- {t}" for t in list(used_topics)[:25])]

    if performance_hint:
        parts += ["", performance_hint]

    parts += [
        "",
        'Respond ONLY with JSON, no markdown fences:',
        '{"topics":[{"title":"...","hook":"one-sentence curiosity hook",'
        '"niche":"science|space|history|tech|psychology|nature|...",'
        '"rpm_tier":"High|Medium|Low"}]}',
    ]
    return "\n".join(parts)


def generate_ideas(model, count=5, signals=None, used_topics=None,
                   performance_hint="", domains=None, focus="", timeout=180):
    """Ask the LLM for ``count`` fresh topics, one per rotated subject area.

    Raises on failure rather than returning junk: the previous code swallowed
    every error and silently fell back to raw trend headlines, so the UI showed
    "lindsay clancy trial live" as a *recommendation* with no indication that
    ranking had failed.
    """
    signals = signals or {}
    if domains:
        pool = list(domains)
        random.shuffle(pool)
        chosen = pool[:max(1, count)]
    else:
        # Discovered fresh each call, so the reachable subject space is not
        # capped by any list in this file.
        chosen = discover_domains(model, max(1, count),
                                  avoid_topics=used_topics, focus=focus)

    prompt = _build_prompt(chosen, signals, used_topics, count, performance_hint)
    resp = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama HTTP {resp.status_code}: {resp.text[:200]}")

    from search_helper import clean_json_response
    data = json.loads(clean_json_response(resp.json().get("response", "").strip()))
    topics = data.get("topics")
    if not isinstance(topics, list) or not topics:
        raise RuntimeError("model returned no topics")
    return topics


def analyse(geo="US", model="qwen2.5:7b-instruct", count=5,
            used_topics=None, performance_hint="", signals=None,
            focus="", max_attempts=3):
    """Return ``count`` novel, ranked topic recommendations.

    Generation is retried because the novelty filter is strict by design: a
    batch can lose several entries to keyword collisions, and asking again with
    a freshly shuffled domain set is cheaper and more effective than loosening
    the filter (loosening it is what let the ocean duplicates through).
    """
    from viral_agent import estimate_rpm

    used = list(used_topics or [])
    signals = signals if signals is not None else gather_signals(geo)

    accepted, errors = [], []
    for _ in range(max_attempts):
        if len(accepted) >= count:
            break
        try:
            raw = generate_ideas(
                model, count=count, signals=signals, used_topics=used,
                performance_hint=performance_hint, focus=focus,
            )
        except Exception as e:
            errors.append(str(e))
            continue

        for t in raw:
            if len(accepted) >= count:
                break
            title = (t.get("title") or "").strip()
            # Reject against BOTH history and the batch being built, so a single
            # response cannot contribute two topics on the same subject.
            if not is_novel(title, used, [a["title"] for a in accepted]):
                continue
            niche = (t.get("niche") or "general").strip().lower()
            accepted.append({
                "title": title,
                "rationale": (t.get("hook") or t.get("rationale") or "").strip(),
                "niche": niche,
                "rpm_tier": t.get("rpm_tier", "Medium"),
                "est_rpm": estimate_rpm(geo, niche),
                "geo": geo,
                "source": "generated",
            })

    if not accepted:
        detail = errors[-1] if errors else "every suggestion duplicated an existing topic"
        raise RuntimeError(f"Topic analysis produced nothing usable: {detail}")

    # High-RPM niches first; within a tier the model's own ordering is kept.
    tier_rank = {"high": 0, "medium": 1, "low": 2}
    accepted.sort(key=lambda r: tier_rank.get(str(r["rpm_tier"]).lower(), 1))
    return accepted
