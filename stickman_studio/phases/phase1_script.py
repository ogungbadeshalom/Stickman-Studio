"""
phase1_script.py  —  GEMINI (via API key), two-pass storyboard
==============================================================
Pass A  WRITER    topic  -> N short narration lines + recurring entities
Pass B  DIRECTOR  lines  -> one structured visual beat per line
                          (subject / action / object / setting / shot / pose / props)
Then    deterministic: validate audio-match -> repair only failing scenes ->
        render each beat into `scene_prompt` (no LLM in the last step).

Why two passes: "what is said" and "what is drawn" are different jobs. The
director sees the whole script (so it can vary shots and keep recurring objects
consistent) and is forced into fields the validator can check.

The narration lines are the single source of truth; `script` is just their
join, so the audio can never drift from the pictures.

Output: StoryBoard (same shape as before) persisted to projects/<slug>/storyboard.json
        plus projects/<slug>/beats.json (structured beats, used by QA / regen).

Env:
  GEMINI_API_KEY, STORYSB_GEMINI_MODEL / GEMINI_MODEL (default gemini-2.5-flash)
  SCENE_COUNT        explicit scene count (else derived from the two below)
  TARGET_SECONDS     default 50   (Shorts-length; set 180 for a 3-min video)
  SEC_PER_SCENE      default 4
  BEAT_REPAIR_ROUNDS default 2
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
    CHARACTER_SHORT,
    REPAIRABLE,
    enforce_shot_variety,
    fallback_beat,
    normalize_beat,
    one_line,
    render_action,
    validate_beats,
)

log = logging.getLogger("stickman_studio.phase1")

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("STORYSB_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")).strip()
TARGET_SECONDS = float(os.getenv("TARGET_SECONDS", "50"))
SEC_PER_SCENE = float(os.getenv("SEC_PER_SCENE", "4"))
REPAIR_ROUNDS = int(os.getenv("BEAT_REPAIR_ROUNDS", "2"))

_STR = {"type": "string"}

_WRITER_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": _STR, "narration": _STR},
                "required": ["title", "narration"],
            },
        },
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": _STR, "description": _STR},
                "required": ["id", "description"],
            },
        },
    },
    "required": ["lines", "entities"],
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
                    "subject": _STR,
                    "action": _STR,
                    "object": _STR,
                    "setting": _STR,
                    "shot": _STR,
                    "pose": _STR,
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

_WRITER_SYSTEM = """\
You write narration for fast-cut animated explainers (Ink Explainer style, stickman protagonist).

RULES
1. Line 1 is the HOOK: a shocking fact, a weird question, or an extreme situation. Never "Today we will learn...".
2. Write EXACTLY the requested number of lines. Each line is ONE spoken beat of 8-14 words (1-2 short sentences) that will become ONE picture.
3. DRAWABLE: every line names a concrete thing that can be pictured (object, place, animal, person, machine) and a physical action. Name the subject explicitly. Never start a line with "It", "This", "They" or "That".
4. ARC: hook -> escalating beats -> payoff or twist in the last lines. Every line adds NEW information; never restate an earlier line.
5. Plain spoken language. No stage directions, emoji, hashtags or visual instructions.

ENTITIES: list 0-4 recurring non-character things (objects, places, creatures) that appear in 2+ lines. Give each a short snake_case id and a fixed visual description of at most 20 words. Do NOT describe the stickman protagonist.
Also give each line a 2-4 word title.
"""

_DIRECTOR_SYSTEM = """\
You are the visual director for a stickman explainer. For each narration line, output ONE visual beat that a text-to-image model can draw.
The protagonist is always "the stickman". His look is injected later: NEVER describe his face, body or clothes.

FIELDS (keep each under 12 words, plain words):
- subject: who or what performs the action (usually "the stickman")
- action: one concrete physical verb phrase
- object: what the action acts on (may be empty)
- setting: a short location phrase starting with in / on / at ("in a dim garage")
- shot: one of: wide shot, medium shot, close-up, top-down view, side view, low-angle view
- pose: the stickman's posture or mood if not neutral (deadpan, panicked, smug...)
- props: up to 3 extra visible objects
- entities: ids from the ENTITIES list that appear in the frame
- metaphor: true only if the line is abstract and you drew a concrete stand-in
- on_screen_text: normally empty; at most 3 words and only if a label is essential

