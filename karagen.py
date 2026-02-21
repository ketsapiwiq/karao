#!/usr/bin/env python
"""
karagen.py - Generate karaoke files from audio

Pipeline:
1. Search lyrics from lrclib database
2. Separate vocals/instrumental with demucs
3. Create .kar file with swiftf0 pitch detection
4. Play with kara.py
"""

import os
import sys
import argparse
from pathlib import Path


def find_lyrics(artist: str, title: str, duration: float = None, db_path: str = None):
    import lrclib

    db_path = db_path or "/mnt/gloubinours2/lrclib-db-dump-20260122T091251Z.sqlite3"

    with lrclib.LrcLibDB(db_path) as db:
        return db.search_by_artist_and_title(artist, title, duration)


def separate_vocals(
    audio_file: str,
    output_folder: str = None,
    model: str = "htdemucs",
    device: str = "cpu",
):
    import separation

    model_map = {m.value: m for m in separation.DemucsModel}
    demucs_model = model_map.get(model, separation.DemucsModel.HTDEMUCS)

    output_folder = output_folder or os.path.dirname(os.path.abspath(audio_file))

    result = separation.separate_audio(audio_file, output_folder, demucs_model, device)

    if result.success:
        return result.vocals_path, result.instrumental_path
    return None, None


def create_karaoke(
    vocals_file: str, lrc_content: str, output_folder: str, bpm: float = 120.0
):
    import tempfile

    lrc_file = None
    if lrc_content:
        lrc_file = os.path.join(output_folder, "lyrics.lrc")
        with open(lrc_file, "w", encoding="utf-8") as f:
            f.write(lrc_content)

    import pitch_detect

    midi_path, kar_path = pitch_detect.audio_to_midi(
        vocals_file, lrc_file=lrc_file, output_folder=output_folder, bpm=bpm
    )

    return kar_path


def main():
    parser = argparse.ArgumentParser(description="Generate karaoke from audio")
    parser.add_argument("audio_file", help="Input audio file (mp3, wav, etc.)")
    parser.add_argument("--artist", "-a", help="Artist name for lyrics search")
    parser.add_argument("--title", "-t", help="Song title for lyrics search")
    parser.add_argument("--output", "-o", help="Output folder (default: same as audio)")
    parser.add_argument(
        "--model",
        "-m",
        default="htdemucs",
        choices=[
            "htdemucs",
            "htdemucs_ft",
            "htdemucs_6s",
            "hdemucs_mmi",
            "mdx",
            "mdx_extra",
        ],
        help="Demucs model",
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
        default=120.0,
        help="Tempo (auto-detected if librosa available)",
    )
    parser.add_argument(
        "--skip-separation", action="store_true", help="Skip vocal separation"
    )
    parser.add_argument("--db", help="Path to lrclib database")
    parser.add_argument("--play", action="store_true", help="Play after generation")

    args = parser.parse_args()

    audio_file = os.path.abspath(args.audio_file)
    output_folder = args.output or os.path.dirname(audio_file) or "."
    os.makedirs(output_folder, exist_ok=True)

    basename = os.path.splitext(os.path.basename(audio_file))[0]

    print(f"Processing: {audio_file}")

    lyrics = None
    if args.artist and args.title:
        print(f"\nSearching lyrics: {args.artist} - {args.title}")
        lyrics = find_lyrics(args.artist, args.title, db_path=args.db)
        if lyrics:
            print(f"Found lyrics: {len(lyrics.lyrics)} lines")
        else:
            print("No synced lyrics found")

    vocals_path = None
    instrumental_path = None

    if not args.skip_separation:
        print(f"\nSeparating vocals (model: {args.model}, device: {args.device})...")
        vocals_path, instrumental_path = separate_vocals(
            audio_file, output_folder, args.model, args.device
        )
        if vocals_path:
            print(f"Vocals: {vocals_path}")
            print(f"Instrumental: {instrumental_path}")
        else:
            print("Separation failed, using original audio")
            vocals_path = audio_file
    else:
        vocals_path = audio_file

    print(f"\nCreating karaoke file...")
    lrc_content = lyrics.raw_lrc if lyrics else None
    kar_path = create_karaoke(vocals_path, lrc_content, output_folder, args.bpm)

    if kar_path:
        print(f"\nKaraoke file: {kar_path}")

        if instrumental_path:
            print(f"Instrumental (for backing): {instrumental_path}")

        if args.play:
            print("\nLaunching kara.py...")
            import kara

            kara.playKara(kar_path)
    else:
        print("\nFailed to create karaoke file")
        sys.exit(1)


if __name__ == "__main__":
    main()
