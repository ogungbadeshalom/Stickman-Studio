"""
tts_engine.py  --  Edge-TTS narration (free, local, no cloud cost)
==================================================================
Generates MP3 narration audio from scene text using the ``edge-tts``
library (Microsoft Edge TTS engine — runs fully locally).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger("stickman_studio.tts")

import os

_DEFAULT_VOICE = os.getenv("TTS_VOICE", "en-US-ChristopherNeural")

# Cache loaded Piper voices by model path (loading is expensive)
_PIPER_CACHE: dict[str, object] = {}

import urllib.request

# Chatterbox via HuggingFace Inference API (no local install)
_HF_TTS_URL = os.getenv("HF_CHATTERBOX_URL", "https://api-inference.huggingface.co/models/ResembleAI/chatterbox")


class TTSEngine:
    """Generates narration audio using Edge-TTS (local, free).

    Uses Microsoft Edge's neural TTS voices. No cloud API calls needed.
    """

    def __init__(
        self,
        voice: str = _DEFAULT_VOICE,
    ) -> None:
        self._voice = voice

    def synthesize_speech(self, text: str, output_path: str | Path) -> Path:
        """Synthesise text into an MP3 file.

        Backend selected by TTS_BACKEND env:
          - 'piper' (default): local Piper ONNX voice (free, offline, reliable)
          - 'edge': Edge-TTS neural voice (local-free)
        """
        backend = os.getenv("TTS_BACKEND", "piper").lower()
        if backend == "piper":
            try:
                return self._synthesize_piper(text, output_path)
            except Exception as exc:
                log.warning("Piper failed (%s); falling back to Edge", str(exc)[:80])
                return self._synthesize_edge(text, output_path)
        return self._synthesize_edge(text, output_path)

    def _synthesize_piper(self, text: str, output_path: str | Path) -> Path:
        """Local Piper ONNX TTS -> proper MP3 (free, offline, reliable)."""
        import wave, subprocess as _sp

        model = os.getenv("PIPER_MODEL", "/root/piper_voices/en_GB-northern_english_male-medium.onnx")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        wav = output.with_suffix(".wav")

        from piper import PiperVoice
        voice = _PIPER_CACHE.get(model)
        if voice is None:
            voice = PiperVoice.load(model)
            _PIPER_CACHE[model] = voice
        w = wave.open(str(wav), "wb")
        voice.synthesize_wav(text, w)
        w.close()

        # encode WAV -> MP3 (persists concise, and the fork expects mp3 files)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
               "-c:a", "libmp3lame", "-q:a", "4", str(output)]
        _sp.run(cmd, check=False)
        if wav.exists() and wav != output:
            wav.unlink(missing_ok=True)
        log.info("TTS (piper): %s <- %s bytes", output.name, output.stat().st_size)
        return output

    def _synthesize_chatterbox(self, text: str, output_path: str | Path) -> Path:
        """Call the Chatterbox HF Inference API and save the returned audio."""
        import json as _json

        token = os.getenv("HF_TOKEN", "").strip()
        if not token:
            raise RuntimeError("TTS_BACKEND=chatterbox requires HF_TOKEN (get one at huggingface.co).")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        req = urllib.request.Request(
            _HF_TTS_URL,
            data=_json.dumps({"inputs": text}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=int(os.getenv("HF_TTS_TIMEOUT", "180"))) as resp:
            data = resp.read()
        output.write_bytes(data)
        log.info("TTS (chatterbox): %d bytes -> %s", len(data), output)
        return output

    def _synthesize_edge(self, text: str, output_path: str | Path) -> Path:
        """Synthesise text into an MP3 file via Edge-TTS (local, free)."""
        import edge_tts

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        async def _do() -> None:
            communicate = edge_tts.Communicate(text, self._voice)
            await communicate.save(str(output))

        asyncio.run(_do())

        size = output.stat().st_size
        log.info("TTS: %d bytes -> %s  (voice=%s)", size, output, self._voice)
        return output

    def generate_per_scene_audio(
        self,
        scenes: list,
        output_dir: str | Path,
    ) -> list[Path]:
        """Generate one MP3 per scene from its narration text.

        Args:
            scenes: Iterable of objects with a ``narration`` attribute.
            output_dir: Directory to write MP3 files into.

        Returns:
            List of Paths to the generated audio files, one per scene.
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for i, scene in enumerate(scenes):
            text = (scene.narration or "").strip()
            if not text:
                log.warning("Scene %d has no narration; skipping audio.", i)
                continue
            path = out_dir / f"scene_{i:02d}.mp3"
            self.synthesize_speech(text, path)
            paths.append(path)

        log.info("TTS: generated %d audio file(s)", len(paths))
        return paths

    def generate_script_audio(
        self,
        script_text: str,
        output_path: str | Path,
    ) -> Path:
        """Generate a single audio file from the full script text."""
        return self.synthesize_speech(script_text, output_path)
