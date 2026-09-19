"""
zenn_style.py — ZENN stickman look + deterministic prompt builder + beat validator.

Single source of truth for:
  * the character / style text (short forms for per-scene prompts, long forms
    for generating the ONE character reference sheet)
  * turning a structured visual "beat" into an image prompt (no LLM involved)
  * checking that a beat really depicts its narration line (audio-match)

Pure Python, no third-party deps -> safe to import anywhere and unit-test.

Env:
  ZENN_LOCK_MODE  "text" (default) = short character description in every prompt
                  "ref"            = rely on an uploaded Flow reference image
  ZENN_ASPECT     composition hint, default "vertical 9:16" ("" to disable)
"""
from __future__ import annotations

import os
import random
import re
from dataclasses import dataclass

LOCK_MODE = os.getenv("ZENN_LOCK_MODE", "text").strip().lower()
ASPECT = os.getenv("ZENN_ASPECT", "vertical 9:16").strip()

# --------------------------------------------------------------------------
# LONG forms — only used once, to make the character reference sheet.
# (Old names kept so existing imports don't break.)
# --------------------------------------------------------------------------
import os as _os

# Active character comes from env (default = POV cartoon character, NOT stickman,
# NOT a realistic human). The stickman is preserved below as ZENN_PRESET_STICKMAN
# and can be restored by setting ZENN_CHARACTER=stickman.
_ACTIVE_CHAR = _os.getenv("ZENN_CHARACTER", "cartoon").strip().lower()

ZENN_PRESET_STICKMAN = (
    "The recurring stickman: oversized round head, two solid black dot eyes, "
    "thin curved eyebrows, tiny curved mouth, no nose or ears, a few short black "
    "hair strokes on top, slim long limbs, oversized plain green t-shirt, loose "
    "blue denim shorts with rolled cuffs, plain white sneakers."
)

# Original stickman (used by CHARACTER_LOCK/REF_LOCK below for the preset)
_STICKMAN_LONG = (
    "A minimalist stickman character: an oversized round "
    "head, two solid black oval dot eyes, thin curved eyebrow lines, a tiny "
    "simple curved mouth, no nose or ears, no skin texture, a few short black "
    "hair strokes sticking up from the top, a narrow cylindrical neck, slim "
    "elongated arms and legs, simplified hands and feet. He wears an oversized "
    "plain green short-sleeve t-shirt, loose medium-blue denim shorts ending "
    "above the knee with simple front pockets and rolled cuffs, and plain "
    "white low-top sneakers, every clothing shape outlined in clean black."
)
_STICKMAN_STYLE = (
    "Clean black hand-drawn-style line art, consistent medium-weight outlines, "
    "simple interior lines, flat color fills, very light gray contact shadow "
    "beneath the character. Minimalist 2D cartoon illustration, restrained "
    "palette of off-white background, black, green, muted medium blue, and "
    "white. No photorealism, no 3D, no anime, no painterly shading, no neon, "
    "no glossy surfaces, no dramatic lighting."
)
_STICKMAN_STYLE_SHORT = (
    "Clean black hand-drawn line art, consistent medium-weight outlines, flat "
    "color fills, off-white background, very light gray contact shadow, generous "
    "negative space, minimalist 2D cartoon, restrained palette."
)

# POV cartoon character: a distinct, friendly flat-2D cartoon person. Not a
# stickman, not photorealistic. Supporting-cast neutral so it fits the genre.
_POV_CARTOON = (
    "The recurring cartoon character: a friendly flat 2D animated person with a "
    "proportionate round head, big expressive eyes, a soft rounded nose, a simple "
    "warm smile, tidy short dark hair, a normal neck and shoulders, and smooth "
    "simple hands and feet. He wears a modern casual outfit — a charcoal crew-neck "
    "tee or a light overshirt over a plain t-shirt, straight dark jeans, and clean "
    "white sneakers. Cheerful, understated, easy to read; consistent in every scene."
)

