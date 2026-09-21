"""
phase1_script.py  —  GEMINI (via API key), storyboard builder
=============================================================
Three ways to get the narration lines (ZENN_WRITER_MODE or `mode=`):

  flat    (default)  topic -> N lines in one call              (short explainers)
  levels             topic -> outline (hook / LEVELS / payoff) -> ONE call per section,
                     each seeing all previous lines            (long-form "every level of X")
  file               lines come from an approved script (`lines_file=`, see spec §9 lines.json)

Then always:
  DIRECTOR   lines -> one structured visual beat per line
             (subject / action / object / setting / shot / pose / presence / props)
  validate audio-match -> repair failing scenes -> render beats into `scene_prompt`
  story_lint on the narration (repeats, caption-style lines, id leaks, few numbers)

Why "levels": one giant call for ~100 lines drifts and loops (a real storyboard
repeated its opening "alarm clock at 4am" 60 scenes later and spent 60% of the
runtime on the lowest level). Per-section calls with an explicit scene budget
and the full list of previous lines prevent that.

The narration lines are the single source of truth; `script` is their join.

Output: StoryBoard persisted to projects/<slug>/storyboard.json, plus
        beats.json (entities, beats, sections, lint, unresolved issues).

Env:
  GEMINI_API_KEY, STORYSB_GEMINI_MODEL / GEMINI_MODEL (default gemini-2.5-flash)
  ZENN_WRITER_MODE   flat | levels | file
  SCENE_COUNT / TARGET_SECONDS (50) / SEC_PER_SCENE (4)
  BEAT_REPAIR_ROUNDS (2)   LINT_REPAIR_ROUNDS (1)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from ..models import StoryBoard, Scene, slugify
from ..retry import with_retry
from zenn_style import (
    ASPECT,
    CHARACTER_SHORT,
    PROTAGONIST,
    REPAIRABLE,
    clean_text,
    enforce_shot_variety,
    entity_conflicts,
    fallback_beat,
    normalize_beat,
    one_line,
    render_action,
    story_lint,
    validate_beats,
)

log = logging.getLogger("stickman_studio.phase1")

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("STORYSB_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")).strip()
# OpenAI-compatible backend (e.g. freeinference.org, DeepSeek). Set LLM_BACKEND=openai
# to drive storyboarding through an OpenAI-chat endpoint instead of Gemini. Uses the
# same JSON schemas/prompts/director; only the transport changes.
LLM_BACKEND = os.getenv("LLM_BACKEND", "gemini").strip().lower()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip() or "https://freeinference.org/v1"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", os.getenv("STORYSB_GEMINI_MODEL", "deepseek-v4-flash")).strip()
TARGET_SECONDS = float(os.getenv("TARGET_SECONDS", "50"))
SEC_PER_SCENE = float(os.getenv("SEC_PER_SCENE", "4"))
REPAIR_ROUNDS = int(os.getenv("BEAT_REPAIR_ROUNDS", "2"))
LINT_ROUNDS = int(os.getenv("LINT_REPAIR_ROUNDS", "1"))
WRITER_MODE = os.getenv("ZENN_WRITER_MODE", "flat").strip().lower()

_STR = {"type": "string"}
_ENTITIES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"id": _STR, "description": _STR},
        "required": ["id", "description"],
    },
}
_LINES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"title": _STR, "narration": _STR},
        "required": ["title", "narration"],
    },
}
_WRITER_SCHEMA = {
    "type": "object",
    "properties": {"lines": _LINES_SCHEMA, "entities": _ENTITIES_SCHEMA},
    "required": ["lines", "entities"],
}
_SECTION_SCHEMA = {"type": "object", "properties": {"lines": _LINES_SCHEMA}, "required": ["lines"]}
_OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": _STR, "role": _STR, "name": _STR, "label": _STR,
                    "scenes": {"type": "integer"}, "arc": _STR,
                },
                "required": ["id", "role", "name", "scenes", "arc"],
            },
        },
        "entities": _ENTITIES_SCHEMA,
    },
    "required": ["sections", "entities"],
}
_DIRECTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "subject": _STR, "action": _STR, "object": _STR, "setting": _STR,
                    "shot": _STR, "pose": _STR, "presence": _STR,
                    "props": {"type": "array", "items": _STR},
                    "entities": {"type": "array", "items": _STR},
                    "metaphor": {"type": "boolean"},
                    "on_screen_text": _STR,
                },
                "required": ["index", "subject", "action", "object", "setting", "shot"],
            },
        }
    },
    "required": ["beats"],
}

# ------------------------------------------------------------------ prompts
_ENTITY_RULES = """\
ENTITIES: list 0-4 recurring non-character things (objects, places, creatures) that appear in 2+ lines. Give each a short snake_case id and a fixed visual description of at most 20 words.
- Entities must NOT be anything the protagonist wears or carries as part of his/her fixed look (clothes, shoes, hair): the protagonist's look is locked elsewhere.
- NEVER use an entity id in the narration. Write plain words ("your worn sneakers" is wrong if it contradicts the locked outfit; "the timeclock", never "red_timeclock").
"""

_WRITER_SYSTEM = """\
You write narration for fast-cut animated explainers (Ink Explainer style).

