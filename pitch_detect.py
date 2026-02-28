#!/usr/bin/env python
"""
swiftf0.py - F0 pitch detection and MIDI/KAR file generation using SwiftF0

Produces MIDI files from audio using SwiftF0 for pitch detection.
Processes both original vocals and separated vocals from demucs.

Output:
- .mid file: Standard MIDI with lyrics
- .kar file: Karaoke MIDI (compatible with midifile.py and kara.py)
"""

import os
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class MidiSegment:
    note: str
    start: float
    end: float
    word: str = ""


def check_dependencies() -> Tuple[bool, str]:
    missing = []
    try:
        from swift_f0 import SwiftF0
    except ImportError:
        missing.append("swift-f0")
    try:
        import librosa
    except ImportError:
        missing.append("librosa")
    try:
        import numpy
    except ImportError:
        missing.append("numpy")
    try:
        import pretty_midi
    except ImportError:
        missing.append("pretty_midi")
    try:
        import unidecode
    except ImportError:
        missing.append("unidecode")

    if missing:
        return False, f"pip install {' '.join(missing)}"
    return True, ""


def get_pitch_swiftf0(
    audio_file: str,
    fmin: float = 46.875,
    fmax: float = 2093.75,
    confidence_threshold: float = 0.9,
):
    from swift_f0 import SwiftF0

    detector = SwiftF0(fmin=fmin, fmax=fmax, confidence_threshold=confidence_threshold)
    return detector.detect_from_file(audio_file)


def freq_to_note(freq: float) -> str:
    import librosa

    if freq <= 0:
        return "REST"
    return librosa.hz_to_note(freq)


def segment_to_midi_note(
    result, confidence_threshold: float = 0.5
) -> List[MidiSegment]:
    from swift_f0 import segment_notes, NoteSegment
    import librosa

    notes = segment_notes(
        result,
        split_semitone_threshold=0.8,
        min_note_duration=0.05,
        unvoiced_grace_period=0.02,
    )

    segments = []
    for note in notes:
        note_name = librosa.midi_to_note(note.pitch_midi)
        segments.append(
            MidiSegment(note=note_name, start=note.start, end=note.end, word="")
        )
    return segments


def lrc_to_segments(result, lrc_content: str) -> List[MidiSegment]:
    segments = []
    pattern = r"\[(\d+):(\d+(?:[.:]\d+)?)\](.*)"

    lines = []
    for line in lrc_content.split("\n"):
        line = line.strip()
        match = re.match(pattern, line)
        if match:
            minutes = int(match.group(1))
            time_part = match.group(2)
            if ":" in time_part:
                parts = time_part.split(":")
                seconds = int(parts[0])
                cents = int(parts[1]) if len(parts) > 1 else 0
            elif "." in time_part:
                parts = time_part.split(".")
                seconds = int(parts[0])
                cents = int(parts[1].ljust(2, "0")[:2])
            else:
                seconds = int(time_part)
                cents = 0

            time_seconds = minutes * 60 + seconds + cents / 100.0
            text = match.group(3).strip()
            if text:
                lines.append((time_seconds, text))

    import numpy as np

    for i, (time, text) in enumerate(lines):
        end_time = lines[i + 1][0] if i + 1 < len(lines) else time + 2.0

        mask = (result.timestamps >= time) & (result.timestamps < end_time)
        voiced_mask = mask & result.voicing

        if np.any(voiced_mask):
            voiced_pitches = result.pitch_hz[voiced_mask]
            median_pitch = (
                float(np.median(voiced_pitches[voiced_pitches > 0]))
                if np.any(voiced_pitches > 0)
                else 0
            )
            note = freq_to_note(median_pitch) if median_pitch > 0 else "REST"
        else:
            note = "REST"

        segments.append(MidiSegment(note=note, start=time, end=end_time, word=text))

    return segments