# Cartoon style lock (matches the POV finance-channel look, flat/clean)
_POV_STYLE = (
    "Clean flat 2D cartoon illustration, smooth consistent medium-weight outlines, "
    "simple interior lines, flat color fills, soft very light contact shadow, "
    "generous negative space, warm modern off-white background, restrained but "
    "pleasant palette. Not a stickman, not photorealistic, no 3D, no anime, no "
    "painterly shading, no neon, no glossy surfaces, no dramatic lighting."
)

STYLE_LOCK = _POV_STYLE if _ACTIVE_CHAR != "stickman" else _STICKMAN_STYLE

# Long form (used by phase2_images character sheet)
CHARACTER_LOCK = _STICKMAN_LONG if _ACTIVE_CHAR == "stickman" else (
    "A friendly flat 2D cartoon character: a proportionate round head, big "
    "expressive eyes, a soft rounded nose, a simple warm smile, tidy short dark "
    "hair, a normal neck and shoulders, smooth simple hands and feet. He wears a "
    "charcoal crew-neck tee or a light overshirt over a plain t-shirt, straight "
    "dark jeans, and clean white sneakers. Cheerful, understated, easy to read, "
    "consistent in every scene."
)

# --------------------------------------------------------------------------
# SHORT forms — what actually goes into every scene prompt.
# Order matters: the scene ACTION goes first so the model weights it most.
# --------------------------------------------------------------------------
CHARACTER_SHORT = _POV_CARTOON if _ACTIVE_CHAR != "stickman" else ZENN_PRESET_STICKMAN

STYLE_SHORT = _POV_STYLE if _ACTIVE_CHAR != "stickman" else _STICKMAN_STYLE_SHORT

# Used instead of CHARACTER_SHORT + STYLE_SHORT when a Flow reference image is attached.
REF_LOCK = (
    "Draw the character and the art style exactly as in the attached reference "
    "image (same face, outfit, proportions, line weight, flat colors), on an "
    "off-white background."
)

NO_TEXT = "No text, letters, captions, speech bubbles or watermarks anywhere in the image."
LABEL_MARK = "The only text in the image is"

SHOTS = ("wide shot", "medium shot", "close-up", "top-down view", "side view", "low-angle view")


def one_line(s: str | None) -> str:
    """Collapse ALL whitespace (incl. newlines). One prompt must be ONE line."""
    return re.sub(r"\s+", " ", s or "").strip()


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


# --------------------------------------------------------------------------
# Prompt builders
# --------------------------------------------------------------------------
def full_image_prompt(action: str, mode: str | None = None) -> str:
    """One self-contained image prompt: ACTION first, then identity/style, then guards."""
    mode = (mode or LOCK_MODE).lower()
    action = one_line(action)
    if mode == "ref":
        parts = [action, REF_LOCK]
    else:
        parts = [action, CHARACTER_SHORT, STYLE_SHORT]
    if LABEL_MARK not in action:
        parts.append(NO_TEXT)
    if ASPECT:
        parts.append(f"Composition: {ASPECT}.")
    return " ".join(parts)


def character_sheet_prompt() -> str:
    """Generate this ONCE in Flow, pick the best result, upload it as the reference."""
    return one_line(
        f"{CHARACTER_LOCK} Character reference sheet on a plain off-white background: "
        "a row of full-body views (front, three-quarter, side, back) plus a row of four "
        "head close-ups (neutral, surprised, smiling, deadpan). Identical outfit and "
        f"proportions in every view, evenly spaced. {STYLE_LOCK} No text or labels."
    )