RULES
1. Line 1 is the HOOK: a shocking fact, a weird question, or an extreme situation. Never "Today we will learn...".
2. Write EXACTLY the requested number of lines. Each line is ONE spoken beat of 8-14 words (1-2 short sentences) that will become ONE picture.
3. DRAWABLE: every line names a concrete thing that can be pictured and a physical action. Name the subject explicitly. Never start a line with "It", "This", "They" or "That".
4. ARC: hook -> escalating beats -> payoff or twist in the last lines. Every line adds NEW information; never restate an earlier line.
5. Plain spoken language. No stage directions, emoji, hashtags or visual instructions.
6. Vary how lines begin; no more than a third of them may start with the same word.

""" + _ENTITY_RULES + "Also give each line a 2-4 word title.\n"

_OUTLINE_SYSTEM = """\
You plan a narrated second-person POV explainer ("your life at every level of X").

STRUCTURE (sections in order): one `hook`, then 6-10 `level` sections in strictly ascending order, then one `payoff`.
- Every level has a `label` (its stage, e.g. an income bracket or milestone; labels are placeholders that will be fact-checked later) and a distinct `arc`: the single emotional situation and money decision that only THIS level has.
- The hook is a striking moment, NOT a recap of the lowest level. The payoff reframes the ladder.
- Level scene budgets must be comparable (within about +/-30% of each other). The `scenes` values MUST sum to the requested total.
- No level may reuse another level's situations or images (no repeated alarm clocks, wallets, buses, etc.).
- Use only numbers that appear in a label. Do not invent statistics.

""" + _ENTITY_RULES

_SECTION_SYSTEM = """\
You write narration for ONE section of a second-person POV explainer, spoken by a calm narrator.

RULES
1. Address the viewer as "you", present tense. Write what happens TO YOU and what it costs or means. Do NOT write image captions ("A rusty clock rings...").
2. Each line is one spoken beat of 9-16 words containing ONE concrete, drawable image.
3. Vary sentence openers. At most 30% of lines may start with the same word.
4. The first line of a `level` section names the level using its label. A `hook` opens with a striking moment; a `payoff` reframes the whole ladder.
5. Never repeat or paraphrase an image, object, place or action from PREVIOUS LINES. Do not restate the outline.
6. Numbers only from the section label. Never invent statistics.
7. Never write ids with underscores; plain words only.
8. Give each line a 2-4 word title.
Write EXACTLY the requested number of lines.
"""

_DIRECTOR_SYSTEM = """\
You are the visual director for an animated explainer. For each narration line, output ONE visual beat that a text-to-image model can draw.
The protagonist is always called "{P}". His/her look is injected later: NEVER describe face, body or clothes.

