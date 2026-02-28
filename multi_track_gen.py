#!/usr/bin/env python
"""
multi_track_gen.py - Generate multi-track MIDI from audio using Demucs and SwiftF0

Pipeline:
1. Separate audio into 6 stems (htdemucs_6s)
2. Detect pitch for each stem using SwiftF0
3. Combine into a single multi-track MIDI file
"""

import os
import sys
import argparse
from pathlib import Path
import separation
import pitch_detect


def main():
    parser = argparse.ArgumentParser(description="Generate multi-track MIDI from audio")
    parser.add_argument("audio_file", help="Input audio file (mp3, wav, etc.)")
    parser.add_argument("--output", "-o", help="Output folder (default: same as audio)")
    parser.add_argument(
        "--model",
        "-m",
        default="htdemucs_6s",
        choices=[
            "htdemucs",
            "htdemucs_ft",
            "htdemucs_6s",
            "hdemucs_mmi",
        ],
        help="Demucs model (htdemucs_6s recommended for multi-track)",
    )
    parser.add_argument(
        "--device",
        "-d",
        default="cpu",
        choices=["cpu", "cuda"],
        help="Processing device",
    )
    parser.add_argument(
        "--bpm",
        type=float,
        default=None,
        help="Tempo (auto-detected if librosa available)",
    )

    parser.add_argument(
        "--no-vocals",
        action="store_true",
        help="Skip the vocal track in the generated MIDI",
    )
    parser.add_argument(
        "--both",
        action="store_true",
        help="Generate both full and instrumental MIDI files",
    )

    args = parser.parse_args()

    audio_file = os.path.abspath(args.audio_file)
    output_folder = args.output or os.path.dirname(audio_file) or "."
    os.makedirs(output_folder, exist_ok=True)

    basename = os.path.splitext(os.path.basename(audio_file))[0]
    
    print(f"Processing: {audio_file}")
    
    # 1. Separate audio
    print(f"Separating stems with {args.model}...")
    # Use two_stems=None to get all stems
    result = separation.separate_audio(
        audio_file, output_folder, separation.DemucsModel(args.model), args.device, two_stems=None
    )
    
    if not result.success:
        print(f"Separation failed: {result.error}")
        sys.exit(1)
        
    # 2. Find all stems
    separation_dir = os.path.join(output_folder, "separated", args.model, basename)
    
    # 3. Detect BPM if not provided
    bpm = args.bpm
    if bpm is None:
        try:
            import librosa
            # Try to use drums for better BPM detection if available
            bpm_source = os.path.join(separation_dir, "drums.wav")
            if not os.path.exists(bpm_source):
                bpm_source = audio_file
                
            print(f"Detecting BPM from {os.path.basename(bpm_source)}...")
            # Use librosa with soundfile backend to be safer
            y, sr = librosa.load(bpm_source)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            # librosa returns an array for tempo in recent versions
            if isinstance(tempo, (list, tuple, object)) and hasattr(tempo, "__getitem__"):
                bpm = float(tempo[0])
            else:
                bpm = float(tempo)
            print(f"Detected BPM: {bpm:.1f}")
        except Exception as e:
            bpm = 120.0
            print(f"Could not detect BPM ({e}), using default 120.0")

    # 4. Generate multi-track MIDI
    modes = []
    if args.both:
        modes = [False, True] # [full, instrumental]
    else:
        modes = [args.no_vocals]

    for no_vocals in modes:
        stem_files = {}
        # Common stem names for demucs models
        possible_stems = ["vocals", "drums", "bass", "other", "guitar", "piano"]
        for stem in possible_stems:
            if no_vocals and stem == "vocals":
                continue
            stem_path = os.path.join(separation_dir, f"{stem}.wav")
            if os.path.exists(stem_path):
                stem_files[stem] = stem_path
                
        if not stem_files:
            print(f"No stems found for {'instrumental' if no_vocals else 'full'} mode")
            continue
            
        suffix = "_instrumental" if no_vocals else "_multitrack"
        output_midi = os.path.join(output_folder, f"{basename}{suffix}.mid")
        print(f"Generating multi-track MIDI ({'instrumental' if no_vocals else 'full'}): {output_midi}...")
        
        pitch_detect.multi_audio_to_midi(
            stem_files,
            output_midi,
            bpm=bpm
        )
    
    print(f"Success! Generation complete.")


if __name__ == "__main__":
    main()