def full_motion_prompt(scene_summary: str = "", seed: int | None = None) -> str:
    """
    Subtle image-to-video motion prompt. Seeded so re-runs are reproducible
    (pass the scene index). scene_summary is accepted for API compatibility.
    """
    motions = [
        "a very slow, almost imperceptible push-in on the character.",
        "gentle parallax drift: background elements move slightly slower than the character.",
        "soft ambient idle: a slow blink and a light breath-like shoulder rise and fall, nothing else moving.",
        "a slow, barely noticeable pull-back to emphasize how small the character is in the frame.",
        "static hold: the character almost completely still, only faint environmental motion.",
    ]
    rng = random.Random(seed)
    return (
        f"For this scene, add {rng.choice(motions)} "
        "No new objects, no new characters, no changed pose, no changes to "
        "lighting or palette. The character's pose, outfit, and background "
        "remain exactly as shown, unchanged. Motion stays subtle and slow."
    )


# --------------------------------------------------------------------------
# Visual beats: structured scene description -> deterministic action sentence
# --------------------------------------------------------------------------
def _norm_shot(x: str) -> str:
    x = (x or "").lower().replace("-", " ").strip()
    if not x:
        return "medium shot"
    for sh in SHOTS:
        s = sh.replace("-", " ")
        if s in x or x in s:
            return sh
    return "medium shot"


