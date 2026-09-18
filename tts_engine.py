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
        if backend == "kokoro":
            try:
                return self._synthesize_kokoro(text, output_path)
            except Exception as exc:
                log.warning("Kokoro failed (%s); falling back to Edge", str(exc)[:80])
                return self._synthesize_edge(text, output_path)
        if backend == "cosyvoice3":
            try:
                return self._synthesize_cosyvoice3(text, output_path)
            except Exception as exc:
                log.warning("CosyVoice3 failed (%s); falling back to Edge", str(exc)[:80])
                return self._synthesize_edge(text, output_path)
        if backend == "kitten":
            try:
                return self._synthesize_kitten(text, output_path)
            except Exception as exc:
                log.warning("KittenTTS failed (%s); falling back to Edge", str(exc)[:80])
                return self._synthesize_edge(text, output_path)
        return self._synthesize_edge(text, output_path)

    def _synthesize_kitten(self, text: str, output_path: str | Path) -> Path:
        """KittenTTS (ONNX, CPU-fast, 24kHz) via shared venv. Voice: Hugo."""
        import tempfile, subprocess as _sp

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        wav_out = output.with_suffix(".wav")
        voice = os.getenv("KITTEN_VOICE", "Hugo")
        wrapper = os.getenv("KITTEN_WRAPPER", "/root/flow_sync/kitten_synth.py")
        py = os.getenv("KITTEN_PY", "/usr/local/lib/hermes-agent/venv/bin/python3")

        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write(text); tpath = fh.name
        try:
            r = _sp.run([py, wrapper, tpath, str(wav_out), voice],
                        capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                raise RuntimeError(r.stderr[-300:])
        finally:
            try: os.remove(tpath)
            except Exception: pass

        # WAV -> MP3 (fork expects mp3)
        _sp.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_out),
                 "-c:a", "libmp3lame", "-q:a", "4", str(output)], check=False)
        if wav_out.exists() and wav_out != output:
            wav_out.unlink(missing_ok=True)
        log.info("TTS (kitten %s): %s <- %s bytes", voice, output.name, output.stat().st_size)
        return output

    def _synthesize_cosyvoice3(self, text: str, output_path: str | Path) -> Path:
        """Local CosyVoice3 GGUF TTS via CrispASR CLI (free, local, neural)."""
        import subprocess as _sp

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        wav_out = output.with_suffix(".wav")

        crispasr = os.getenv("CRISPASR", "/root/CrispASR/build/bin/crispasr")
        model = os.getenv("CRISPASR_MODEL",
                          "/root/cosyvoice3_models/cosyvoice3-llm-q4_k.gguf")
        voice = os.getenv("COSYVOICE3_VOICE", "fleurs-en")

        cmd = [crispasr, "--backend", "cosyvoice3-tts", "-m", model,
               "--voice", voice, "--i-have-rights",
               "--no-c2pa", "--no-spoken-disclaimer",
               "--accept-marking-responsibility",
               "--tts", text, "--tts-output", str(wav_out)]
        r = _sp.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-300:] or r.stdout[-300:])
        if not wav_out.exists():
            raise RuntimeError("CosyVoice3 produced no output wav")

        # WAV -> MP3 (the fork expects mp3 files)
        _sp.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_out),
                 "-c:a", "libmp3lame", "-q:a", "4", str(output)], check=False)
        if wav_out.exists() and wav_out != output:
            wav_out.unlink(missing_ok=True)
        log.info("TTS (cosyvoice3 %s): %s <- %s bytes", voice, output.name, output.stat().st_size)
        return output

    def _synthesize_kokoro(self, text: str, output_path: str | Path) -> Path:
        """Local Kokoro neural TTS (voice am_adam) via isolated venv wrapper.

        Kokoro lives in /root/tts-chatterbox venv (CPU torch, avoids nvidia on
        the shared venv). This method shells out to the wrapper and produces an
        MP3. Free, local, and a clear upgrade in naturalness over Piper.
        """
        import tempfile, subprocess as _sp

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        voice = os.getenv("KOKORO_VOICE", "am_adam")
        wrapper = os.getenv("KOKORO_WRAPPER", "/root/flow_sync/kokoro_synth.py")
        kv = os.getenv("KOKORO_VENV", "/root/tts-chatterbox/bin/python")

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write(text)
            tpath = fh.name
        try:
            r = _sp.run([kv, wrapper, voice, tpath, str(output)],
                        capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                raise RuntimeError(r.stderr[-300:])
        finally:
            try: os.remove(tpath)
            except Exception: pass
        log.info("TTS (kokoro %s): %s <- %s bytes", voice, output.name, output.stat().st_size)
        return output

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
