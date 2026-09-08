#!/usr/bin/env python3
"""Matchering worker — GPL-3 isolated subprocess.

Pure Desktop spawns this as a subprocess from the sidecar; it is NEVER imported
into the proprietary sidecar process. GPL-3 code lives entirely in this script
and the isolated venv under models/matchering-venv/.

Usage:
    python matchering_worker.py --target TARGET --reference REFERENCE --output OUTPUT

Writes JSON-line progress to stdout: {"percent": N, "step": "..."} or {"error": "..."}.
Exits 0 on success, 1 on any failure.

Source: https://github.com/sergree/matchering (GPL-3)
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _emit(percent: float, step: str) -> None:
    print(json.dumps({"percent": round(percent), "step": step}), flush=True)


def _emit_error(msg: str) -> None:
    print(json.dumps({"error": msg}), flush=True)


# Map matchering 2.x info strings (exactly as produced by explanations.py) to
# progress percent + user-facing step labels. Using exact-match on the English
# strings is reliable because these are the module's own public log messages —
# they don't change between patch releases.
_INFO_PROGRESS: dict[str, tuple[float, str]] = {
    "Loading and analysis":              (20, "Loading and analysing audio…"),
    "Matching levels":                   (40, "Matching levels to reference…"),
    "Matching frequencies":              (60, "Matching frequencies…"),
    "Correcting levels":                 (78, "Correcting levels…"),
    "Final processing and saving":       (90, "Final processing…"),
    "Exporting various audio formats":   (95, "Writing output…"),
    "The task is completed":             (100, "Done"),
}


def _make_info_handler():
    """Return the callable passed to mg.log(info_handler=...).

    Matchering 2.x calls info_handler(message_string) — a plain string from
    explanations.py, NOT a Logger object. We map the known strings to progress
    events; unknown strings are silently ignored so future matchering versions
    that add new log messages don't break the worker.
    """
    def handler(message: str) -> None:
        entry = _INFO_PROGRESS.get(message)
        if entry:
            pct, step = entry
            _emit(pct, step)
    return handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Matchering local mastering worker")
    parser.add_argument("--target", required=True, help="Path to the target audio file")
    parser.add_argument("--reference", required=True, help="Path to the reference audio file")
    parser.add_argument("--output", required=True, help="Path for the mastered output WAV")
    args = parser.parse_args()

    # Validate inputs before importing the heavy library.
    for flag, path in (("--target", args.target), ("--reference", args.reference)):
        if not os.path.isfile(path):
            _emit_error(f"{flag}: file not found: {path!r}")
            return 1

    out_dir = os.path.dirname(os.path.abspath(args.output))
    if not os.path.isdir(out_dir):
        _emit_error(f"--output directory does not exist: {out_dir!r}")
        return 1

    _emit(5, "Loading Matchering…")

    try:
        import matchering as mg
    except ImportError as exc:
        _emit_error(
            f"Matchering is not installed in the isolated venv: {exc}. "
            "Re-install the Matchering model from the Marketplace."
        )
        return 1

    # mg.log() is set_handlers() — wire the info handler BEFORE calling process().
    # The handler receives plain strings; matchering 2.x has no Logger class.
    mg.log(info_handler=_make_info_handler())

    _emit(10, "Starting mastering…")

    try:
        mg.process(
            target=args.target,
            reference=args.reference,
            # mg.pcm24(path) = Result(path, "PCM_24") — the correct 2.x output helper.
            results=[mg.pcm24(args.output)],
        )
    except Exception as exc:
        _emit_error(str(exc))
        return 1

    if not os.path.isfile(args.output) or os.path.getsize(args.output) == 0:
        _emit_error("Matchering produced no output.")
        return 1

    _emit(100, "Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