def segments_to_midi(
    segments: List[MidiSegment],
    bpm: float,
    output_path: Optional[str] = None,
    instrument_name: str = "Vocals",
    program: int = 0,
    is_drum: bool = False,
    midi_data: Optional[object] = None,
) -> object:
    import pretty_midi
    import librosa
    import unidecode

    if midi_data is None:
        midi_data = pretty_midi.PrettyMIDI(initial_tempo=bpm)

    instrument = pretty_midi.Instrument(
        program=program, name=instrument_name, is_drum=is_drum
    )
    velocity = 100

    for segment in segments:
        if segment.note != "REST":
            try:
                note_number = librosa.note_to_midi(segment.note)
                note = pretty_midi.Note(
                    velocity, note_number, segment.start, segment.end
                )
                instrument.notes.append(note)
            except Exception:
                continue

            if segment.word:
                sanitized = unidecode.unidecode(segment.word)
                midi_data.lyrics.append(
                    pretty_midi.Lyric(text=sanitized, time=segment.start)
                )

    midi_data.instruments.append(instrument)

    if output_path:
        midi_data.write(output_path)
    return midi_data


def create_kar_file(segments: List[MidiSegment], bpm: float, output_path: str) -> str:
    import pretty_midi
    import librosa
    import unidecode

    midi_data = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    melody_track = pretty_midi.Instrument(program=0, name="Melody")
    lyrics_track = pretty_midi.Instrument(program=0, name="Lyrics")
    velocity = 100

    for segment in segments:
        if segment.note != "REST":
            note_number = librosa.note_to_midi(segment.note)
            note = pretty_midi.Note(velocity, note_number, segment.start, segment.end)
            melody_track.notes.append(note)

        if segment.word:
            sanitized = unidecode.unidecode(segment.word)
            midi_data.lyrics.append(
                pretty_midi.Lyric(text=sanitized, time=segment.start)
            )

    midi_data.instruments.append(melody_track)
    midi_data.instruments.append(lyrics_track)
    midi_data.write(output_path)
    return output_path


def clean_midi_instrument(instrument, min_duration=0.1, min_velocity=30):
    """Remove short notes and low velocity noise from an instrument."""
    cleaned_notes = []
    for note in instrument.notes:
        if (note.end - note.start) >= min_duration and note.velocity >= min_velocity:
            cleaned_notes.append(note)
    instrument.notes = cleaned_notes
    return instrument


def basic_pitch_to_midi(
    audio_file: str,
    midi_data: Optional[object] = None,
    instrument_name: str = "Piano",
    program: int = 0,
) -> object:
    from basic_pitch.inference import predict
    import pretty_midi

    print(f"Polyphonic transcription for {instrument_name} (High Quality Mode)...")
    # Higher thresholds = cleaner output, fewer ghost notes
    model_output, midi_data_bp, notes = predict(
        audio_file,
        onset_threshold=0.6,
        frame_threshold=0.4,
        minimum_note_length=120, # ms
    )
    
    if midi_data_bp.instruments:
        instr = midi_data_bp.instruments[0]
        instr.name = instrument_name
        instr.program = program
        # Apply cleaning
        instr = clean_midi_instrument(instr)
        
        if midi_data is None:
            # Create new with correct BPM
            # Note: predict() doesn't know our BPM, so we just take the notes
            midi_data = pretty_midi.PrettyMIDI() 
            midi_data.instruments.append(instr)
        else:
            midi_data.instruments.append(instr)
            
    return midi_data


