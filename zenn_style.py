"""
zenn_style.py — look + deterministic prompt builder + beat validator + story linter.

Single source of truth for:
  * the character / style text (short forms for per-scene prompts, long forms
    for generating the ONE character reference sheet)
  * turning a structured visual "beat" into an image prompt (no LLM involved)
  * checking that a beat really depicts its narration line (audio-match)
  * linting the STORY itself (repeats, caption-style narration, id leaks...)

Pure Python, no third-party deps -> safe to import anywhere and unit-test.

Env:
  ZENN_LOCK_MODE       "text" (default) | "ref"  (Flow reference image attached)
  ZENN_ASPECT          composition hint, default "vertical 9:16" ("" to disable)
  ZENN_BACKGROUND      default "off-white background". For scenes with real settings
                       use e.g. "full-bleed simple flat-color background that matches the setting"
  ZENN_CHARACTER_FILE  path to a JSON profile that replaces the built-in stickman:
                       {"name": "the character",           # how prompts refer to him/her
                        "short": "...45-word identity lock...",
                        "style_short": "...30-word style lock...",   (optional)
                        "sheet_long": "...long description for the reference sheet..."} (optional)
  ZENN_PROTAGONIST     fallback for "name" when no profile file (default "the stickman")
"""
from __future__ import annotations

import collections
import json
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path

LOCK_MODE = os.getenv("ZENN_LOCK_MODE", "text").strip().lower()
ASPECT = os.getenv("ZENN_ASPECT", "vertical 9:16").strip()
BACKGROUND = os.getenv("ZENN_BACKGROUND", "off-white background").strip()

