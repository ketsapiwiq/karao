#!/usr/bin/env python
"""
lrclib.py - Query synced lyrics from lrclib SQLite database

This module provides functionality to search and retrieve synced lyrics
from the lrclib database dump (SQLite format).

Database schema:
- tracks: id, name, artist_name, album_name, duration, last_lyrics_id
- lyrics: id, plain_lyrics, synced_lyrics, track_id, has_synced_lyrics

Synced lyrics format (LRC):
[mm:ss.xx]lyrics line
Example: [00:12.34]Hello world
"""

import sqlite3
import os
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class LyricLine:
    """A single lyric line with timestamp"""

    time_seconds: float
    text: str
    time_str: str  # Original [mm:ss.xx] format


@dataclass
class SyncedLyrics:
    """Parsed synced lyrics with timing information"""

    track_id: int
    track_name: str
    artist_name: str
    album_name: Optional[str]
    duration: Optional[float]
    lyrics: List[LyricLine]
    raw_lrc: str


class LrcLibDB:
    """Interface to the lrclib SQLite database"""

    def __init__(
        self, db_path: str = "/mnt/gloubinours2/lrclib-db-dump-20260122T091251Z.sqlite3"
    ):
        """
        Initialize the database connection.

        Args:
            db_path: Path to the lrclib SQLite database file
        """
        self.db_path = db_path
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database not found: {db_path}")
        self._conn = None

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a database connection"""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self):
        """Close the database connection"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def search_tracks(
        self, query: str, limit: int = 20, require_synced: bool = True
    ) -> List[dict]:
        """
        Search for tracks by name, artist, or album using FTS5 full-text search.

        Args:
            query: Search query (song name, artist, or both)
            limit: Maximum number of results
            require_synced: Only return tracks with synced lyrics

        Returns:
            List of matching tracks with metadata
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Use FTS5 for full-text search
        sql = """
            SELECT t.id, t.name, t.artist_name, t.album_name, t.duration,
                   l.has_synced_lyrics, l.has_plain_lyrics
            FROM tracks t
            JOIN tracks_fts fts ON t.id = fts.rowid
            LEFT JOIN lyrics l ON t.last_lyrics_id = l.id
            WHERE tracks_fts MATCH ?
        """

        if require_synced:
            sql += " AND l.has_synced_lyrics = 1"

        sql += " ORDER BY t.id LIMIT ?"

        # FTS5 query format - escape special characters and join terms
        search_terms = query.replace('"', '""')
        fts_query = f'"{search_terms}"'

        cursor.execute(sql, (fts_query, limit))
        results = []
        for row in cursor.fetchall():
            results.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "artist_name": row["artist_name"],
                    "album_name": row["album_name"],
                    "duration": row["duration"],
                    "has_synced_lyrics": bool(row["has_synced_lyrics"]),
                    "has_plain_lyrics": bool(row["has_plain_lyrics"]),
                }
            )

        return results

    def search_by_artist_and_title(
        self,
        artist: str,
        title: str,
        duration: Optional[float] = None,
        duration_tolerance: float = 5.0,
        require_synced: bool = True,
    ) -> Optional[SyncedLyrics]:
        """
        Search for a specific track by artist and title.

        Args:
            artist: Artist name
            title: Song title
            duration: Optional duration in seconds for better matching
            duration_tolerance: Tolerance for duration matching in seconds
            require_synced: Require synced lyrics (not just plain text)

        Returns:
            SyncedLyrics object if found, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Normalize search terms (lowercase)
        artist_lower = artist.lower().strip()
        title_lower = title.lower().strip()

        sql = """
            SELECT t.id, t.name, t.artist_name, t.album_name, t.duration,
                   l.synced_lyrics, l.plain_lyrics
            FROM tracks t
            LEFT JOIN lyrics l ON t.last_lyrics_id = l.id
            WHERE t.artist_name_lower = ? AND t.name_lower = ?
        """
        params = [artist_lower, title_lower]

        if duration is not None:
            sql += " AND ABS(t.duration - ?) <= ?"
            params.extend([duration, duration_tolerance])

        if require_synced:
            sql += " AND l.has_synced_lyrics = 1"

        sql += " LIMIT 1"

        cursor.execute(sql, params)
        row = cursor.fetchone()

        if row is None:
            return None

        lyrics = self._parse_lrc(row["synced_lyrics"]) if row["synced_lyrics"] else []

        return SyncedLyrics(
            track_id=row["id"],
            track_name=row["name"],
            artist_name=row["artist_name"],
            album_name=row["album_name"],
            duration=row["duration"],
            lyrics=lyrics,
            raw_lrc=row["synced_lyrics"] or "",
        )

    def get_by_id(self, track_id: int) -> Optional[SyncedLyrics]:
        """
        Get lyrics for a specific track by ID.

        Args:
            track_id: The track ID in the database

        Returns:
            SyncedLyrics object if found, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        sql = """
            SELECT t.id, t.name, t.artist_name, t.album_name, t.duration,
                   l.synced_lyrics, l.plain_lyrics
            FROM tracks t
            LEFT JOIN lyrics l ON t.last_lyrics_id = l.id
            WHERE t.id = ?
        """

        cursor.execute(sql, (track_id,))
        row = cursor.fetchone()

        if row is None:
            return None

        lyrics = self._parse_lrc(row["synced_lyrics"]) if row["synced_lyrics"] else []

        return SyncedLyrics(
            track_id=row["id"],
            track_name=row["name"],
            artist_name=row["artist_name"],
            album_name=row["album_name"],
            duration=row["duration"],
            lyrics=lyrics,
            raw_lrc=row["synced_lyrics"] or "",
        )

    @staticmethod
    def _parse_lrc(lrc_content: str) -> List[LyricLine]:
        """
        Parse LRC format lyrics into structured data.

        LRC format: [mm:ss.xx]lyrics text
        Example: [00:12.34]Hello world

        Args:
            lrc_content: Raw LRC format string

        Returns:
            List of LyricLine objects sorted by time
        """
        if not lrc_content:
            return []

        lyrics = []
        # Pattern matches [mm:ss.xx] or [mm:ss:xx] format
        pattern = r"\[(\d+):(\d+(?:[.:]\d+)?)\](.*)"

        for line in lrc_content.split("\n"):
            line = line.strip()
            match = re.match(pattern, line)
            if match:
                minutes = int(match.group(1))
                # Handle both mm:ss.xx and mm:ss:xx formats
                time_part = match.group(2)
                if ":" in time_part:
                    seconds_parts = time_part.split(":")
                    seconds = int(seconds_parts[0])
                    centiseconds = (
                        int(seconds_parts[1]) if len(seconds_parts) > 1 else 0
                    )
                elif "." in time_part:
                    seconds_parts = time_part.split(".")
                    seconds = int(seconds_parts[0])
                    centiseconds = int(seconds_parts[1].ljust(2, "0")[:2])
                else:
                    seconds = int(time_part)
                    centiseconds = 0

                time_seconds = minutes * 60 + seconds + centiseconds / 100.0
                text = match.group(3).strip()

                # Skip empty lines or metadata
                if text and not text.startswith("["):
                    lyrics.append(
                        LyricLine(
                            time_seconds=time_seconds,
                            text=text,
                            time_str=f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]",
                        )
                    )

        return sorted(lyrics, key=lambda x: x.time_seconds)

    def lrc_to_kar_format(self, synced_lyrics: SyncedLyrics, output_path: str) -> str:
        """
        Convert synced lyrics to a simple karaoke format compatible with midifile.py.

        Note: This creates a basic MIDI file with lyrics but without pitch information.
        For full karaoke with pitch, use swiftf0.py to generate a proper .kar file.

        Args:
            synced_lyrics: SyncedLyrics object from search
            output_path: Path to save the output file

        Returns:
            Path to the created file
        """
        # This is a placeholder - actual MIDI/KAR creation needs swiftf0.py
        # Here we just save the LRC format which can be used by other tools
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(synced_lyrics.raw_lrc)
        return output_path


def search_lyrics(
    query: str,
    db_path: str = "/mnt/gloubinours2/lrclib-db-dump-20260122T091251Z.sqlite3",
    limit: int = 10,
) -> List[dict]:
    """
    Convenience function to search for lyrics.

    Args:
        query: Search query
        db_path: Path to the database
        limit: Maximum results

    Returns:
        List of matching tracks
    """
    with LrcLibDB(db_path) as db:
        return db.search_tracks(query, limit)


def get_synced_lyrics(
    artist: str,
    title: str,
    duration: Optional[float] = None,
    db_path: str = "/mnt/gloubinours2/lrclib-db-dump-20260122T091251Z.sqlite3",
) -> Optional[SyncedLyrics]:
    """
    Convenience function to get synced lyrics for a specific song.

    Args:
        artist: Artist name
        title: Song title
        duration: Optional duration for better matching
        db_path: Path to the database

    Returns:
        SyncedLyrics if found, None otherwise
    """
    with LrcLibDB(db_path) as db:
        return db.search_by_artist_and_title(artist, title, duration)


if __name__ == "__main__":
    # Example usage
    import sys

    if len(sys.argv) < 2:
        print("Usage: python lrclib.py <search query>")
        print("       python lrclib.py <artist> - <title>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    print(f"Searching for: {query}")
    print("-" * 50)

    results = search_lyrics(query, limit=5)

    if not results:
        print("No results found.")
        sys.exit(0)

    for i, track in enumerate(results, 1):
        print(f"{i}. {track['artist_name']} - {track['name']}")
        print(f"   Album: {track['album_name'] or 'Unknown'}")
        print(
            f"   Duration: {track['duration']:.2f}s"
            if track["duration"]
            else "   Duration: Unknown"
        )
        print(f"   Synced: {'Yes' if track['has_synced_lyrics'] else 'No'}")
        print()