FIELDS (keep each under 12 words, plain words):
- subject: who or what performs the action ("{P}" when the protagonist acts)
- action: one concrete physical verb phrase. Do NOT repeat the object inside it.
- object: what the action acts on (may be empty). Do NOT repeat it inside `action` or `setting`.
- setting: the LOCATION ONLY, a short phrase starting with in / on / at ("in a dim garage"). Never repeat the object.
- shot: one of: wide shot, medium shot, close-up, top-down view, side view, low-angle view
- pose: the protagonist's mood if he/she is visible ("exhausted", "smug"); empty if not visible. Avoid "neutral".
- presence: full | partial | none.
    full    = the protagonist is clearly visible and matters to the picture.
    partial = first-person POV: only the protagonist's hands/arms are visible (use for things happening TO the viewer or held in hand).
    none    = the protagonist does not appear (pure object/environment moments). Prefer this over forcing a bystander pose.
- props: up to 3 extra visible objects
- entities: ids from the ENTITIES list that appear in the frame (ids only here, never in other fields)
- metaphor: true only if the line is abstract and you drew a concrete stand-in
- on_screen_text: normally empty; at most 3 words and only if a label is essential

RULES
1. AUDIO-MATCH: reuse the literal nouns and verbs of the narration line in subject / action / object.
2. ABSTRACT LINE (nothing drawable): choose ONE concrete visual metaphor, set metaphor=true, and still name the line's key noun in `object`.
3. ONE visual idea per scene. Physical comedy is welcome when the line supports it.
4. Never draw anything the line does not mention, apart from setting and props that make the scene readable.
5. Every beat stands alone: no "again", "as before".
6. Vary `shot` and `presence`. Never use the same shot three scenes in a row.
7. Never put speech, captions, signs or writing in the picture.
8. Never use underscores anywhere.
"""


# ------------------------------------------------------------------ Gemini/OpenAI plumbing
def _call_openai(client, prompt: str, system: str, schema: dict | None = None) -> str:
    # OpenAI-compatible models ignore Gemini's response_schema; force JSON output.
    shape_hint = ""
    if schema and isinstance(schema, dict):
        if schema.get("type") == "object":
            props = ", ".join(schema.get("properties", {}).keys())
            shape_hint = (f"\nIMPORTANT: respond with exactly ONE JSON object "
                          f"with keys: {props}. No markdown, no code fences, no extra text.")
            # if it wraps an array property, describe the inner element shape
            for pk, pv in (schema.get("properties") or {}).items():
                if isinstance(pv, dict) and pv.get("type") == "array" and isinstance(pv.get("items"), dict):
                    item = pv["items"]
                    if item.get("type") == "object":
                        ikeys = ", ".join(item.get("properties", {}).keys())
                        shape_hint += (f" The '{pk}' value must be an array of JSON objects, "
                                       f"each with keys: {ikeys}."
                                       if ikeys else "")
        elif schema.get("type") == "array":
            shape_hint = ("\nIMPORTANT: respond with exactly ONE JSON array of objects. "
                          "No markdown, no code fences, no extra text.")
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt + shape_hint}]
    kw = dict(model=OPENAI_MODEL, messages=msgs, temperature=0.4, max_tokens=16384)
    try:
        kw["response_format"] = {"type": "json_object"}
    except Exception:  # noqa: BLE001
        pass
    resp = client.chat.completions.create(**kw)
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("LLM returned an empty response (blocked or truncated).")
    return text


def _call(client, prompt: str, system: str, schema: dict | None) -> str:
    if LLM_BACKEND == "openai":
        return _call_openai(client, prompt, system, schema)
    from google.genai import types

    cfg = dict(
        temperature=0.4,
        max_output_tokens=16384,  # 2.5 "thinking" tokens count against this budget
        system_instruction=system,
        response_mime_type="application/json",
    )
    if schema:
        cfg["response_schema"] = schema
    resp = client.models.generate_content(
        model=MODEL, contents=prompt, config=types.GenerateContentConfig(**cfg)
    )
    text = resp.text
    if not text:
        raise RuntimeError("Gemini returned an empty response (blocked or truncated).")
    return text


@with_retry
def _generate(client, prompt: str, system: str, schema: dict | None = None) -> str:
    """One Gemini call. Uses the response schema; if the API rejects it, retry once without."""
    try:
        return _call(client, prompt, system, schema)
    except Exception as e:  # noqa: BLE001
        if schema is None:
            raise
        log.warning("Schema-constrained call failed (%s); retrying without schema.", e)
        return _call(client, prompt, system, None)


def _extract_json(raw: str):
    """Robustly pull a JSON object OR array out of Gemini output (handles fences/prefix).

    NOTE: this is a minimal robustness fix I added during integration — the version
    you uploaded only extracted a top-level object `{...}`, but the section writer
    sometimes returns a bare top-level array `[...]`, which crashed with
    "Extra data". This version also slices a balanced top-level array.
    """
    s = raw.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].strip().lstrip("#").strip().lower().startswith("json"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    # Branch on the outer container FIRST (an array contains '{', so the object
    # check below must not fire first on array bodies).
    if s[:1] == "[":
        aa, bb = s.find("["), s.rfind("]")
        if bb > aa:
            return json.loads(s[aa : bb + 1])
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b != -1 and b > a:
        return json.loads(s[a : b + 1])
    return json.loads(s)


def _json_call(client, prompt: str, system: str, schema: dict) -> dict:
    raw = _generate(client, prompt, system, schema)
    try:
        return _extract_json(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse Gemini JSON: {e}\n--- raw ---\n{raw[:2000]}")


def _entities(items) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(items, dict):
        items = [{"id": k, "description": v} for k, v in items.items()]
    for e in items or []:
        eid = "".join(c if c.isalnum() else "_" for c in one_line(e.get("id")).lower()).strip("_")
        desc = one_line(e.get("description"))
        if eid and desc:
            out[eid] = desc
    return out


def _lines(items, want: int | None = None) -> list[dict]:
    out = [
        {"title": clean_text(x.get("title")) or f"Scene {i + 1}", "narration": clean_text(x.get("narration"))}
        for i, x in enumerate(items or [])
        if clean_text(x.get("narration"))
    ]
    if want and len(out) > want + 1:
        out = out[:want]
    return out


# ------------------------------------------------------------------ writers
def _write_flat(client, topic: str, n: int):
    prompt = (
        f'TOPIC: "{topic}"\n\n'
        f"Write EXACTLY {n} lines (about {TARGET_SECONDS:.0f} seconds of narration) and the ENTITIES list."
    )
    data = _json_call(client, prompt, _WRITER_SYSTEM, _WRITER_SCHEMA)
    lines = _lines(data.get("lines"))
    if not lines:
        raise RuntimeError("Gemini returned zero narration lines — cannot build video.")
    if len(lines) != n:
        log.warning("Writer returned %d lines, wanted %d — continuing with %d.", len(lines), n, len(lines))
    for x in lines:
        x.update(section_id=None, level_id=None)
    return lines, _entities(data.get("entities"))


def _fit_budgets(sections: list[dict], n: int) -> list[dict]:
    """Force scene budgets to sum to n (>=2 each), proportionally."""
    for s in sections:
        s["scenes"] = max(2, int(s.get("scenes") or 0))
    total = sum(s["scenes"] for s in sections)
    if total != n:
        scale = n / total
        for s in sections:
            s["scenes"] = max(2, round(s["scenes"] * scale))
        diff = n - sum(s["scenes"] for s in sections)
        big = sorted(sections, key=lambda s: -s["scenes"])
        i = 0
        while diff != 0 and big:
            s = big[i % len(big)]
            if diff > 0:
                s["scenes"] += 1
                diff -= 1
            elif s["scenes"] > 2:
                s["scenes"] -= 1
                diff += 1
            i += 1
            if i > 10000:
                break
    return sections


def _section_prompt(topic, sections, sec, prior: list[str], feedback: str = "") -> str:
    outline = "\n".join(
        f"- [{s['id']}] {s['role']}: {s['name']}" + (f" ({s['label']})" if s.get("label") else "") + f" — {s['arc']}"
        for s in sections
    )
    prev = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(prior)) or "(none yet)"
    out = (
        f'TOPIC: "{topic}"\n\nOUTLINE:\n{outline}\n\nPREVIOUS LINES (never repeat these images):\n{prev}\n\n'
        f"WRITE SECTION [{sec['id']}] — role={sec['role']}, name={sec['name']}, label={sec.get('label') or '-'}, "
        f"arc={sec['arc']}.\nWrite EXACTLY {sec['scenes']} lines."
    )
    if feedback:
        out += f"\n\nYour previous version was rejected: {feedback}\nWrite it again with completely different images."
    return out


def _write_levels(client, topic: str, n: int):
    plan = _json_call(
        client,
        f'PLAN THE OUTLINE for: "{topic}". Total scenes required: {n}.',
        _OUTLINE_SYSTEM,
        _OUTLINE_SCHEMA,
    )
    sections = []
    for i, s in enumerate(plan.get("sections") or []):
        sections.append({
            "id": "".join(c if c.isalnum() else "_" for c in one_line(s.get("id") or f"s{i + 1}").lower()).strip("_") or f"s{i + 1}",
            "role": one_line(s.get("role")).lower() or "level",
            "name": one_line(s.get("name")) or f"Section {i + 1}",
            "label": one_line(s.get("label")),
            "scenes": s.get("scenes") or 0,
            "arc": one_line(s.get("arc")),
        })
    if not sections:
        raise RuntimeError("Outline came back empty.")
    _fit_budgets(sections, n)
    entities = _entities(plan.get("entities"))
    log.info("Outline: %s", [(s["id"], s["scenes"]) for s in sections])

    written: dict[str, list[dict]] = {}

    def write(sec, prior, feedback=""):
        data = _json_call(client, _section_prompt(topic, sections, sec, prior, feedback), _SECTION_SYSTEM, _SECTION_SCHEMA)
        got = _lines(data.get("lines"), sec["scenes"])
        if len(got) != sec["scenes"]:
            log.warning("section %s: got %d lines, wanted %d", sec["id"], len(got), sec["scenes"])
        return got

    def flat() -> list[dict]:
        out = []
        for s in sections:
            for x in written.get(s["id"], []):
                out.append({**x, "section_id": s["id"], "level_id": s["id"] if s["role"] == "level" else None})
        return out

    prior: list[str] = []
    for sec in sections:
        written[sec["id"]] = write(sec, prior)
        prior += [x["narration"] for x in written[sec["id"]]]

    for rnd in range(LINT_ROUNDS):
        allines = flat()
        problems = [p for p in story_lint([x["narration"] for x in allines]) if p["code"] == "near_duplicates"]
        if not problems:
            break
        bad_sections = {allines[i - 1]["section_id"] for p in problems for i in p["scenes"] if 0 < i <= len(allines)}
        log.info("Lint round %d: rewriting sections with repeats: %s", rnd + 1, sorted(bad_sections))
        for sec in sections:
            if sec["id"] not in bad_sections:
                continue
            before = [x["narration"] for s in sections if s["id"] != sec["id"] for x in written.get(s["id"], [])]
            written[sec["id"]] = write(sec, before, problems[0]["msg"])

    lines = flat()
    if not lines:
        raise RuntimeError("Writer returned zero lines — cannot build video.")
    return lines, entities, sections


def _load_lines_file(path: Path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    lines = [
        {
            "title": clean_text(x.get("title")) or f"Scene {i + 1}",
            "narration": clean_text(x.get("text") or x.get("narration")),
            "section_id": x.get("section_id"),
            "level_id": x.get("level_id"),
        }
        for i, x in enumerate(data.get("lines") or [])
        if clean_text(x.get("text") or x.get("narration"))
    ]
    if not lines:
        raise RuntimeError(f"No lines found in {path}")
    return lines, _entities(data.get("entities"))


# ------------------------------------------------------------------ director
def _director_prompt(narrs, entities, todo, problems) -> str:
    ent = "\n".join(f"- {k}: {v}" for k, v in entities.items()) or "(none)"
    script = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(narrs))
    scope = "ALL scenes" if len(todo) == len(narrs) else "ONLY scenes " + ", ".join(str(i + 1) for i in todo)
    out = f"ENTITIES (reference by id in `entities`):\n{ent}\n\nFULL NARRATION (for context):\n{script}\n\nWrite beats for {scope}. Use the scene number as `index`."
    if problems:
        fix = "\n".join(f"- scene {i + 1}: " + " | ".join(m) for i, m in sorted(problems.items()))
        out += f"\n\nYour previous beats for these scenes were rejected. Fix them:\n{fix}"
    return out


def _direct(client, narrs, entities, todo, problems) -> dict[int, dict]:
    system = _DIRECTOR_SYSTEM.replace("{P}", PROTAGONIST)
    data = _json_call(client, _director_prompt(narrs, entities, todo, problems), system, _DIRECTOR_SCHEMA)
    items = data.get("beats") or []
    out: dict[int, dict] = {}
    for pos, item in enumerate(items):
        try:
            idx = int(item.get("index")) - 1
        except (TypeError, ValueError):
            idx = todo[pos] if len(items) == len(todo) and pos < len(todo) else -1
        if 0 <= idx < len(narrs):
            out[idx] = item
    return out


def _build_beats(client, narrs: list[str], entities: dict[str, str]):
    """Direct -> validate -> repair loop. Returns (beats, unresolved issues as dicts)."""
    beats: dict[int, dict] = {}
    todo, problems = list(range(len(narrs))), {}
    issues = []
    for rnd in range(REPAIR_ROUNDS + 1):
        try:
            got = _direct(client, narrs, entities, todo, problems)
        except Exception as e:  # noqa: BLE001
            if rnd == 0:
                raise
            log.warning("Director repair round %d failed (%s); keeping current beats.", rnd, e)
            break
        for i, b in got.items():
            beats[i] = normalize_beat(b)
        ordered = [beats.get(i, {}) for i in range(len(narrs))]
        issues = [x for x in validate_beats(narrs, ordered, entities) if x.code in REPAIRABLE]
        if not issues:
            break
        todo = sorted({x.index for x in issues})
        problems = {i: [x.msg for x in issues if x.index == i] for i in todo}
        log.info("Beat validation: %d scene(s) need repair (round %d): %s", len(todo), rnd + 1, [i + 1 for i in todo])

    final = []
    for i, narr in enumerate(narrs):
        b = beats.get(i)
        if not b or not b.get("action"):
            log.warning("scene %d: no usable beat — using literal fallback.", i + 1)
            b = fallback_beat(narr)
        final.append(b)
    enforce_shot_variety(final)
    unresolved = [{"scene": x.index + 1, "code": x.code, "msg": x.msg} for x in issues]
    if unresolved:
        log.warning("Unresolved beat issues after repair: %s", unresolved)
    return final, unresolved


# ------------------------------------------------------------------ human-review export
def _export_markdown(board: StoryBoard, lines: list[dict], sections: list[dict] | None, path: Path) -> None:
    """storyboard.md in the same layout as the hand-reviewed POV storyboards, plus a header per section/level."""
    names = {s["id"]: f"{s['name']}" + (f" ({s['label']})" if s.get("label") else "") for s in (sections or [])}
    out = [
        f"# {board.topic} — Storyboard", "",
        f"**Scenes:** {len(board.scenes)}  |  **Character lock:** {CHARACTER_SHORT}  |  **Aspect:** {ASPECT or 'n/a'}",
        "", "---", "",
    ]
    last = None
    for i, sc in enumerate(board.scenes):
        sid = lines[i].get("section_id")
        if sid and sid != last:
            out += [f"# ▸ {names.get(sid, sid)}", ""]
            last = sid
        out += [f"## Scene {i + 1} — {sc.title}", "",
                f"- **Narration:** {sc.narration}", f"- **Visual prompt:** {sc.scene_prompt}", ""]
    path.write_text("\n".join(out), encoding="utf-8")


# ------------------------------------------------------------------ entry point
def _scene_count(scene_count: int | None) -> int:
    if scene_count:
        return scene_count
    env = os.getenv("SCENE_COUNT", "").strip()
    if env:
        return int(env)
    return max(6, round(TARGET_SECONDS / SEC_PER_SCENE))


def run(
    topic: str,
    project_dir: Path,
    scene_count: int | None = None,
    lines_file: Path | str | None = None,
    mode: str | None = None,
) -> StoryBoard:
    """Execute Phase 1 and return a populated StoryBoard (API-key backend)."""
    if LLM_BACKEND == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError("LLM_BACKEND=openai but OPENAI_API_KEY is not set.")
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    else:
        if not API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set in the environment.")
        from google import genai
        client = genai.Client(api_key=API_KEY)

    mode = "file" if lines_file else (mode or WRITER_MODE)
    n = _scene_count(scene_count)
    sections = None
    if mode == "file":
        log.info("Phase 1: using approved lines from %s", lines_file)
        lines, entities = _load_lines_file(Path(lines_file))
    elif mode == "levels":
        log.info("Phase 1 (Gemini %s): levels writer, %d scenes for '%s'", MODEL, n, topic)
        lines, entities, sections = _write_levels(client, topic, n)
    else:
        log.info("Phase 1 (Gemini %s): flat writer, %d lines for '%s'", MODEL, n, topic)
        lines, entities = _write_flat(client, topic, n)

    narrs = [clean_text(x["narration"]) for x in lines]  # TTS must never see underscores/ids

    bad = entity_conflicts(entities)
    for k, why in bad.items():
        log.warning("Dropping entity '%s': it redefines the locked character look (%s).", k, why)
        entities.pop(k, None)

    lint = story_lint(narrs)
    for p in lint:
        log.warning("story_lint [%s] %s", p["code"], p["msg"])

    log.info("Phase 1: directing %d visual beats", len(narrs))
    beats, unresolved = _build_beats(client, narrs, entities)

    scenes = [
        Scene(
            index=i,
            title=lines[i]["title"],
            scene_prompt=render_action(beats[i], entities),
            narration=narrs[i],
        )
        for i in range(len(narrs))
    ]

    board = StoryBoard(
        topic=topic,
        slug=slugify(topic),
        script=" ".join(narrs),  # single source of truth: the audio is exactly these lines
        character_reference_prompt=CHARACTER_SHORT,  # deterministic; matches the lock used in flow_stage
        scenes=scenes,
    )

    project_dir = Path(project_dir)
    out = board.save(project_dir / "storyboard.json")
    (project_dir / "script.txt").write_text(board.script, encoding="utf-8")
    _export_markdown(board, lines, sections, project_dir / "storyboard.md")
    (project_dir / "beats.json").write_text(
        json.dumps(
            {
                "entities": entities,
                "beats": beats,
                "sections": [{"scene": i + 1, "section_id": x.get("section_id"), "level_id": x.get("level_id")}
                             for i, x in enumerate(lines)],
                "outline": sections,
                "lint": lint,
                "unresolved": unresolved,
            },
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log.info("Phase 1 complete: %d scenes -> %s", len(scenes), out)
    return board
