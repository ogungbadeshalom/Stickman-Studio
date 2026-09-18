"""
qa_images.py — score every generated image against its narration line (Gemini vision).

Replaces "prompt overlap" as the accuracy signal: we check the PICTURE, not the prompt.
Free-tier friendly (one small vision call per scene, sleeps between calls).

Per scene it asks Gemini:
  matches_narration     0-5  does the picture literally show what the line says?
  character_consistent  0-5  same stickman as the reference image (or the written spec)?
  text_in_image         bool any letters/captions/speech bubbles drawn?
  missing               list what the line mentions that is NOT in the picture
  fix                   one sentence telling the image model what to change

Outputs (in project_dir):
  qa_report.json      all scores + pass/fail
  regen_prompts.txt   corrected prompts for FAILING scenes only (one per line)
  regen_index.json    scene number for each line of regen_prompts.txt

Regen loop:
  1. run Flow batch on regen_prompts.txt  ->  regen_out/
  2. import_flow_images(board, project_dir, "regen_out", index_map=<regen_index.json>)
  3. run qa_images again (max 2 rounds is plenty)

Env: QA_MIN_MATCH (4)  QA_MIN_CHAR (4)  QA_SLEEP (1.5 s between calls)
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from ..models import StoryBoard
from ..retry import with_retry
from zenn_style import CHARACTER_SHORT, full_image_prompt, one_line

log = logging.getLogger("stickman_studio.qa")

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("STORYSB_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")).strip()
MIN_MATCH = int(os.getenv("QA_MIN_MATCH", "4"))
MIN_CHAR = int(os.getenv("QA_MIN_CHAR", "4"))
SLEEP = float(os.getenv("QA_SLEEP", "1.5"))

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

_SCHEMA = {
    "type": "object",
    "properties": {
        "matches_narration": {"type": "integer"},
        "character_consistent": {"type": "integer"},
        "text_in_image": {"type": "boolean"},
        "missing": {"type": "array", "items": {"type": "string"}},
        "fix": {"type": "string"},
    },
    "required": ["matches_narration", "character_consistent", "text_in_image", "missing", "fix"],
}

_SYSTEM = (
    "You are a strict QA reviewer for a stickman explainer video. Judge ONLY what is visibly drawn. "
    "Scores are integers 0-5 (5 = perfect). Be harsh: if a noun or action from the narration is not "
    "clearly visible, matches_narration is at most 3."
)


def _mime(p: Path) -> str:
    return _MIME.get(p.suffix.lower(), "image/png")


def _call(client, contents) -> str:
    from google.genai import types

    resp = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=2048,
            system_instruction=_SYSTEM,
            response_mime_type="application/json",
            response_schema=_SCHEMA,
        ),
    )
    if not resp.text:
        raise RuntimeError("empty QA response")
    return resp.text


@with_retry
def _review(client, img: Path, narration: str, ref: Path | None) -> dict:
    from google.genai import types

    parts = []
    if ref is not None:
        parts.append(types.Part.from_text(text="REFERENCE character (the stickman must look like this):"))
        parts.append(types.Part.from_bytes(data=ref.read_bytes(), mime_type=_mime(ref)))
        spec = "the reference image above"
    else:
        spec = f"this written spec: {CHARACTER_SHORT}"
    parts.append(types.Part.from_text(text="CANDIDATE image to review:"))
    parts.append(types.Part.from_bytes(data=img.read_bytes(), mime_type=_mime(img)))
    parts.append(types.Part.from_text(
        text=f'Narration line this image must depict: "{narration}"\n'
             f"Character must match {spec}\nReturn the JSON review."
    ))
    return json.loads(_call(client, parts))


def _clamp(v) -> int:
    try:
        return max(0, min(5, int(v)))
    except (TypeError, ValueError):
        return 0


def run(board: StoryBoard, project_dir: Path, ref_image: Path | str | None = None) -> dict:
    """Review every scene image. Returns the report dict (also written to qa_report.json)."""
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment.")
    from google import genai
    client = genai.Client(api_key=API_KEY)

    project_dir = Path(project_dir)
    ref = Path(ref_image) if ref_image else None
    if ref is not None and not ref.exists():
        log.warning("reference image %s not found — judging against the written spec", ref)
        ref = None

    beats_file = project_dir / "beats.json"
    beats = json.loads(beats_file.read_text(encoding="utf-8"))["beats"] if beats_file.exists() else []

    results, regen_lines, regen_index = [], [], []
    for s in board.scenes:
        if not s.image_path or not Path(s.image_path).exists():
            results.append({"scene": s.index + 1, "pass": False, "error": "no image"})
            continue
        try:
            r = _review(client, Path(s.image_path), s.narration, ref)
        except Exception as e:  # noqa: BLE001
            log.warning("scene %d QA call failed: %s", s.index + 1, e)
            results.append({"scene": s.index + 1, "pass": None, "error": str(e)})
            continue

        match, char = _clamp(r.get("matches_narration")), _clamp(r.get("character_consistent"))
        wants_label = bool(beats[s.index].get("on_screen_text")) if s.index < len(beats) else False
        text_bad = bool(r.get("text_in_image")) and not wants_label
        ok = match >= MIN_MATCH and char >= MIN_CHAR and not text_bad
        missing = [one_line(m) for m in (r.get("missing") or []) if one_line(m)]
        res = {
            "scene": s.index + 1, "pass": ok, "matches_narration": match, "character_consistent": char,
            "text_in_image": bool(r.get("text_in_image")), "missing": missing, "fix": one_line(r.get("fix")),
        }
        results.append(res)
        log.info("scene %d: match=%d char=%d text=%s -> %s", s.index + 1, match, char, res["text_in_image"], "OK" if ok else "REGEN")

        if not ok:
            extra = []
            if missing:
                extra.append("The picture MUST clearly show: " + ", ".join(missing) + ".")
            if res["fix"]:
                extra.append(res["fix"])
            if text_bad:
                extra.append("Absolutely no text or letters anywhere.")
            regen_lines.append(full_image_prompt(f"{one_line(s.scene_prompt)} {' '.join(extra)}"))
            regen_index.append(s.index + 1)
        time.sleep(SLEEP)

    scored = [r for r in results if r.get("pass") is not None]
    report = {
        "passed": sum(1 for r in scored if r["pass"]),
        "total": len(results),
        "thresholds": {"match": MIN_MATCH, "character": MIN_CHAR},
        "scenes": results,
    }
    (project_dir / "qa_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if regen_lines:
        (project_dir / "regen_prompts.txt").write_text("\n".join(regen_lines) + "\n", encoding="utf-8")
        (project_dir / "regen_index.json").write_text(json.dumps(regen_index), encoding="utf-8")
    log.info("QA: %d/%d passed, %d to regenerate", report["passed"], report["total"], len(regen_lines))
    return report
