#!/usr/bin/env python3
"""ACE-Step local music generation worker.

Ships as a marketplace asset (models/ace-step/ace_step_worker.py).
Runs as a subprocess of the Pure BPM sidecar — never imported directly.

Outputs newline-delimited JSON progress to stdout:
  {"percent": 0-100, "step": "..."}
  {"error": "human-readable message"}   ← fatal, worker exits non-zero

Writes the generated audio as WAV to --output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time


def _emit(percent: float, step: str) -> None:
    print(json.dumps({"percent": round(percent, 1), "step": step}), flush=True)


def _error(msg: str) -> None:
    print(json.dumps({"error": msg}), flush=True)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="ACE-Step local music generation")
    parser.add_argument("--prompt", required=True, help="Text description of the music")
    parser.add_argument("--duration", type=float, default=30.0, help="Duration in seconds")
    parser.add_argument("--output", required=True, help="Output WAV file path")
    parser.add_argument("--checkpoint-dir", required=True, help="Model weights directory")
    parser.add_argument("--infer-steps", type=int, default=27, help="Diffusion steps (27=fast, 60=quality)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed (optional)")
    args = parser.parse_args()

    # Validate inputs
    if not args.prompt.strip():
        _error("Prompt cannot be empty.")
    if not (10 <= args.duration <= 240):
        _error(f"Duration must be between 10 and 240 seconds (got {args.duration}).")
    if not os.path.isdir(args.checkpoint_dir):
        _error(f"Checkpoint directory not found: {args.checkpoint_dir}")

    # Check that the four weight sub-directories exist before loading anything
    required_weights = [
        os.path.join(args.checkpoint_dir, "ace_step_transformer", "diffusion_pytorch_model.safetensors"),
        os.path.join(args.checkpoint_dir, "music_dcae_f8c8", "diffusion_pytorch_model.safetensors"),
        os.path.join(args.checkpoint_dir, "music_vocoder", "diffusion_pytorch_model.safetensors"),
        os.path.join(args.checkpoint_dir, "umt5-base", "model.safetensors"),
    ]
    missing = [p for p in required_weights if not os.path.isfile(p)]
    if missing:
        _error(
            "ACE-Step model weights are incomplete. "
            "Re-install ACE-Step from the Pure Desktop Marketplace.\n"
            f"Missing: {missing[0]}"
        )

    _emit(2, "Loading ACE-Step model…")

    # Import here so startup errors are surfaced as JSON
    try:
        # The pip package installs as 'ace_step'; try that first, then fall back
        # to an import from the checkpoint dir for standalone operation.
        try:
            from ace_step.pipeline import ACEStepPipeline  # type: ignore
        except ImportError:
            # Fallback: look for pipeline_ace_step.py next to this worker
            _worker_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, _worker_dir)
            from pipeline_ace_step import ACEStepPipeline  # type: ignore
    except Exception as exc:
        _error(
            f"Could not import ACE-Step: {exc}. "
            "Re-install ACE-Step from the Pure Desktop Marketplace."
        )
        return  # unreachable; makes type checker happy

    _emit(5, "Loading model weights…")

    try:
        pipeline = ACEStepPipeline(
            checkpoint_dir=args.checkpoint_dir,
            dtype="bfloat16",   # float32 on MPS (pipeline handles the override)
        )
        pipeline.load_checkpoint(args.checkpoint_dir)
    except Exception as exc:
        _error(f"Failed to load ACE-Step model: {exc}")
        return

    _emit(20, "Generating music…")

    # Determine the output directory (pipeline writes files into a directory)
    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)

    try:
        # Use a tqdm-progress-capturing approach: monkey-patch tqdm to emit progress.
        # The pipeline reports progress via tqdm over the diffusion steps.
        _total_steps = args.infer_steps
        _progress_base = 20.0
        _progress_span = 75.0   # 20% → 95% of our scale during inference

        try:
            import tqdm as tqdm_module  # type: ignore
            _OrigTqdm = tqdm_module.tqdm

            class _ProgressTqdm(_OrigTqdm):  # type: ignore
                def update(self, n=1):
                    super().update(n)
                    completed = self.n or 0
                    total = self.total or _total_steps
                    frac = min(completed / max(total, 1), 1.0)
                    pct = _progress_base + frac * _progress_span
                    step_label = f"Generating… step {completed}/{total}"
                    _emit(pct, step_label)

            tqdm_module.tqdm = _ProgressTqdm
            _patched = True
        except Exception:
            _patched = False

        seeds = [args.seed] if args.seed is not None else None
        output_paths = pipeline(
            prompt=args.prompt,
            audio_duration=args.duration,
            infer_step=args.infer_steps,
            manual_seeds=seeds,
            save_path=out_dir,
            format="wav",
            batch_size=1,
        )

        if _patched:
            try:
                tqdm_module.tqdm = _OrigTqdm
            except Exception:
                pass

    except Exception as exc:
        _error(f"ACE-Step generation failed: {exc}")
        return

    _emit(96, "Saving audio…")

    # The pipeline writes to save_path with a timestamped filename.
    # Move it to the exact output path the caller specified.
    if not output_paths:
        _error("ACE-Step did not produce any output files.")
        return

    generated_path = output_paths[0]
    if not os.path.isfile(generated_path):
        _error(f"Output file not found at {generated_path}.")
        return

    if generated_path != args.output:
        try:
            os.replace(generated_path, args.output)
        except OSError as exc:
            _error(f"Could not move output to {args.output}: {exc}")
            return

    _emit(100, "Done")


if __name__ == "__main__":
    main()
