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
    pools = [
        ("why you keep {topic}", "you keep {verb} even though you know better",
         "the invisible habit quietly sabotaging your results",
         "self-recognition", "a mechanism, not weakness"),
        ("you're not lazy, you're {sab}", "you quit before the friction starts",
         "what the resistance actually is", "contradiction", "reframing self-blame"),
        ("the {cost} mistake ruining your {domain}", "a small daily choice compounds into a big cost",
         "the expensive error hiding in plain sight", "loss-aversion", "a costly trap avoided"),
        ("nobody tells you this about {topic}", "an unspoken truth that changes your decision",
         "what everyone gets wrong", "mystery", "a counterintuitive truth"),
        ("the psychology behind {topic}", "the mental mechanism runs you without you noticing",
         "the hidden driver", "curiosity", "seeing the mechanism"),
        ("what {topic} does to you over time", "the slow, invisible long-term effect",
         "what really happens month by month", "surprise", "long-term clarity"),
    ]
    verbs = {"finance": ["overspend","save","invest"], "self-improvement": ["procrastinate","delay","avoid"]}
    sab = {"finance": "overspending", "self-improvement": "procrastinating"}.get(direction, "stalling")
    cost = {"finance": "small money", "self-improvement": "small effort"}.get(direction, "small")
    topic = {"finance": "compound interest", "self-improvement": "procrastination"}.get(direction, "your habits")
    domain = {"finance": "wealth", "self-improvement": "potential"}.get(direction, "life")
    v = verbs.get(direction, ["miss"])
    ideas = []
    seen = set()
    i = 0
    while len(ideas) < n:
        pool = pools[i % len(pools)]
        title_tmpl, prob_tmpl, hook, trig, angle = pool
        title = title_tmpl.format(topic=topic, sab=sab, cost=cost, domain=domain)
        if title in seen:
            # vary the topic rendering to force uniqueness
            title = title_tmpl.format(
                topic=f"{topic} ({'the quiet side' if len(seen)%2 else 'the real driver'})",
                sab=sab, cost=cost, domain=domain)
        seen.add(title)
        ideas.append({
            "title": title,
            "core_problem": prob_tmpl.format(verb=v[len(seen) % len(v)], topic=topic),
            "hook": hook,
            "trigger": trig,
            "unique_angle": f"A minimalist stickman explainer exposing {angle}.",
            "transformation": "Recognize the real mechanism and gain a practical escape",
        })
        i += 1
    return ideas[:n]


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