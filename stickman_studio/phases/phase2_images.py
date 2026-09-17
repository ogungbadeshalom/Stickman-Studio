"""
phase2_images.py  —  GEMINI "NANO BANANA" IMAGE API (VPS-native)
==========================================
Generates every scene image with the OpenAI-image-capable Gemini model
(gemini-3.1-flash-image / Nano Banana 2) using GEMINI_API_KEY. Runs entirely
on the VPS — no T470, no browser, no Google Flow session.

Every prompt is composed from zenn_style CHARACTER_LOCK + STYLE_LOCK so the
same minimalist stickman stays pixel-consistent across all scenes.

Output: PNG/JPEG files in projects/<slug>/images/, paths recorded on scenes.

NOTE: This supersedes both the flow_staged (T470/Google Flow) path for
automated bulk runs. Set IMAGE_ASPECT to '9:16' for vertical Shorts.
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
from zenn_style import CHARACTER_LOCK, STYLE_LOCK

log = logging.getLogger("stickman_studio.phase2")

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
IMAGEN_MODEL = os.getenv("IMAGEN_GENERATE_MODEL", "gemini-3.1-flash-image").strip()
IMAGE_ASPECT = os.getenv("IMAGE_ASPECT", "9:16").strip()  # vertical Shorts by default
IMAGE_PERCENT = int(os.getenv("IMAGE_PERCENT", "70"))
IMAGE_MAGIC = os.getenv("IMAGE_MAGIC", "enable").strip()

_NEGATIVE = (
    "photorealistic, 3d render, realistic human anatomy, anime, painterly, "
    "neon, glossy, watermark, text, clutter, dramatic lighting, gradients"
)


def _client():
    from google import genai
    return genai.Client(api_key=API_KEY)


def _build_prompt(action: str) -> str:
    """One self-contained prompt with the ZENN character + style + action + negative."""
    if IMAGE_MAGIC == "enable":
        return (
            f"{CHARACTER_LOCK} {action} {STYLE_LOCK} "
            f"Full body or medium shot as the scene requires. "
            f"- {_NEGATIVE}"
        )
    return f"{CHARACTER_LOCK} {action} {STYLE_LOCK}"


@with_retry
def _generate_image(prompt: str, aspect: str = "9:16"):
    """Single image via the Nano Banana image model using the plain API key."""
    from google.genai import types
    client = _client()
    resp = client.models.generate_content(
        model=IMAGEN_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=aspect,
                image_size=None,
            ),
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
        raise RuntimeError("Nano Banana returned no image bytes.")
    return data


def _save(img, path: Path):
    data = img if isinstance(img, (bytes, bytearray)) else _deref_bytes(img)
    if not data:
        raise RuntimeError("Generated image had no bytes to save.")
    path.write_bytes(data)


def _deref_bytes(img):
    for attr in ("image_bytes",):
        v = getattr(img, attr, None)
        if v:
            return v
    if getattr(img, "image", None) is not None:
        return img.image.image_bytes
    return None


def run(board: StoryBoard, project_dir: Path) -> StoryBoard:
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment.")

    images_dir = project_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    aspect = IMAGE_ASPECT

    for scene in board.scenes:
        log.info("Phase 2: scene %d/%d — %s", scene.index + 1, len(board.scenes), scene.title)
        action = (scene.scene_prompt or scene.narration or "").strip()
        try:
            img = _generate_image(_build_prompt(action), aspect=aspect)
        except Exception:
            log.warning("Scene %d generation failed; retrying once.\n%s",
                        scene.index, traceback.format_exc())
            img = _generate_image(_build_prompt(action), aspect=aspect)

        img_path = images_dir / f"scene_{scene.index:02d}.png"
        _save(img, img_path)
        scene.image_path = str(img_path)
        log.info("  saved -> %s", img_path)

    board.save(project_dir / "storyboard.json")
    log.info("Phase 2 complete: %d scene images generated (model=%s aspect=%s)",
             len(board.scenes), IMAGEN_MODEL, aspect)
    return board