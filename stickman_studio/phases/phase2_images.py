"""
phase2_images.py  —  IMAGEN (via API key)
==========================================
Generates scene images with the standalone Gemini Images API (google-genai)
using GEMINI_API_KEY. Rewritten so it does NOT require Vertex AI.

PATCHED: uses `genai.Client(api_key=...)` + `client.models.generate_images`
instead of the Vertex service-account path. Subject-reference "capability"
customization is Vertex-only, so we use prompt-only generation that
re-states the character description in every scene (consistent enough for
a minimalist black-line stickman).

Output: PNG files in projects/<slug>/images/, paths recorded on scenes.
"""

from __future__ import annotations

import logging
import os
import traceback
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from ..models import StoryBoard
from ..retry import with_retry

log = logging.getLogger("stickman_studio.phase2")

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
IMAGEN_MODEL = os.getenv("IMAGEN_GENERATE_MODEL", "gemini-3.1-flash-image").strip()

_NEGATIVE = "color, photorealistic, 3d render, shadows, gradients, text, watermark, clutter, realistic human, detailed illustration, astronaut, robot, animal, clothing, shading"

_CHAR_CONSTRAINT = (
    "Minimalist stickman: simple round head, black line art, thin stick body "
    "and limbs, no color, no shading, no clothing, no details, plain white background."
)


def _client():
    from google import genai
    return genai.Client(api_key=API_KEY)


@with_retry
def _generate_image(prompt: str, aspect_ratio: str = "16:9"):
    """Single image via Gemini image model using the plain API key.

    Uses generate_content with an image-output model (works in Developer mode)
    instead of Vertex-only generate_images.
    """
    from google.genai import types
    client = _client()

    resp = client.models.generate_content(
        model=IMAGEN_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )
    data = None
    cand = resp.candidates[0] if resp.candidates else None
    if cand:
        for part in cand.content.parts:
            if getattr(part, "inline_data", None) is not None and part.inline_data.data:
                data = part.inline_data.data
                break
    if not data:
        raise RuntimeError("Imagen returned no image bytes (API-key backend).")
    return data


def _save(img, path: Path):
    """Save raw image bytes to disk."""
    data = img if isinstance(img, (bytes, bytearray)) else _deref_bytes(img)
    if not data:
        raise RuntimeError("Generated image had no bytes to save.")
    path.write_bytes(data)


def _deref_bytes(img):
    """Extract bytes from an image object-ish fallback."""
    for attr in ("image_bytes",):
        v = getattr(img, attr, None)
        if v:
            return v
    if getattr(img, "image", None) is not None:
        return img.image.image_bytes
    return None


def _character_prompt() -> str:
    return ("A minimalist stickman figure: simple round head, thin stick body "
            "and limbs, clean black line art, no color, no shading, plain white "
            "background, vector style, lots of negative space.")


def _generate_scene_prompt_only(ref_prompt: str, scene_prompt: str):
    full_prompt = (
        f"STICKMAN: {ref_prompt} {_CHAR_CONSTRAINT}. "
        f"ACTION: The stickman {scene_prompt}. "
        "Clean black line art, simple, no color, plain white background, "
        "vector style, lots of negative space, no shading, no gradients, no text."
    )
    return _generate_image(full_prompt, aspect_ratio="16:9")


def _make_reference(board: StoryBoard, images_dir: Path) -> Path:
    log.info("Phase 2A (Imagen): generating character reference image")
    prompt = (
        f"{board.character_reference_prompt}. {_CHAR_CONSTRAINT}. "
        "Full body, centered, neutral stance, minimalist stickman, "
        "clean black line art on plain white background, lots of negative space."
    )
    img = _generate_image(prompt, aspect_ratio="16:9")
    ref_path = images_dir / "character_reference.png"
    _save(img, ref_path)
    log.info("Character reference saved -> %s", ref_path)
    return ref_path


def run(board: StoryBoard, project_dir: Path) -> StoryBoard:
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment.")

    images_dir = project_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    ref_prompt = board.character_reference_prompt
    _make_reference(board, images_dir)

    for scene in board.scenes:
        log.info("Phase 2B: scene %d/%d — %s", scene.index + 1, len(board.scenes), scene.title)
        try:
            img = _generate_scene_prompt_only(ref_prompt, scene.scene_prompt)
        except Exception:
            log.warning("Scene %d generation failed; retrying once.\n%s",
                        scene.index, traceback.format_exc())
            img = _generate_scene_prompt_only(ref_prompt, scene.scene_prompt)

        img_path = images_dir / f"scene_{scene.index:02d}.png"
        _save(img, img_path)
        scene.image_path = str(img_path)
        log.info("  saved -> %s", img_path)

    board.save(project_dir / "storyboard.json")
    log.info("Phase 2 complete: %d scene images generated", len(board.scenes))
    return board