def _as_list(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        v = re.split(r"[;,]", v)
    out = []
    for x in v:
        x = one_line(str(x))
        if x:
            out.append(x)
    return out


_PROTAGONIST = "the stickman" if _ACTIVE_CHAR == "stickman" else "the character"

def normalize_beat(b: dict | None) -> dict:
    """Clean an LLM beat: strings collapsed, shot snapped to SHOTS, text label <= 3 words."""
    b = b or {}

    def s(k: str) -> str:
        return one_line(str(b.get(k) or ""))

    label = " ".join(s("on_screen_text").split()[:3])
    meta = b.get("metaphor")
    if isinstance(meta, str):
        meta = meta.strip().lower() in ("true", "yes", "1")
    return {
        "subject": s("subject") or _PROTAGONIST,
        "action": s("action"),
        "object": s("object"),
        "setting": s("setting"),
        "shot": _norm_shot(s("shot")),
        "pose": s("pose"),
        "props": _as_list(b.get("props"))[:3],
        "entities": [re.sub(r"[^a-z0-9_]+", "_", e.lower()).strip("_") for e in _as_list(b.get("entities"))],
        "metaphor": bool(meta),
        "on_screen_text": label,
    }


def fallback_beat(narration: str) -> dict:
    """Last resort when the director fails: still literal, still one line."""
    return normalize_beat({
        "subject": _PROTAGONIST,
        "action": "acts out this moment",
        "object": one_line(narration),
        "shot": "medium shot",
    })


def render_action(beat: dict, entities: dict[str, str] | None = None) -> str:
    """Beat -> one action sentence. Deterministic: same beat, same prompt."""
    b = normalize_beat(beat)
    entities = entities or {}
    core = " ".join(x for x in (b["subject"], b["action"], b["object"]) if x)
    sentence = f"{_cap(b['shot'])}: {_cap(core)}"
    if b["setting"]:
        sentence += f" {b['setting']}" if re.match(r"(in|on|at|inside|outside|under|near|beside|behind|above)\b", b["setting"], re.I) else f" in {b['setting']}"
    parts = [sentence + "."]
    if _PROTAGONIST not in core.lower():
        parts.append(f"The {_PROTAGONIST} is also in frame, {b['pose'] or 'watching'}.")
    elif b["pose"]:
        parts.append(f"{_PROTAGONIST.capitalize()} pose and mood: {b['pose']}.")
    if b["props"]:
        parts.append(f"Visible props: {', '.join(b['props'])}.")
    for eid in b["entities"]:
        if eid in entities:
            parts.append(f"{eid.replace('_', ' ').capitalize()} (draw identically every time): {one_line(entities[eid])}.")
    if b["on_screen_text"]:
        parts.append(f'{LABEL_MARK} the label "{b["on_screen_text"]}".')
    return " ".join(parts)


def enforce_shot_variety(beats: list[dict]) -> list[dict]:
    """Never allow the same shot 3 scenes in a row (deterministic rotation)."""
    for i in range(2, len(beats)):
        if beats[i].get("shot") == beats[i - 1].get("shot") == beats[i - 2].get("shot"):
            for sh in SHOTS:
                if sh != beats[i - 1]["shot"] and (i + 1 >= len(beats) or sh != beats[i + 1].get("shot")):
                    beats[i]["shot"] = sh
                    break
    return beats


# --------------------------------------------------------------------------
# Audio-match validation (deterministic, free, runs before any image is made)
# --------------------------------------------------------------------------
_STOP = set("""a an the and or but if then so of to in on at by for with from as into onto over under about
is are was were be been being am do does did done have has had having it its this that these those
he she they we you i his her their our your my him them us me not no yes just very more most much many
can could will would should may might must than too also only even still what when where which who whom
why how there here up down out off all any each some one two get gets got""".split())


def content_words(text: str) -> list[str]:
    seen, out = set(), []
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if len(w) >= 3 and w not in _STOP and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _same(a: str, b: str) -> bool:
    n = min(len(a), len(b))
    if n < 3:
        return a == b
    k = min(5, n)
    return a[:k] == b[:k]


def beat_visual_text(beat: dict, entities: dict[str, str] | None = None) -> str:
    entities = entities or {}
    bits = [beat.get(k, "") for k in ("subject", "action", "object", "setting", "pose", "on_screen_text")]
    bits += list(beat.get("props") or [])
    bits += [entities.get(e, "") for e in beat.get("entities") or []]
    return " ".join(str(x) for x in bits)


def coverage(narration: str, visual_text: str) -> tuple[float, list[str]]:
    """Share of the narration's content words that the visual actually contains."""
    want = content_words(narration)
    if not want:
        return 1.0, []
    have = content_words(visual_text)
    missing = [w for w in want if not any(_same(w, h) for h in have)]
    return (len(want) - len(missing)) / len(want), missing


@dataclass
class Issue:
    index: int   # 0-based scene index
    code: str    # missing | coverage | forbidden_text | dup_action | narr_len
    msg: str


REPAIRABLE = {"missing", "coverage", "forbidden_text", "dup_action"}

_FORBIDDEN = re.compile(
    r"\b(captions?|subtitles?|speech bubbles?|sign (?:that )?(?:says|reads)|labell?ed|the words?|the text)\b", re.I
)


def validate_beats(
    narrations: list[str],
    beats: list[dict],
    entities: dict[str, str] | None = None,
    min_cov: float = 0.5,
    min_cov_metaphor: float = 0.3,
) -> list[Issue]:
    issues: list[Issue] = []
    seen_keys: list[tuple[int, set[str]]] = []
    for i, narr in enumerate(narrations):
        n_words = len(narr.split())
        if not 5 <= n_words <= 20:
            issues.append(Issue(i, "narr_len", f"narration is {n_words} words (target 8-14)"))

        raw = beats[i] if i < len(beats) else None
        if not raw or not (raw.get("action") or "").strip():
            issues.append(Issue(i, "missing", "no usable visual beat (action is empty)"))
            continue
        b = normalize_beat(raw)

        cov, missing = coverage(narr, beat_visual_text(b, entities))
        need = min_cov_metaphor if b["metaphor"] else min_cov
        if cov < need:
            issues.append(Issue(
                i, "coverage",
                f"visual covers only {cov:.0%} of the narration; the picture must literally show: {', '.join(missing)}",
            ))

        body = " ".join([b["subject"], b["action"], b["object"], b["setting"], b["pose"], *b["props"]])
        if not b["on_screen_text"] and _FORBIDDEN.search(body):
            issues.append(Issue(i, "forbidden_text", "beat asks for text/captions/signs in the image; draw it instead"))

        key = set(content_words(f"{b['action']} {b['object']}"))
        if len(key) >= 2:
            for j, other in seen_keys:
                if len(key & other) / len(key | other) >= 0.8:
                    issues.append(Issue(i, "dup_action", f"same visual as scene {j + 1}; show a different action"))
                    break
            seen_keys.append((i, key))
    return issues
