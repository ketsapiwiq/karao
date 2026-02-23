#!/usr/bin/env python
"""
kara2.py - Karaoke player for audio + LRC files

Plays instrumental audio with synchronized lyrics from LRC file.
Unlike kara.py (which plays .kar MIDI files), this plays any audio format.

Usage:
    python kara2.py <audio_file> <lrc_file>
    python kara2.py separated/htdemucs/rachida/no_vocals.wav rachida_words.lrc
"""

import re
import sys
import time
import pygame
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class LyricWord:
    time: float
    word: str
    line_idx: int = 0


def parse_word_lrc(lrc_path: str) -> Tuple[List[LyricWord], int]:
    """Parse word-level LRC format.
    Each line in the LRC file is a display line.
    Returns (words, num_lines)."""
    words = []
    line_idx = 0

    with open(lrc_path, "r", encoding="utf-8") as f:
        for lrc_line in f:
            lrc_line = lrc_line.strip()
            if not lrc_line:
                continue

            pattern = r"\[(\d+):(\d+\.?\d*)\]([^\[]*)"
            matches = re.findall(pattern, lrc_line)

            line_has_words = False
            for match in matches:
                mins, secs, word = match
                time_sec = float(mins) * 60 + float(secs)
                word = word.strip()
                if word:
                    words.append(LyricWord(time=time_sec, word=word, line_idx=line_idx))
                    line_has_words = True

            if line_has_words:
                line_idx += 1

    return sorted(words, key=lambda w: w.time), line_idx


def group_into_lines(words: List[LyricWord]) -> List[Tuple[float, List[LyricWord]]]:
    """Group words by their line_idx into display lines."""
    if not words:
        return []

    lines = {}
    for word in words:
        if word.line_idx not in lines:
            lines[word.line_idx] = []
        lines[word.line_idx].append(word)

    result = []
    for idx in sorted(lines.keys()):
        line_words = lines[idx]
        line_start = line_words[0].time
        result.append((line_start, line_words))

    return result


class KaraokeDisplay:
    def __init__(
        self,
        words: List[LyricWord],
        screen_width: int = 2000,
        screen_height: int = 1200,
    ):
        self.words = words
        self.lines = group_into_lines(words)
        self.word_idx = 0

        pygame.init()
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        pygame.display.set_caption("Karaoke")

        self.font = pygame.font.Font(None, 60)
        self.active_color = (100, 100, 250)
        self.base_color = (250, 250, 250)

        self.line_a = ["", "", ""]
        self.line_b = ["", "", ""]
        self.current_line_idx = 0
        self.line_word_indices = []  # (line_idx, start_word_idx, end_word_idx)

        self._compute_line_indices()

    def _compute_line_indices(self):
        """Precompute which words belong to which lines"""
        self.line_word_indices = []
        word_idx = 0
        for line_start, line_words in self.lines:
            start_idx = word_idx
            end_idx = word_idx + len(line_words) - 1
            self.line_word_indices.append(
                (len(self.line_word_indices), start_idx, end_idx)
            )
            word_idx = end_idx + 1

    def update(self, current_time: float):
        """Update display based on current playback time"""
        # Find current word index
        while (
            self.word_idx < len(self.words) - 1
            and self.words[self.word_idx + 1].time <= current_time
        ):
            self.word_idx += 1

        # Find which lines to display (current + next 2)
        current_line = -1
        for line_idx, start_idx, end_idx in self.line_word_indices:
            if start_idx <= self.word_idx <= end_idx:
                current_line = line_idx
                break
            elif start_idx > self.word_idx:
                current_line = max(0, line_idx - 1)
                break

        if current_line == -1:
            current_line = len(self.lines) - 1

        # Build display lines
        self.line_a = ["", "", ""]
        self.line_b = ["", "", ""]

        for i in range(3):
            line_idx = current_line + i
            if line_idx >= len(self.lines):
                break

            _, line_words = self.lines[line_idx]
            _, start_idx, end_idx = self.line_word_indices[line_idx]

            # Words already sung (active)
            sung_end = min(self.word_idx, end_idx)
            if sung_end >= start_idx:
                sung_words = [w.word for w in line_words[: sung_end - start_idx + 1]]
                self.line_a[i] = " ".join(sung_words)

            # Words not yet sung (base)
            unsung_start = max(self.word_idx + 1, start_idx)
            if unsung_start <= end_idx:
                unsung_words = [w.word for w in line_words[unsung_start - start_idx :]]
                self.line_b[i] = " ".join(unsung_words)

    def render(self):
        """Render the current display"""
        self.screen.fill(0)

        for iline in range(3):
            # Calculate total line width for centering
            total_width = self.font.size(self.line_a[iline] + " " + self.line_b[iline])[
                0
            ]
            x0 = self.screen.get_width() / 2 - total_width / 2

            # Render active (sung) text
            if self.line_a[iline]:
                text_a = self.font.render(
                    self.line_a[iline] + " ", 0, self.active_color
                )
                rect_a = self.screen.blit(text_a, [x0, 80 + iline * 60])
                x0 += rect_a.width

            # Render base (unsung) text
            if self.line_b[iline]:
                text_b = self.font.render(self.line_b[iline], 0, self.base_color)
                self.screen.blit(text_b, [x0, 80 + iline * 60])

        pygame.display.flip()


def play(audio_path: str, lrc_path: str):
    """Play audio with synchronized lyrics"""
    words, num_lines = parse_word_lrc(lrc_path)

    if not words:
        print(f"No lyrics found in {lrc_path}")
        sys.exit(1)

    print(f"Loaded {len(words)} words in {num_lines} lines from {lrc_path}")
    print(f"First word: '{words[0].word}' at {words[0].time:.2f}s")
    print(f"Last word: '{words[-1].word}' at {words[-1].time:.2f}s")

    pygame.mixer.pre_init(frequency=44100, buffer=2048)
    pygame.mixer.init()

    display = KaraokeDisplay(words)

    pygame.mixer.music.load(audio_path)
    pygame.mixer.music.play()

    print(f"\nPlaying: {audio_path}")
    print("Press Ctrl+C or close window to stop\n")

    done = False
    while pygame.mixer.music.get_busy() and not done:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                done = True

        # Get current playback position
        pos_ms = pygame.mixer.music.get_pos()
        current_time = pos_ms / 1000.0

        display.update(current_time)
        display.render()

        time.sleep(0.03)  # ~30 FPS

    pygame.quit()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python kara2.py <audio_file> <lrc_file>")
        print(
            "Example: python kara2.py separated/htdemucs/rachida/no_vocals.wav rachida_words.lrc"
        )
        sys.exit(1)

    audio_file = sys.argv[1]
    lrc_file = sys.argv[2]

    play(audio_file, lrc_file)
