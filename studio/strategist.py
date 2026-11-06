"""The 'brain': turns research + your analytics + your brand profile into reports, post ideas,
captions, bios and image prompts — all with a local model through Ollama."""
from __future__ import annotations

from .config import brand_brief
from .llm import chat, chat_json, chat_stream, parse_json, speed

SYSTEM = (
    "You are a senior social media strategist and creative director for independent clothing brands. "
    "You know Instagram, TikTok, Pinterest and X deeply: hooks, formats, the algorithms' preference for "
    "saves/shares/watch-time, drop culture, UGC, behind-the-scenes, styling content and community building. "
    "You are specific and practical. You never invent statistics; when you infer, say so. "
    "Always write in the brand's voice and respect its words-to-avoid list."
)

PLATFORM_NOTES = {
    "Instagram": "Caption hook in the first 125 characters (before 'more'). 3-8 targeted hashtags. Carousels and Reels perform best for saves/shares.",
    "TikTok": "Caption under 150 characters, conversational, 3-5 hashtags. The on-screen hook in the first 2 seconds matters most.",
    "Pinterest": "Keyword-rich title and description (it's a search engine). No slang-only text. 2-5 hashtags max.",
    "X": "Under 280 characters. Punchy. 0-2 hashtags.",
    "Facebook": "Conversational, a clear question or CTA, 0-3 hashtags.",
    "YouTube": "Shorts: punchy title under 60 characters with the hook, description of 1-3 sentences plus 3 hashtags. Long-form: searchable title, first 2 lines of the description sell the video.",
}

BIO_LIMITS = {"Instagram": 150, "TikTok": 80, "X": 160, "Pinterest": 500, "Facebook": 101, "YouTube": 1000}


def _report_prompt(brand: dict, digest: str, analytics_text: str = "", notes: str = "") -> str:
    return f"""{brand_brief(brand)}

=== FRESH RESEARCH (web, news, Reddit, fashion press) ===
{digest or '(none gathered)'}

=== THE BRAND'S OWN ANALYTICS ===
{analytics_text or '(no analytics uploaded)'}

=== OWNER'S NOTES (competitor observations, things seen on IG/TikTok, goals) ===
{notes or '(none)'}

Write a research brief in Markdown for this brand with these sections:
## Trends worth acting on
(5-7 bullets: the trend, evidence from the research above, and how THIS brand could use it. Skip trends that don't fit the brand.)
## What the audience is talking about
(themes, complaints, wants — mostly from Reddit/community posts)
## What's working on your own account
(only if analytics were provided: formats, timing, hashtags, caption style — cite the numbers)
## Competitor & inspiration takeaways
## Content pillars for the next 30 days
(3-5 pillars, each with a one-line description and suggested % of posts)
## Posting plan
(how often, which formats, best days/times — use analytics if present, otherwise say it's a starting point to test)
## Avoid
(3 things not to do right now)
"""


def research_report(brand: dict, digest: str, analytics_text: str = "", notes: str = "") -> str:
    return chat(SYSTEM, _report_prompt(brand, digest, analytics_text, notes), temperature=0.5)


def research_report_stream(brand: dict, digest: str, analytics_text: str = "", notes: str = ""):
    """Yield pieces of the brief as the model writes them."""
    yield from chat_stream(SYSTEM, _report_prompt(brand, digest, analytics_text, notes), temperature=0.5)


IDEA_SCHEMA = """{
  "title": "short name",
  "format": "Reel | Carousel | Single image | Story | TikTok video | YouTube Short | Pin",
  "pillar": "which content pillar",
  "hook": "the first line / first 2 seconds",
  "concept": "what happens in the post, 2-3 sentences",
  "shot_list": ["shot or slide 1", "shot or slide 2", "..."],
  "image_prompt": "detailed prompt for an AI image generator for the hero visual: subject, clothing, setting, lighting, camera, mood, colors. Photographic, no text in the image.",
  "overlay_text": "max 6 words of headline text to put on the graphic, or empty",
  "caption": "full caption in brand voice, platform-appropriate length",
  "hashtags": ["#tag", "..."],
  "cta": "call to action",
  "best_time": "suggested day/time and why",
  "why_it_works": "one sentence tied to the research"
}"""


def _ideas_prompt(brand, report, n, platform, goal, extra, avoid=None, build_on=None) -> str:
    report_chars = 3000 if speed()["ctx"] <= 4096 else 6000
    memory = ""
    if avoid:
        memory += "\nAlready posted (do NOT repeat these, find fresh angles):\n" + "\n".join(f"- {t}" for t in avoid[:25])
    if build_on:
        memory += "\nThe owner's favorite past ideas (match their spirit, don't copy them):\n" + "\n".join(f"- {t}" for t in build_on[:10])
    return f"""{brand_brief(brand)}

=== LATEST RESEARCH BRIEF ===
{report[:report_chars] or '(no research yet - rely on general best practice and the brand profile)'}
{memory}

Goal for these posts: {goal}
Main platform: {platform}. {PLATFORM_NOTES.get(platform, '')}
Extra direction from the owner: {extra or 'none'}

Create {n} distinct post ideas ranked from strongest to weakest. Mix formats. Return JSON:
{{"ideas": [{IDEA_SCHEMA}]}}"""


