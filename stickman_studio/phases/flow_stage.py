"""
flow_stage.py — stage scene prompts for Google Flow generation on the T470.

Instead of generating images on the VPS (which needs a Gemini/billing key),
this writes one prompt per scene to a file the T470 batch tool consumes:

  projects/<slug>/flow_prompts.txt

On the T470:  powershell -File .\flow-batch-gen.ps1 flow_prompts.txt flow_out
then upload the flow_out/ scenes back. The orchestrator then treats those
PNG/JPG files as the scene images.

This keeps the fork VPS-side (no browser, no billing) and the Flow-images
T470-side — matching the working Google Flow setup.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from ..models import StoryBoard

log = logging.getLogger("stickman_studio.flow_stage")

_STYLE_SUFFIX = (
    "minimalist black line art stickman, simple round head, thin stick limbs, "
    "plain white background, no shading, no color, clean vector style."
)


def run(board: StoryBoard, project_dir: Path) -> StoryBoard:
    """Write flow_prompts.txt from the storyboard scenes.

    Returns the board unchanged (images are added when the T470 batch
    results are copied back). Callers should then import the generated
    files via `import_flow_images`.
    """
    char_prompt = board.character_reference_prompt.strip()
    lines = []
    for s in board.scenes:
        action = (s.scene_prompt or s.narration or "").strip()
        prompt = f"{char_prompt} {action} {_STYLE_SUFFIX}".strip()
        lines.append(prompt)
    out = project_dir / "flow_prompts.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("Flow stage: wrote %d prompts -> %s", len(lines), out)
    return board


def import_flow_images(board: StoryBoard, project_dir: Path, img_dir: Path | str) -> StoryBoard:
    """Attach generated scene images (from the T470 batch) back to scenes.

    Expects scene_001.jpg/.png, scene_002, ... in img_dir, ordered by index.
    """
    img_dir = Path(img_dir)
    exts = (".jpg", ".jpeg", ".png", ".webp")
    import re
    mapped: list[tuple[int, Path]] = []
    for p in img_dir.iterdir():
        if p.suffix.lower() not in exts:
            continue
        m = re.search(r"(\d+)", p.stem)
        mapped.append((int(m.group(1)) if m else 9999, p))
    mapped.sort()

    for scene in board.scenes:
        want = scene.index + 1  # 1-based file naming
        hit = next((p for n, p in mapped if n == want), None)
        if hit is None:
            log.warning("no image for scene %d", scene.index)
            continue
        scene.image_path = str(hit)
        log.info("scene %d -> %s", scene.index, hit.name)
    board.save(project_dir / "storyboard.json")
    return board