_PROFILE: dict = {}
_pf = os.getenv("ZENN_CHARACTER_FILE", "").strip()
if _pf and Path(_pf).is_file():
    try:
        _PROFILE = json.loads(Path(_pf).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        _PROFILE = {}

# How prompts refer to the protagonist. NEVER hard-code "stickman" elsewhere.
PROTAGONIST = (_PROFILE.get("name") or os.getenv("ZENN_PROTAGONIST", "the stickman")).strip()

# --------------------------------------------------------------------------
# LONG forms — only used once, to make the character reference sheet.
# --------------------------------------------------------------------------
CHARACTER_LOCK = _PROFILE.get("sheet_long") or (
    "A minimalist stickman character: an oversized round "
    "head, two solid black oval dot eyes, thin curved eyebrow lines, a tiny "
    "simple curved mouth, no nose or ears, no skin texture, a few short black "
    "hair strokes sticking up from the top, a narrow cylindrical neck, slim "
    "elongated arms and legs, simplified hands and feet. He wears an oversized "
    "plain green short-sleeve t-shirt, loose medium-blue denim shorts ending "
    "above the knee with simple front pockets and rolled cuffs, and plain "
    "white low-top sneakers, every clothing shape outlined in clean black."
)

STYLE_LOCK = (
    "Clean black hand-drawn-style line art, consistent medium-weight outlines, "
    "simple interior lines, flat color fills, very light gray contact shadow "
    "beneath the character. Minimalist 2D cartoon illustration, restrained "
    "palette of off-white background, black, green, muted medium blue, and "
    "white. No photorealism, no 3D, no anime, no painterly shading, no neon, "
    "no glossy surfaces, no dramatic lighting."
)

# --------------------------------------------------------------------------
# SHORT forms — what actually goes into every scene prompt.
# Order matters: the scene ACTION goes first so the model weights it most.
# --------------------------------------------------------------------------
CHARACTER_SHORT = _PROFILE.get("short") or (
    "The recurring stickman: oversized round head, two solid black dot eyes, "
    "thin curved eyebrows, tiny curved mouth, no nose or ears, a few short black "
    "hair strokes on top, slim long limbs, oversized plain green t-shirt, loose "
    "blue denim shorts with rolled cuffs, plain white sneakers."
)

STYLE_SHORT = _PROFILE.get("style_short") or (
    "Clean black hand-drawn line art, consistent medium-weight outlines, flat "
    f"color fills, {BACKGROUND}, very light gray contact shadow, generous "
    "negative space, minimalist 2D cartoon, restrained palette."
)

# Used instead of CHARACTER_SHORT + STYLE_SHORT when a Flow reference image is attached.
REF_LOCK = (
    "Draw the character and the art style exactly as in the attached reference "
    "image (same face, hair, outfit, proportions, line weight, flat colors). "
    f"Background: {BACKGROUND}."
)
# Reference attached but the character is NOT in this shot: keep the style only.
REF_STYLE_ONLY = (
    "Match the art style of the attached reference image exactly (line weight, "
    f"flat colors), but do not draw the character from it. Background: {BACKGROUND}."
)

NO_TEXT = "No text, letters, captions, speech bubbles or watermarks anywhere in the image."
LABEL_MARK = "The only text in the image is"
ABSENT_MARK = "The main character does not appear in this shot."

SHOTS = ("wide shot", "medium shot", "close-up", "top-down view", "side view", "low-angle view")


def one_line(s: str | None) -> str:
    """Collapse ALL whitespace (incl. newlines). One prompt must be ONE line."""
    return re.sub(r"\s+", " ", s or "").strip()


def clean_text(s: str | None) -> str:
    """one_line + underscores -> spaces (entity ids like worn_sneakers must never reach TTS or prompts)."""
    return one_line((s or "").replace("_", " "))


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _pkey() -> str:
    """Bare noun of the protagonist name: 'the stickman' -> 'stickman'."""
    return re.sub(r"^(the|a|an)\s+", "", PROTAGONIST.lower()).strip() or "character"


# --------------------------------------------------------------------------
# Prompt builders
# --------------------------------------------------------------------------
def full_image_prompt(action: str, mode: str | None = None) -> str:
    """One self-contained image prompt: ACTION first, then identity/style, then guards."""
    mode = (mode or LOCK_MODE).lower()
    action = one_line(action)
    absent = ABSENT_MARK in action
    if mode == "ref":
        parts = [action, REF_STYLE_ONLY if absent else REF_LOCK]
    elif absent:
        parts = [action, STYLE_SHORT]
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


def _norm_presence(v: str, subject: str) -> str:
    """full = protagonist visible | partial = first-person POV, hands only | none = not in shot."""
    v = (v or "").strip().lower()
    if v.startswith(("full", "in", "yes", "visible")):
        return "full"
    if v.startswith(("part", "hand", "pov", "first")):
        return "partial"
    if v.startswith(("none", "no", "abs", "off", "out")):
        return "none"
    return "full" if _pkey() in (subject or "").lower() else "none"


def _as_list(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        v = re.split(r"[;,]", v)
    out = []
    for x in v:
        x = clean_text(str(x))
        if x:
            out.append(x)
    return out


def normalize_beat(b: dict | None) -> dict:
    """Clean an LLM beat: strings collapsed, ids de-underscored, shot snapped, label <= 3 words."""
    b = b or {}

    def s(k: str) -> str:
        return clean_text(str(b.get(k) or ""))

    label = " ".join(s("on_screen_text").split()[:3])
    meta = b.get("metaphor")
    if isinstance(meta, str):
        meta = meta.strip().lower() in ("true", "yes", "1")
    subject = s("subject") or PROTAGONIST
    return {
        "subject": subject,
        "action": s("action"),
        "object": s("object"),
        "setting": s("setting"),
        "shot": _norm_shot(s("shot")),
        "pose": s("pose"),
        "presence": _norm_presence(s("presence"), subject),
        "props": _as_list(b.get("props"))[:3],
        "entities": [re.sub(r"[^a-z0-9_]+", "_", e.lower()).strip("_") for e in _as_list(b.get("entities"))],
        "metaphor": bool(meta),
        "on_screen_text": label,
    }


def fallback_beat(narration: str) -> dict:
    """Last resort when the director fails: still literal, still one line."""
    return normalize_beat({
        "subject": PROTAGONIST,
        "action": "acts out this moment",
        "object": clean_text(narration),
        "shot": "medium shot",
        "presence": "full",
    })


def _mostly_in(part: str, ref: str, thr: float = 0.6) -> bool:
    """True if >= thr of `part`'s content words already appear in `ref` (avoids 'X ... X' repeats)."""
    pw = content_words(part)
    if not pw:
        return False
    rw = content_words(ref)
    hit = sum(1 for w in pw if any(_same(w, r) for r in rw))
    return hit / len(pw) >= thr


_LOC = re.compile(r"(in|on|at|inside|outside|under|near|beside|behind|above)\b", re.I)


def render_action(beat: dict, entities: dict[str, str] | None = None) -> str:
    """Beat -> one action sentence. Deterministic: same beat, same prompt."""
    b = normalize_beat(beat)
    entities = entities or {}
    action, obj, setting = b["action"], b["object"], b["setting"]
    if obj and _mostly_in(obj, f"{b['subject']} {action}"):
        obj = ""  # object already stated inside the action
    core = " ".join(x for x in (b["subject"], action, obj) if x)
    if setting and _mostly_in(setting, core):
        setting = ""  # setting already stated
    sentence = f"{_cap(b['shot'])}: {_cap(core)}"
    if setting:
        sentence += f" {setting}" if _LOC.match(setting) else f" in {setting}"
    parts = [sentence.rstrip(".") + "."]

    mentions = _pkey() in core.lower()
    presence = "full" if mentions else b["presence"]
    if mentions:
        if b["pose"]:
            parts.append(f"Pose and mood: {b['pose']}.")
    elif presence == "full":
        parts.append(f"{_cap(PROTAGONIST)} is also in frame{', ' + b['pose'] if b['pose'] else ''}.")
    elif presence == "partial":
        parts.append("First-person POV shot: only the character's hands are visible at the edge of the frame.")
    else:
        parts.append(ABSENT_MARK)

    if b["props"]:
        parts.append(f"Visible props: {', '.join(b['props'])}.")
    for eid in b["entities"]:
        if eid in entities:
            desc = one_line(entities[eid]).rstrip(".!? ")
            parts.append(f"{eid.replace('_', ' ').capitalize()} (draw identically every time): {desc}.")
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


# --------------------------------------------------------------------------
# Story lint: problems in the NARRATION itself (run before beats/images)
# --------------------------------------------------------------------------
_SECOND = re.compile(r"\b(you|your|you're|you've|yours)\b", re.I)
_NUMBERISH = re.compile(
    r"\d|\b(dollars?|percent|thousand|million|billion|hundred|grand|salary|wage|paycheck|rent|interest)\b", re.I
)


def story_lint(narrations: list[str], pov: bool = True, expect_numbers: bool = True) -> list[dict]:
    """
    Returns [{"code", "msg", "scenes": [1-based scene numbers]}].
    Codes: id_leak | openers | caption_style | second_person | few_numbers | near_duplicates
    """
    out: list[dict] = []
    n = len(narrations)
    if not n:
        return out

    leak = [i + 1 for i, t in enumerate(narrations) if "_" in t]
    if leak:
        out.append({"code": "id_leak", "scenes": leak,
                    "msg": f"{len(leak)} lines contain '_' (entity ids leaked into narration; TTS would read them aloud)"})

    firsts = collections.Counter((t.split()[0].lower() if t.split() else "") for t in narrations)
    word, cnt = firsts.most_common(1)[0]
    if cnt >= 6 and cnt / n > 0.4:
        out.append({"code": "openers", "scenes": [],
                    "msg": f"{cnt}/{n} lines start with '{word}' — monotone rhythm"})

    cap_like = [i + 1 for i, t in enumerate(narrations)
                if re.match(r"(a|an|the)\b", t.strip(), re.I) and not _SECOND.search(t)]
    if len(cap_like) / n >= 0.5:
        out.append({"code": "caption_style", "scenes": cap_like[:20],
                    "msg": f"{len(cap_like)}/{n} lines read like image captions (object as subject, no 'you'), not narration"})

    if pov:
        share = sum(1 for t in narrations if _SECOND.search(t)) / n
        if share < 0.4:
            out.append({"code": "second_person", "scenes": [],
                        "msg": f"only {share:.0%} of lines address the viewer as 'you' (POV format expects most)"})

    if expect_numbers:
        share = sum(1 for t in narrations if _NUMBERISH.search(t)) / n
        if share < 0.1:
            out.append({"code": "few_numbers", "scenes": [],
                        "msg": f"only {share:.0%} of lines contain a number, price, salary or money term"})

    sets = [set(content_words(t)) for t in narrations]
    dups: list[tuple[int, int]] = []
    for j in range(n):
        for i in range(j):
            if len(sets[i]) < 4 or len(sets[j]) < 4:
                continue
            inter = len(sets[i] & sets[j])
            if inter / len(sets[i] | sets[j]) >= 0.4 or inter >= 5:
                dups.append((i + 1, j + 1))
                break
    if dups:
        out.append({"code": "near_duplicates", "scenes": [b for _, b in dups],
                    "msg": "repeated lines: " + ", ".join(f"{b} repeats {a}" for a, b in dups[:10])})
    return out


_WEAR = {"sneakers", "sneaker", "shoes", "shoe", "boots", "shirt", "tee", "jeans", "pants",
         "shorts", "hat", "cap", "jacket", "hoodie", "sweater", "hair", "glasses"}


def entity_conflicts(entities: dict[str, str]) -> dict[str, str]:
    """Entities that redefine something the character lock already fixes (e.g. 'faded blue sneakers' vs white sneakers)."""
    lock = set(content_words(CHARACTER_SHORT))
    bad: dict[str, str] = {}
    for k, d in entities.items():
        hit = sorted(w for w in set(content_words(d)) if w in _WEAR and any(_same(w, l) for l in lock))
        if hit:
            bad[k] = ", ".join(hit)
    return bad