def _clean_ideas(data, n):
    ideas = data.get("ideas", data) if isinstance(data, dict) else data
    if isinstance(ideas, dict):
        ideas = [ideas]
    return [i for i in ideas if isinstance(i, dict)][:n]


def post_ideas(brand: dict, report: str, n: int = 6, platform: str = "Instagram",
               goal: str = "Grow engagement", extra: str = "", avoid=None, build_on=None) -> list[dict]:
    data = chat_json(SYSTEM, _ideas_prompt(brand, report, n, platform, goal, extra, avoid, build_on), temperature=0.8)
    return _clean_ideas(data, n)


def post_ideas_stream(brand: dict, report: str, n: int = 6, platform: str = "Instagram",
                      goal: str = "Grow engagement", extra: str = "", avoid=None, build_on=None):
    """Yields ("progress", chars_so_far) while writing, then ("done", ideas)."""
    raw = ""
    for piece in chat_stream(SYSTEM, _ideas_prompt(brand, report, n, platform, goal, extra, avoid, build_on),
                             temperature=0.8, json_mode=True):
        raw += piece
        yield "progress", len(raw)
    yield "done", _clean_ideas(parse_json(raw), n)


def remix_idea(brand: dict, idea: dict, direction: str = "", platform: str = "") -> dict:
    """A fresh variation of a saved idea: new hook, new angle, same core."""
    import json as _json
    plat = platform or "the same platform"
    user = f"""{brand_brief(brand)}

Here is a past post idea the owner wants to reuse:
{_json.dumps({k: idea.get(k) for k in ("title", "format", "hook", "concept", "caption", "cta")}, ensure_ascii=False)}

Remix it into ONE new post for {plat}: keep what made it work, but give it a new hook, a fresh angle and a new caption
so the audience doesn't feel it's a repeat. Direction from the owner: {direction or 'surprise me'}.
{PLATFORM_NOTES.get(platform, '')}
Return JSON with exactly these keys: {IDEA_SCHEMA}"""
    data = chat_json(SYSTEM, user, temperature=0.9)
    ideas = _clean_ideas(data, 1)
    if not ideas:
        raise ValueError("The model didn't return an idea. Try again.")
    return ideas[0]


def captions(brand: dict, description: str, platform: str, tone: str, n: int = 3,
             include_hashtags: bool = True, report: str = "") -> str:
    user = f"""{brand_brief(brand)}

Trend context (optional): {report[:3000] or 'n/a'}

Write {n} different captions for this post on {platform}: {description}
Tone tweak: {tone}. {PLATFORM_NOTES.get(platform, '')}
{'Add a hashtag set to each (mix of core brand tags, niche tags and 1-2 broader tags).' if include_hashtags else 'No hashtags.'}
Label them **Option 1**, **Option 2**... and for each add one line in italics on why the hook works.
Also give 3 alt-text descriptions for accessibility at the end under **Alt text**."""
    return chat(SYSTEM, user, temperature=0.9)


def bios(brand: dict, platform: str, n: int = 5, focus: str = "") -> str:
    limit = BIO_LIMITS.get(platform, 150)
    user = f"""{brand_brief(brand)}

Write {n} profile bios for {platform}. HARD LIMIT: {limit} characters each including emojis and line breaks.
Focus / current campaign: {focus or 'general brand bio'}.
Each should say what the brand is, who it's for, and include a reason to tap the link.
Format: numbered list, then the character count in brackets after each."""
    text = chat(SYSTEM, user, temperature=0.9)
    return text + f"\n\n_Limit for {platform}: {limit} characters. Double-check counts before pasting._"


def improve_image_prompt(brand: dict, idea: str) -> str:
    user = f"""{brand_brief(brand)}

Turn this post idea into ONE image-generation prompt (max 70 words) for a photorealistic image that
matches the brand's visual style. Describe clothing precisely (garment, fit, fabric, color), the model/pose,
setting, lighting, lens and film look. Do not include any text, logos or words in the image.
Idea: {idea}
Return only the prompt."""
    return chat(SYSTEM, user, temperature=0.6).strip().strip('"')


def ideas_markdown(ideas: list[dict]) -> str:
    out = []
    for i, d in enumerate(ideas, 1):
        tags = " ".join(d.get("hashtags", []) if isinstance(d.get("hashtags"), list) else [str(d.get("hashtags", ""))])
        shots = d.get("shot_list") or []
        shots_md = "\n".join(f"   {j}. {s}" for j, s in enumerate(shots, 1)) if isinstance(shots, list) else str(shots)
        out.append(
            f"### {i}. {d.get('title','Idea')}  ·  _{d.get('format','')}_  ·  {d.get('pillar','')}\n"
            f"**Hook:** {d.get('hook','')}\n\n"
            f"{d.get('concept','')}\n\n"
            f"**Shot list / slides:**\n{shots_md}\n\n"
            f"**Caption:**\n> {str(d.get('caption','')).replace(chr(10), chr(10) + '> ')}\n\n"
            f"**Hashtags:** {tags}\n\n"
            f"**CTA:** {d.get('cta','')}  ·  **When:** {d.get('best_time','')}\n\n"
            f"**Why it works:** {d.get('why_it_works','')}\n\n"
            f"**Image prompt:** `{d.get('image_prompt','')}`\n\n---"
        )
    return "\n".join(out) or "_No ideas returned — try again._"