def multi_audio_to_midi(
    stem_files: dict[str, str],
    output_path: str,
    bpm: float = 120.0,
    fmin: float = 46.875,
    fmax: float = 2093.75,
    confidence_threshold: float = 0.9,
) -> str:
    import pretty_midi

    midi_data = pretty_midi.PrettyMIDI(initial_tempo=bpm)

    # Stem name to MIDI program (General MIDI)
    program_map = {
        "vocals": 0,  # Piano (often used for vocals in MIDI)
        "bass": 33,  # Electric Bass (finger)
        "guitar": 25,  # Acoustic Guitar (steel)
        "piano": 0,  # Acoustic Grand Piano
        "other": 48,  # String Ensemble 1
    }

    polyphonic_stems = ["guitar", "piano", "other"]

    for stem_name, audio_file in stem_files.items():
        stem_name_lower = stem_name.lower()
        if not os.path.exists(audio_file):
            print(f"Skipping missing stem: {stem_name} ({audio_file})")
            continue

        if stem_name_lower == "drums":
            # For now, skip drums to avoid noise, or we could add a simple beat
            print("Skipping drums in MIDI generation to avoid noise...")
            continue

        program = program_map.get(stem_name_lower, 0)
        
        if stem_name_lower in polyphonic_stems:
            try:
                midi_data = basic_pitch_to_midi(
                    audio_file,
                    midi_data=midi_data,
                    instrument_name=stem_name.capitalize(),
                    program=program
                )
            except Exception as e:
                print(f"Error in basic-pitch for {stem_name}: {e}")
        else:
            # Monophonic for vocals and bass
            print(f"Monophonic transcription for {stem_name}...")
            try:
                result = get_pitch_swiftf0(audio_file, fmin, fmax, confidence_threshold)
                segments = segment_to_midi_note(result, confidence_threshold)

                if segments:
                    segments_to_midi(
                        segments,
                        bpm,
                        instrument_name=stem_name.capitalize(),
                        program=program,
                        is_drum=False,
                        midi_data=midi_data,
                    )
            except Exception as e:
                print(f"Error in swift-f0 for {stem_name}: {e}")

    midi_data.write(output_path)
    return output_path


def audio_to_midi(
    audio_file: str,
    lrc_file: Optional[str] = None,
    output_folder: Optional[str] = None,
    bpm: float = 120.0,
    fmin: float = 46.875,
    fmax: float = 2093.75,
    confidence_threshold: float = 0.9,
) -> Tuple[Optional[str], Optional[str]]:
    deps_ok, msg = check_dependencies()
    if not deps_ok:
        print(f"Missing: {msg}")
        return None, None

    if output_folder is None:
        output_folder = os.path.dirname(os.path.abspath(audio_file)) or "."

    basename = os.path.splitext(os.path.basename(audio_file))[0]
    midi_path = os.path.join(output_folder, f"{basename}.mid")
    kar_path = os.path.join(output_folder, f"{basename}.kar")

    try:
        import librosa

        y, sr = librosa.load(audio_file, sr=None)
        detected_bpm, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(detected_bpm) if detected_bpm > 0 else bpm
        print(f"BPM: {bpm:.1f}")
    except Exception:
        pass

    print(f"Pitch detection with SwiftF0...")
    result = get_pitch_swiftf0(audio_file, fmin, fmax, confidence_threshold)

    segments = []
    if lrc_file and os.path.exists(lrc_file):
        with open(lrc_file, "r", encoding="utf-8") as f:
            lrc_content = f.read()
        segments = lrc_to_segments(result, lrc_content)
    else:
        segments = segment_to_midi_note(result, confidence_threshold)

    if segments:
        print(f"Writing: {midi_path}")
        segments_to_midi(segments, bpm, midi_path)
        print(f"Writing: {kar_path}")
        create_kar_file(segments, bpm, kar_path)
        return midi_path, kar_path

    return None, None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python swiftf0.py <audio_file> [lrc_file] [output_folder] [bpm]")
        sys.exit(1)

    audio_file = sys.argv[1]
    lrc_file = sys.argv[2] if len(sys.argv) > 2 else None
    output_folder = sys.argv[3] if len(sys.argv) > 3 else None
    bpm = float(sys.argv[4]) if len(sys.argv) > 4 else 120.0

    deps_ok, msg = check_dependencies()
    if not deps_ok:
        print(f"Missing: {msg}")
        sys.exit(1)

    midi_path, kar_path = audio_to_midi(audio_file, lrc_file, output_folder, bpm)

    if midi_path:
        print(f"\nMIDI: {midi_path}")
        print(f"KAR: {kar_path}")
    else:
        print("Failed.")
        sys.exit(1)
