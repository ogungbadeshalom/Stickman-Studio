"""
flow_stage.py — stage scene prompts for Google Flow generation on the T470.

Writes one prompt per scene to  projects/<slug>/flow_prompts.txt  (the T470
batch tool consumes it), plus  flow_manifest.json  (line number -> scene).

On the T470:  powershell -File .\\flow-batch-gen.ps1 flow_prompts.txt flow_out
then upload flow_out/ back and call `import_flow_images`.

Changes vs v1
  * Every prompt is forced onto ONE line (a stray newline in an LLM scene_prompt
    used to silently shift every later image by one).
  * Hard checks: line count == scene count, no empty prompts, length budget.
  * The verbatim narration quote is OFF by default: image models tend to paint
    quoted text into the picture. The structured beat already carries the
    literal nouns/verbs. Re-enable with ZENN_APPEND_NARRATION=1.
  * import_flow_images is STRICT: missing / duplicate / reused images abort
    instead of warning (matches the "no image reuse" rule).
  * ZENN_LOCK_MODE=ref -> also writes character_sheet_prompt.txt (generate the
    reference sheet once, upload it in Flow as the character reference).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from ..models import StoryBoard
from zenn_style import LOCK_MODE, character_sheet_prompt, full_image_prompt, one_line

log = logging.getLogger("stickman_studio.flow_stage")

MAX_WORDS = int(os.getenv("ZENN_MAX_PROMPT_WORDS", "140"))
APPEND_NARRATION = os.getenv("ZENN_APPEND_NARRATION", "0") == "1"


def build_prompt(scene) -> str:
    """Scene -> final one-line Flow prompt."""
    action = one_line(scene.scene_prompt or scene.narration or scene.title or f"Scene {scene.index + 1}")
    narr = one_line(scene.narration)
    if APPEND_NARRATION and narr:
        action += f" Illustrates the spoken line (never write it as text): {narr}"
    return full_image_prompt(action)


def run(board: StoryBoard, project_dir: Path) -> StoryBoard:
    """Write flow_prompts.txt + flow_manifest.json from the storyboard scenes."""
    project_dir = Path(project_dir)
    prompts = [build_prompt(s) for s in board.scenes]

    # ---- hard checks: 1 prompt == 1 scene == 1 image, or stop now
    if len(prompts) != len(board.scenes) or not prompts:
        raise RuntimeError("Prompt count != scene count; refusing to stage.")
    for i, p in enumerate(prompts):
        if not p.strip():
            raise RuntimeError(f"scene {i + 1}: empty prompt")
        if "\n" in p or "\r" in p:
            raise RuntimeError(f"scene {i + 1}: prompt contains a newline")
        w = len(p.split())
        if w > MAX_WORDS:
            log.warning("scene %d prompt is %d words (> %d) — long prompts risk WireFormatError", i + 1, w, MAX_WORDS)
    if len(set(prompts)) != len(prompts):
        log.warning("some scenes produced IDENTICAL prompts — those images will look duplicated")

    out = project_dir / "flow_prompts.txt"
    out.write_text("\n".join(prompts) + "\n", encoding="utf-8")
    manifest = [
        {"line": i + 1, "scene": s.index + 1, "words": len(p.split()), "narration": s.narration, "prompt": p}
        for i, (s, p) in enumerate(zip(board.scenes, prompts))
    ]
    (project_dir / "flow_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    avg = sum(m["words"] for m in manifest) / len(manifest)
    log.info("Flow stage: wrote %d prompts (avg %.0f words, lock=%s) -> %s", len(prompts), avg, LOCK_MODE, out)

    if LOCK_MODE == "ref":
        sheet = project_dir / "character_sheet_prompt.txt"
        if not sheet.exists():
            sheet.write_text(character_sheet_prompt() + "\n", encoding="utf-8")
        ref = os.getenv("ZENN_REF_IMAGE") or str(project_dir / "character_ref.png")
        if not Path(ref).exists():
            log.warning("ZENN_LOCK_MODE=ref but no reference image at %s — generate one from %s and attach it in Flow.", ref, sheet)
    return board


# --------------------------------------------------------------------------
_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _file_number(stem: str) -> int | None:
    m = re.search(r"scene[_\-\s]*(\d+)", stem, re.I)
    if m:
        return int(m.group(1))
    nums = re.findall(r"\d+", stem)
    return int(nums[-1]) if nums else None  # LAST number: timestamps/ids come first


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def import_flow_images(
    board: StoryBoard,
    project_dir: Path,
    img_dir: Path | str,
    index_map: list[int] | None = None,
    strict: bool = True,
) -> StoryBoard:
    """Attach generated images to scenes.

    Default: files scene_001.png ... map to scenes 1..N.
    Regen batches: pass index_map (scene number for file 1, file 2, ...), e.g.
    the `regen_index.json` written by qa_images, so only those scenes update.
    strict=True raises on missing/duplicate/extra files or reused (byte-identical) images.
    """
    img_dir, project_dir = Path(img_dir), Path(project_dir)
    n_scenes = len(board.scenes)
    targets = {i + 1: sc for i, sc in enumerate(index_map)} if index_map else {k: k for k in range(1, n_scenes + 1)}

    found: dict[int, Path] = {}
    dupes, extras = [], []
    for p in sorted(img_dir.iterdir()):
        if p.suffix.lower() not in _EXTS:
            continue
        n = _file_number(p.stem)
        if n is None or n not in targets:
            extras.append(p.name)
        elif n in found:
            dupes.append(f"{found[n].name} & {p.name}")
        else:
            found[n] = p

    missing = [targets[n] for n in sorted(targets) if n not in found]
    problems = []
    if missing:
        problems.append(f"missing images for scene(s): {missing}")
    if dupes:
        problems.append(f"two files claim the same scene: {dupes}")
    if extras:
        problems.append(f"unmatched files: {extras}")

    for n, p in found.items():
        board.scenes[targets[n] - 1].image_path = str(p)

    # reuse check across ALL scenes that now have an image
    by_hash: dict[str, int] = {}
    for s in board.scenes:
        if s.image_path and Path(s.image_path).exists():
            h = _sha(Path(s.image_path))
            if h in by_hash:
                problems.append(f"scene {s.index + 1} image is byte-identical to scene {by_hash[h]} (reuse)")
            by_hash[h] = s.index + 1

    if problems:
        msg = "; ".join(problems)
        if strict:
            raise RuntimeError(f"Flow import aborted: {msg}")
        log.warning("Flow import problems (non-strict): %s", msg)

    for n, p in sorted(found.items()):
        log.info("scene %d -> %s", targets[n], p.name)
    board.save(project_dir / "storyboard.json")
    return board
