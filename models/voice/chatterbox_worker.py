#!/usr/bin/env python3
"""Chatterbox TTS/voice-cloning worker.

Ships as a marketplace asset (models/voice/chatterbox_worker.py).
Runs as a subprocess of the Pure BPM sidecar — never imported directly.

Outputs newline-delimited JSON progress to stdout:
  {"percent": 0-100, "step": "..."}
  {"error": "human-readable message"}   ← fatal, worker exits non-zero

Writes the generated WAV to --output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _emit(percent: float, step: str) -> None:
    print(json.dumps({"percent": round(percent, 1), "step": step}), flush=True)


def _error(msg: str) -> None:
    print(json.dumps({"error": msg}), flush=True)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chatterbox TTS voice generation")
    parser.add_argument("--text", required=True, help="Text to synthesize")
    parser.add_argument("--output", required=True, help="Output WAV file path")
    parser.add_argument("--checkpoint-dir", required=True, help="Model weights directory")
    parser.add_argument("--reference", default=None, help="Reference audio file for voice cloning (optional)")
    parser.add_argument("--exaggeration", type=float, default=0.5, help="Expression intensity (0–2, default 0.5)")
    parser.add_argument("--cfg-weight", type=float, default=0.5, help="CFG/pace weight (0.2–1.0, default 0.5)")
    parser.add_argument("--temperature", type=float, default=0.8, help="Sampling temperature (default 0.8)")
    args = parser.parse_args()

    if not args.text.strip():
        _error("Text cannot be empty.")
    if not os.path.isdir(args.checkpoint_dir):
        _error(f"Checkpoint directory not found: {args.checkpoint_dir}")

    required = [
        os.path.join(args.checkpoint_dir, "t3_cfg.pt"),
        os.path.join(args.checkpoint_dir, "s3gen.pt"),
        os.path.join(args.checkpoint_dir, "ve.pt"),
        os.path.join(args.checkpoint_dir, "tokenizer.json"),
    ]
    missing = [p for p in required if not os.path.isfile(p)]
    if missing:
        _error(
            "Chatterbox model weights are incomplete. "
            "Re-install Voice from the Pure Desktop Marketplace.\n"
            f"Missing: {missing[0]}"
        )

    if args.reference and not os.path.isfile(args.reference):
        _error(f"Reference audio file not found: {args.reference}")

    _emit(5, "Loading Voice model…")

    try:
        import torch
        from chatterbox.tts import ChatterboxTTS  # type: ignore
    except ImportError as exc:
        _error(
            f"Could not import chatterbox: {exc}. "
            "Re-install Voice from the Pure Desktop Marketplace."
        )
        return

    # Auto-select device: MPS (Apple Silicon) → CPU fallback
    if torch.backends.mps.is_available():
        device = "mps"
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"

    _emit(10, f"Loading model on {device.upper()}…")

    try:
        model = ChatterboxTTS.from_local(args.checkpoint_dir, device)
    except Exception as exc:
        _error(f"Failed to load Chatterbox model: {exc}")
        return

    _emit(40, "Synthesizing speech…")

    try:
        gen_kwargs: dict = {
            "exaggeration": float(args.exaggeration),
            "cfg_weight": float(args.cfg_weight),
            "temperature": float(args.temperature),
        }
        if args.reference:
            gen_kwargs["audio_prompt_path"] = args.reference

        wav = model.generate(args.text[:300], **gen_kwargs)
    except Exception as exc:
        _error(f"Voice generation failed: {exc}")
        return

    _emit(90, "Saving audio…")

    try:
        import torchaudio
        out_dir = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(out_dir, exist_ok=True)
        torchaudio.save(args.output, wav.cpu(), model.sr)
    except Exception as exc:
        _error(f"Could not save output: {exc}")
        return

    _emit(100, "Done")


if __name__ == "__main__":
    main()