RULES
1. AUDIO-MATCH: reuse the literal nouns and verbs of the narration line in subject / action / object. The picture must depict what the line says, not a loosely related idea.
2. ABSTRACT LINE (nothing drawable): choose ONE concrete visual metaphor, set metaphor=true, and still name the line's key noun in `object`.
3. ONE visual idea per scene. Physical comedy (squished, launched, chased, shrunk) is welcome when the line supports it.
4. Never draw anything the line does not mention, apart from setting and props that make the scene readable.
5. Every beat stands alone: no "again", "as before", "same as last scene".
6. Vary `shot`. Never use the same shot three scenes in a row.
7. Never put speech, captions, signs or writing in the picture.
"""


# ---------------------------------------------------------------- Gemini plumbing
def _call(client, prompt: str, system: str, schema: dict | None) -> str:
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
    """Robustly pull a JSON object out of Gemini output (handles fences/prefix)."""
    s = raw.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].strip().lstrip("#").strip().lower().startswith("json"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b != -1 and b > a:
        s = s[a : b + 1]
    return json.loads(s)


def _json_call(client, prompt: str, system: str, schema: dict) -> dict:
    raw = _generate(client, prompt, system, schema)
    try:
        return _extract_json(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse Gemini JSON: {e}\n--- raw ---\n{raw[:2000]}")


# ---------------------------------------------------------------- Pass A: writer
def _write_lines(client, topic: str, n: int) -> tuple[list[dict], dict[str, str]]:
    prompt = (
        f'TOPIC: "{topic}"\n\n'
        f"Write EXACTLY {n} lines (about {TARGET_SECONDS:.0f} seconds of narration) and the ENTITIES list."
    )
    data = _json_call(client, prompt, _WRITER_SYSTEM, _WRITER_SCHEMA)
    lines = [
        {"title": one_line(x.get("title")) or f"Scene {i + 1}", "narration": one_line(x.get("narration"))}
        for i, x in enumerate(data.get("lines") or [])
        if one_line(x.get("narration"))
    ]
    if not lines:
        raise RuntimeError("Gemini returned zero narration lines — cannot build video.")
    if len(lines) != n:
        log.warning("Writer returned %d lines, wanted %d — continuing with %d.", len(lines), n, len(lines))
    entities: dict[str, str] = {}
    for e in data.get("entities") or []:
        eid = "".join(c if c.isalnum() else "_" for c in one_line(e.get("id")).lower()).strip("_")
        desc = one_line(e.get("description"))
        if eid and desc:
            entities[eid] = desc
    return lines, entities


# ---------------------------------------------------------------- Pass B: director
def _director_prompt(narrs: list[str], entities: dict[str, str], todo: list[int], problems: dict[int, list[str]]) -> str:
    ent = "\n".join(f"- {k}: {v}" for k, v in entities.items()) or "(none)"
    script = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(narrs))
    scope = "ALL scenes" if len(todo) == len(narrs) else "ONLY scenes " + ", ".join(str(i + 1) for i in todo)
    out = f"ENTITIES (reference by id in `entities`):\n{ent}\n\nFULL NARRATION (for context):\n{script}\n\nWrite beats for {scope}. Use the scene number as `index`."
    if problems:
        fix = "\n".join(f"- scene {i + 1}: " + " | ".join(m) for i, m in sorted(problems.items()))
        out += f"\n\nYour previous beats for these scenes were rejected. Fix them:\n{fix}"
    return out


def _direct(client, narrs, entities, todo, problems) -> dict[int, dict]:
    data = _json_call(client, _director_prompt(narrs, entities, todo, problems), _DIRECTOR_SYSTEM, _DIRECTOR_SCHEMA)
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


def _build_beats(client, narrs: list[str], entities: dict[str, str]) -> tuple[list[dict], list[dict]]:
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


# ---------------------------------------------------------------- entry point
def _scene_count(scene_count: int | None) -> int:
    if scene_count:
        return scene_count
    env = os.getenv("SCENE_COUNT", "").strip()
    if env:
        return int(env)
    return max(6, round(TARGET_SECONDS / SEC_PER_SCENE))


def run(topic: str, project_dir: Path, scene_count: int | None = None) -> StoryBoard:
    """Execute Phase 1 and return a populated StoryBoard (API-key backend)."""
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment.")

    from google import genai
    client = genai.Client(api_key=API_KEY)

    n = _scene_count(scene_count)
    log.info("Phase 1 (Gemini %s): writing %d lines for '%s'", MODEL, n, topic)
    lines, entities = _write_lines(client, topic, n)
    narrs = [x["narration"] for x in lines]

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
    (project_dir / "beats.json").write_text(
        json.dumps({"entities": entities, "beats": beats, "unresolved": unresolved}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Phase 1 complete: %d scenes -> %s", len(scenes), out)
    return board
