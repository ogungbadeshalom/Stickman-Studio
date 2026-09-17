"""
phase1_script.py  —  GEMINI (via API key)
==========================================
Takes a topic, asks Gemini for:
  1. a ~500-word narration script, and
  2. a structured, scene-by-scene storyboard (character + scene prompts)
returned as strict JSON.

PATCHED: uses the standalone Gemini REST API via `google-genai` with a
GEMINI_API_KEY instead of the Vertex AI service-account path.
Output: a StoryBoard object, also persisted to projects/<slug>/storyboard.json
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

log = logging.getLogger("stickman_studio.phase1")

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("STORYSB_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")).strip()


_RESONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "script": {"type": "string"},
        "character_reference_prompt": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "scene_prompt": {"type": "string"},
                    "narration": {"type": "string"},
                },
                "required": ["title", "scene_prompt", "narration"],
            },
        },
    },
    "required": ["script", "character_reference_prompt", "scenes"],
}

_SYSTEM_INSTRUCTION = """\
You are the Storyboard Architect for 'Stickman Studio', crafting viral educational explainers in the style of Ink Explainer / Kurzgesagt.
Your role is to transform topics into fast-paced JSON storyboards that NEVER let a single image linger — every scene is short and cut quickly to retain attention.

RETENTION PACING + AUDIO-MATCH RULES (CRITICAL):
1. THE HOOK (Scene 1): Open with a shocking fact, a weird question, or an extreme visual. Never "Today we will learn about...".
2. SHORT BEATS: Make MORE scenes, each with a SHORT narration line (1-2 short sentences, ~8-14 words). Scenes must cut fast — one visual idea per ~3-5 seconds. Break long ideas into multiple quick scenes.
3. AUDIO-MATCH (IMAGE MUST EQUAL ITS LINE): Each scene's `scene_prompt` must be built from the LITERAL subject, verb and object of that scene's own `narration` — reuse the exact nouns and verbs. The image and the spoken line must be ABOUT THE SAME thing. Never draw something the narration does not mention, and never put narration keywords only in the image or only in the text.
4. VISUAL COMEDY: Leverage the stickman for exaggerated, dynamic physical situations in `scene_prompt` (getting squished, launched, chased, transformed). Keep actions highly dynamic.
5. CONTINUITY: Tell a connected mini-story — hook, escalating beats, payoff. Each scene's visual must match ITS OWN narration line exactly (do not reuse concepts or images).

Technical Constraints (CRITICAL):
- Output must be strict JSON.
- Style: minimalist black line art, simple round head, thin limbs, green tee, denim shorts, white sneakers, flat color, off-white background.
- Storyboard structure must include: topic, slug, script, and a list of scenes.
- Each scene must contain: index, title, scene_prompt, narration.
- Do NOT include 'character_prompt' in the scene object (managed globally).
- Ensure `scene_prompt` focuses ONLY on the action and environment, omitting character identity rules.
- Each `narration` must be SHORT. Prefer ~12-16 scenes over 5-6, so the video cuts quickly.
"""


def _build_prompt(topic: str, scene_count: int) -> str:
    return f"""TOPIC: "{topic}"

Produce:
1. A ~{os.getenv('SCRIPT_WORDS', '500')}-word narration SCRIPT, engaging and clear.
2. A CHARACTER REFERENCE PROMPT for the stickman.
3. Exactly {scene_count} SCENES.

Each scene: title, scene_prompt, narration."""


@with_retry
def _generate(client, prompt: str):
    """Single Gemini call wrapped with retry/backoff (google-genai SDK)."""
    from google.genai import types

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=8192,
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
        ),
    )
    return resp.text


def _extract_json(raw: str):
    """Robustly pull a JSON object out of Gemini output (handles fences/prefix)."""
    s = raw.strip()
    if s.startswith("```"):
        # strip ```json ... ``` fences
        lines = s.splitlines()
        if lines and lines[0].strip().lstrip("#").strip().lower().startswith("json"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    # find first { and last }
    a = s.find("{")
    b = s.rfind("}")
    if a != -1 and b != -1 and b > a:
        s = s[a:b+1]
    return json.loads(s)


def run(topic: str, project_dir: Path, scene_count: int | None = None) -> StoryBoard:
    """Execute Phase 1 and return a populated StoryBoard (API-key backend)."""
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment.")

    from google import genai
    client = genai.Client(api_key=API_KEY)

    scene_count = scene_count or int(os.getenv("SCENE_COUNT", "5"))
    log.info("Phase 1 (Gemini %s): generating script + %d scenes for '%s'", MODEL, scene_count, topic)

    raw = _generate(client, _build_prompt(topic, scene_count))
    try:
        data = _extract_json(raw)
    except json.JSONDecodeError as e:
        log.error("Gemini returned non-JSON output; attempting salvage.")
        raise RuntimeError(f"Failed to parse Gemini JSON: {e}\n--- raw ---\n{raw[:2000]}")

    scenes = [
        Scene(
            index=i,
            title=s.get("title", f"Scene {i + 1}"),
            scene_prompt=s.get("scene_prompt", s.get("narration", "")),
            narration=s.get("narration", ""),
        )
        for i, s in enumerate(data.get("scenes", []) or [])
    ]
    if not scenes:
        raise RuntimeError("Gemini returned zero scenes — cannot build video.")

    char_ref = data.get("character_reference_prompt") or (
        "a minimalist stickman character with an oversized round head, two "
        "solid black dot eyes, thin curved eyebrows, a tiny curved mouth, a few "
        "short black hair strokes, slim elongated limbs; wearing a plain green "
        "short-sleeve tee, medium-blue denim shorts, white low-top sneakers; "
        "clean black line art, flat color, off-white background."
    )

    board = StoryBoard(
        topic=topic,
        slug=slugify(topic),
        script=data.get("script", ""),
        character_reference_prompt=char_ref,
        scenes=scenes,
    )

    out = board.save(project_dir / "storyboard.json")
    (project_dir / "script.txt").write_text(board.script, encoding="utf-8")
    log.info("Phase 1 complete: %d scenes -> %s", len(scenes), out)
    return board