#!/usr/bin/env bash
# =============================================================================
# zenn_flow.sh — fully-automated ZENN stickman video, all on the VPS.
#
#   topic -> Gemini storyboard (15 scenes) -> Google Flow (Nano Banana 2, via
#   gflow CLI, real Google Flow on the VPS) -> per-scene images -> vertical
#   1080x1920 video with narration + Ken Burns -> ready to upload.
#
# No T470. No browser window needed (gflow runs under Xvfb :99). $0.
#
# Usage:
#   ./zenn_flow.sh "Why you still procrastinate" [--scenes 8] [--out DIR]
# =============================================================================
set -euo pipefail

TOPIC="$1"; shift || true
SCENES=8
OUT="/root/zenn_videos"
GFLOW_HOME="/root/gflow-home"
GFLOW_PROFILE="stickman"
GFLOW_FORK="/root/gflow-fork"
STICK="/root/stickman-fork"
PY="${STICK}/.venv/bin/python3"
# orchestrator uses the hermes venv python3 — reconcile:
PY3="/usr/local/lib/hermes-agent/venv/bin/python3"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenes) SCENES="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done

mkdir -p "$OUT"
export GFLOW_CLI_HOME="$GFLOW_HOME"
export GFLOW_CLI_PROFILE="$GFLOW_PROFILE"
export GFLOW_CLI_FLOW_HOST="flow.google.com"
export DISPLAY="${DISPLAY:-:99}"

echo "=== [1/6] starting Xvfb if not running ==="
pgrep -x Xvfb >/dev/null || { nohup Xvfb :99 -screen 0 1280x1024x24 >/root/xvfb.log 2>&1 & sleep 1; }

echo "=== [2/6] storyboard: $SCENES scenes via Gemini ==="
rm -rf "$OUT/current"
mkdir -p "$OUT/current"
cd "$STICK"
# bust cache + RETRY: Gemini free-tier 503s hard; keep retrying with backoff
# until flow_prompts.txt exists (the self-healing link).
for attempt in $(seq 1 12); do
  "$PY3" orchestrator.py "$TOPIC" --scenes "$SCENES" --flow-staged --project-dir "$OUT/current" >/tmp/zenn_story_$attempt.log 2>&1 || true
  if find "$OUT/current" -name flow_prompts.txt 2>/dev/null | grep -q .; then
    echo "storyboard OK (attempt $attempt)"
    break
  fi
  echo "attempt $attempt failed (Gemini busy) — backing off 15s"
  sleep 15
done
# orchestrator with --flow-staged writes flow_prompts.txt (does NOT generate images on VPS)
PROMPTS=$(find "$OUT/current" -name flow_prompts.txt 2>/dev/null | head -1)
if [ -z "${PROMPTS:-}" ] || [ ! -s "$PROMPTS" ]; then
  echo "ERROR: no flow_prompts.txt generated. Aborting."
  exit 3
fi
echo "prompts file: $PROMPTS ($(wc -l < "$PROMPTS") scenes)"

echo "=== [3/6] ensuring a Flow project exists ==="
cd "$GFLOW_FORK"
PROJ=$(GFLOW_CLI_HOME="$GFLOW_HOME" GFLOW_CLI_PROFILE="$GFLOW_PROFILE" uv run gflow project list 2>/dev/null \
        | awk 'NR>2 && $1 ~ /^[0-9a-f-]{36}/ {print $1; exit}')
if [ -z "${PROJ:-}" ]; then
  echo "No existing project found. Creating one via the browser dashboard is required once."
  echo "We reuse the session project created earlier: 5e83ba0b-9909-41f3-a15a-02f3ef741e79"
  PROJ="5e83ba0b-9909-41f3-a15a-02f3ef741e79"
fi
echo "project: $PROJ"

echo "=== [4/6] generating scenes via Google Flow (Nano Banana 2, per-prompt loop) ==="
rm -f /root/gflow-home/locks/*.lock 2>/dev/null || true
DEST="$OUT/current/flow_out"
mkdir -p "$DEST"
# --prompts-file is incompatible with --project; loop one prompt at a time
# (each single-prompt call supports --project; all share the same Flow project).
n=0
while IFS= read -r p; do
  [ -z "$p" ] && continue
  case "$p" in \#*) continue;; esac
  n=$((n+1))
  echo "  scene $n: generating..."
  uv run gflow image t2i "$p" --model nano2 --aspect 9:16 --project "$PROJ" \
      --out "$DEST" >/tmp/zenn_flow_scene_$n.log 2>&1 || echo "  scene $n FAILED (see log)"
  # throttle to respect the daily image cap + anti-bot courtesy
  sleep 3
done < "$PROMPTS"
echo "loop done ($n prompts)"

echo "=== [5/6] mapping generated Flow images to scene files ==="
# gflow names outputs <uuid>_N.jpg; we need scene_001..scene_NN as orchestrator expects
"$PY3" - <<PYEOF
import glob, os, re, shutil
dest="$DEST"
files = sorted(glob.glob(os.path.join(dest, "*.jp*")))
# gflow may output M images; map in order to scene_NNN.jpg
for i, f in enumerate(files, 1):
    scene = os.path.join(dest, f"scene_{i:03d}.jpg")
    shutil.copy(f, scene)
    print("scene", i, "->", os.path.basename(scene))
print("mapped", len(files), "images")
PYEOF

echo "=== [6/6] assembling vertical video (narration + Ken Burns) ==="
cd "$STICK"
PROJDIR=$(dirname "$PROMPTS")
# rerun WITH --flow-staged so it imports the already-generated Flow scenes
# from flow_out/ (NOT the quota'd Gemini image API), then assembles.
rm -f "$PROJDIR/final.mp4" || true
"$PY3" orchestrator.py "$TOPIC" --scenes "$SCENES" --flow-staged \
    --flow-import-dir "$DEST" --project-dir "$OUT/current" 2>&1 | tail -25 || echo "(assembly issue—see above)"

FINAL=$(find "$OUT/current" -name final.mp4 2>/dev/null | head -1)
echo ""
echo "=============================================="
if [ -n "${FINAL:-}" ]; then
  echo "DONE: $FINAL"
  echo "SIZE: $(du -h "$FINAL" | cut -f1)"
  ffprobe -v error -show_entries stream=codec_type,width,height -of csv=p=0 "$FINAL" 2>/dev/null | head -2
else
  echo "No final.mp4 produced. Check the assembly logs above."
fi
echo "=============================================="