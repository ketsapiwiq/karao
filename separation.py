#!/usr/bin/env python
"""
demucs.py - Separate vocals from audio using demucs

Scavenged from UltraSinger/src/modules/Audio/separation.py

This module provides instrumental/vocal separation using demucs models.
Output is an instrumental (no_vocals) audio file for karaoke backing tracks.
"""

import os
import subprocess
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


class DemucsModel(Enum):
    """Available demucs models for source separation"""

    HTDEMUCS = "htdemucs"
    HTDEMUCS_FT = "htdemucs_ft"
    HTDEMUCS_6S = "htdemucs_6s"
    HDEMUCS_MMI = "hdemucs_mmi"
    MDX = "mdx"
    MDX_EXTRA = "mdx_extra"
    MDX_Q = "mdx_q"
    MDX_EXTRA_Q = "mdx_extra_q"


@dataclass
class SeparationResult:
    """Result of audio separation"""

    vocals_path: Optional[str]
    instrumental_path: Optional[str]
    output_folder: str
    model_used: str
    success: bool
    error: Optional[str] = None


def check_demucs_installed() -> bool:
    """Check if demucs is available"""
    try:
        import demucs

        return True
    except ImportError:
        return False


def separate_audio(
    input_file: str,
    output_folder: str,
    model: DemucsModel = DemucsModel.HTDEMUCS,
    device: str = "cpu",
    two_stems: Optional[str] = "vocals",
) -> SeparationResult:
    """
    Separate audio into stems using demucs.

    Args:
        input_file: Path to input audio file (mp3, wav, etc.)
        output_folder: Folder to save separated tracks
        model: Demucs model to use
        device: "cpu" or "cuda" for GPU acceleration
        two_stems: Stem name to separate from the rest (e.g. "vocals"), or None for all stems.

    Returns:
        SeparationResult with paths to separated files
    """
    if not os.path.exists(input_file):
        return SeparationResult(
            vocals_path=None,
            instrumental_path=None,
            output_folder=output_folder,
            model_used=model.value,
            success=False,
            error=f"Input file not found: {input_file}",
        )

    os.makedirs(output_folder, exist_ok=True)

    basename = os.path.splitext(os.path.basename(input_file))[0]
    separation_output = os.path.join(output_folder, "separated", model.value, basename)

    vocals_path = os.path.join(separation_output, "vocals.wav")
    instrumental_path = os.path.join(separation_output, "no_vocals.wav")

    # If two_stems is requested and both exist, return them
    if two_stems and os.path.exists(vocals_path) and os.path.exists(instrumental_path):
        return SeparationResult(
            vocals_path=vocals_path,
            instrumental_path=instrumental_path,
            output_folder=output_folder,
            model_used=model.value,
            success=True,
        )

    try:
        import demucs.separate

        args = [
            "-d",
            device,
            "--float32",
            "-n",
            model.value,
            "--out",
            os.path.join(output_folder, "separated"),
            input_file,
        ]
        if two_stems:
            args = ["--two-stems", two_stems] + args

        demucs.separate.main(args)

        return SeparationResult(
            vocals_path=vocals_path if os.path.exists(vocals_path) else None,
            instrumental_path=instrumental_path
            if os.path.exists(instrumental_path)
            else None,
            output_folder=output_folder,
            model_used=model.value,
            success=True,
        )

    except Exception as e:
        return SeparationResult(
            vocals_path=None,
            instrumental_path=None,
            output_folder=output_folder,
            model_used=model.value,
            success=False,
            error=str(e),
        )


def get_instrumental(
    audio_file: str,
    output_folder: Optional[str] = None,
    model: DemucsModel = DemucsModel.HTDEMUCS,
    device: str = "cpu",
    force_reprocess: bool = False,
) -> Optional[str]:
    """
    Get or create an instrumental (no vocals) version of an audio file.

    Args:
        audio_file: Path to input audio file
        output_folder: Where to save separated tracks (default: same dir as input)
        model: Demucs model to use
        device: "cpu" or "cuda"
        force_reprocess: Reprocess even if cached files exist

    Returns:
        Path to instrumental (no_vocals.wav) file, or None on failure
    """
    if output_folder is None:
        output_folder = os.path.dirname(os.path.abspath(audio_file))

    basename = os.path.splitext(os.path.basename(audio_file))[0]
    expected_instrumental = os.path.join(
        output_folder, "separated", model.value, basename, "no_vocals.wav"
    )

    if os.path.exists(expected_instrumental) and not force_reprocess:
        return expected_instrumental

    result = separate_audio(audio_file, output_folder, model, device)

    if result.success:
        return result.instrumental_path
    else:
        print(f"Separation failed: {result.error}")
        return None


def get_vocals(
    audio_file: str,
    output_folder: Optional[str] = None,
    model: DemucsModel = DemucsModel.HTDEMUCS,
    device: str = "cpu",
    force_reprocess: bool = False,
) -> Optional[str]:
    """
    Get or create a vocals-only version of an audio file.

    Args:
        audio_file: Path to input audio file
        output_folder: Where to save separated tracks (default: same dir as input)
        model: Demucs model to use
        device: "cpu" or "cuda"
        force_reprocess: Reprocess even if cached files exist

    Returns:
        Path to vocals.wav file, or None on failure
    """
    if output_folder is None:
        output_folder = os.path.dirname(os.path.abspath(audio_file))

    basename = os.path.splitext(os.path.basename(audio_file))[0]
    expected_vocals = os.path.join(
        output_folder, "separated", model.value, basename, "vocals.wav"
    )

    if os.path.exists(expected_vocals) and not force_reprocess:
        return expected_vocals

    result = separate_audio(audio_file, output_folder, model, device)

    if result.success:
        return result.vocals_path
    else:
        print(f"Separation failed: {result.error}")
        return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python demucs.py <audio_file> [output_folder] [model] [device]")
        print(
            "\nModels: htdemucs (default), htdemucs_ft, htdemucs_6s, hdemucs_mmi, mdx, mdx_extra"
        )
        print("Device: cpu (default), cuda")
        sys.exit(1)

    audio_file = sys.argv[1]
    output_folder = sys.argv[2] if len(sys.argv) > 2 else None
    model_name = sys.argv[3] if len(sys.argv) > 3 else "htdemucs"
    device = sys.argv[4] if len(sys.argv) > 4 else "cpu"

    model_map = {m.value: m for m in DemucsModel}
    model = model_map.get(model_name, DemucsModel.HTDEMUCS)

    print(f"Separating: {audio_file}")
    print(f"Model: {model.value}, Device: {device}")

    result = separate_audio(
        audio_file, output_folder or os.path.dirname(audio_file), model, device
    )

    if result.success:
        print(f"\nVocals: {result.vocals_path}")
        print(f"Instrumental: {result.instrumental_path}")
    else:
        print(f"\nError: {result.error}")
        sys.exit(1)
