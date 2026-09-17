"""
zenn_ideas.py — Doc 4: viral content ideation. Generates 10 click-worthy
content ideas for a chosen direction (finance / self-improvement / habits /
discipline / money mistakes / relationship / mental models), then hands over
the top picks for script generation.

Fully local-first: deterministic templates + Gemini scoring when available.
"""

import os, sys, json, re
sys.path.insert(0, '/root/stickman-fork')
from dotenv import load_dotenv
load_dotenv('/root/stickman-fork/.env')

DIRECTIONS = {
    "finance": "personal finance, investing, money psychology, money mistakes",
    "self-improvement": "procrastination, discipline, focus, habits, self-sabotage",
    "habits": "building and breaking habits, willpower, routines",
    "discipline": "self-discipline, doing hard things, consistency",
    "money-mistakes": "expensive financial mistakes and how to avoid them",
    "relationships": "relationship patterns, attachment, boundaries",
    "mental-models": "thinking frameworks that change decisions",
}

TITLE_FORMULAS = [
    "Why You Still {verb} Even Though You Know Better",
    "The Hidden Reason You {verb}",
    "You're Not Lazy. You're {bad_habit}.",
    "The {stake} Mistake Slowly Ruining Your {domain}",
    "Nobody Tells You This About {topic}",
    "The Psychology Behind {topic}",
    "The Brutal Truth About {topic}",
    "Why {glorified_thing} Feels Impossible",
    "What No One Admits About {topic}",
    "Stop Doing {bad_habit} If You Want {outcome}",
]

def _build_prompt(direction: str, n: int = 10):
    domain = DIRECTIONS.get(direction, direction)
    return f"""
You are an elite content strategist and behavioral psychologist for a minimalist
stickman explainer YouTube channel.

Generate exactly {n} compelling, click-driving content ideas in the domain:
"{domain}"

The audience is intelligent people who struggle with procrastination, lack of
discipline, overthinking, poor financial decisions, low confidence, wasted time,
addictive behaviors, and hidden self-sabotage.

For EACH idea provide a JSON object with fields:
  - title: a specific, emotionally loaded, curiosity-driven title (NOT generic
           tips/lists; use a strong structure like "Why You Keep ___ Even Though ___").
  - core_problem: the painful/frustrating problem it exposes.
  - hook: the unanswered question that makes someone click.
  - trigger: curiosity | fear | status | surprise | self-recognition |
             contradiction | loss-aversion | desire | identity | mystery.
  - unique_angle: what makes it different from generic videos.
  - transformation: what the viewer gains/avoids after watching.

Make the ideas vary: at least 3 challenge a common belief, at least 2 are
"I never realized I was doing this" reactions, at least 2 involve a costly
mistake, at least 2 promise a real transformation.

Respond with STRICT JSON ONLY: an object {{"ideas": [...]}}.
No markdown, no commentary.
"""

def generate_ideas(direction: str, n: int = 10, use_llm: bool = True):
    """Return list of idea dicts. Uses Gemini if available, else template fallback."""
    if use_llm:
        key = os.getenv("GEMINI_API_KEY")
        if key:
            try:
                from google import genai
                client = genai.Client(api_key=key)
                resp = client.models.generate_content(
                    model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                    contents=_build_prompt(direction, n))
                text = (resp.text or "").strip()
                # strip fences
                if text.startswith("```"):
                    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
                    text = re.sub(r"\n?```\s*$", "", text)
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if m:
                    data = json.loads(m.group(0))
                    return data.get("ideas", [])
            except Exception as e:
                print(f"[zenn] LLM ideation failed ({e}); using template fallback", file=sys.stderr)
    return _template_ideas(direction, n)


def _template_ideas(direction: str, n: int):
    topics = {
        "finance": [("compounding", "save", "compound interest", "wealth", "money"),
                    ("surviving paycheck to paycheck", "overspend", "spending", "finances", "money")],
        "self-improvement": [("procrastinating", "delay", "procrastination", "goals", "focus"),
                             ("you're not lazy", "quit", "motivation", "life", "discipline")],
    }.get(direction, [("it", "overthink", "overthinking", "life", "results")])
    base_t, verb, topic, domain, outcome = topics[0]
    ideas = []
    for i in range(n):
        sf = TITLE_FORMULAS[i % len(TITLE_FORMULAS)]
        title = (sf.format(verb=verb, bad_habit="procrastinating", stake="Small",
                           domain=domain, topic=topic, glorified_thing="the grind",
                           outcome=outcome) if "{" not in sf else
                 f"The Hidden Rule of {topic.title()} No One Follows")
        ideas.append({
            "title": title,
            "core_problem": f"You keep {verb} even though it costs you {domain}.",
            "hook": "What small, invisible habit is quietly sabotaging your results?",
            "trigger": "self-recognition",
            "unique_angle": f"A stickman explainer showing the real mechanism behind {topic}.",
            "transformation": f"Understand the {topic} trap and gain a practical escape",
        })
    return ideas


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("direction", nargs="?", default="self-improvement",
                    choices=list(DIRECTIONS)+["finance","self-improvement"])
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    ideas = generate_ideas(a.direction, a.n, use_llm=not a.no_llm)
    for i, it in enumerate(ideas, 1):
        print(f"{i}. {it.get('title')}")
        print(f"   Problem: {it.get('core_problem')}  |  Trigger: {it.get('trigger')}")
        print()