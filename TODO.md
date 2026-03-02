# Karaokeke Project TODO

## Milestone: Finalizing & Polish

### 1. UX "Gap" Fix (Finalizing State)
- [ ] Implement a "Finalizing..." state in `web/src/lib/KaraokePlayer.svelte` and the preparation UI.
- [ ] Show a pulsing animation when progress hits 100% but the task status is not yet `completed`.
- [ ] Provide clearer feedback that the server is wrapping up the MP3 encoding/process.

### 2. Cleanup & Retention Logic
- [ ] Add a background routine in `api-server.ts` to monitor the `/data/separated` directory.
- [ ] Implement a retention policy (e.g., delete files older than 24 hours) to prevent disk exhaustion.
- [ ] Ensure the 83GB SQLite database has priority on the mount.

### 3. Visual Feedback for Sync (Toasts & Cues)
- [ ] Add reactive "Toast" notifications in the `KaraokePlayer.svelte` for sync adjustments (e.g., `+0.5s`).
- [ ] **Discrete Cursor:** Implement a visual cue/cursor to signal the start of a song or the end of an instrumental break.
- [ ] Style toasts and cursors to be non-intrusive but clearly visible over the lyrics.

### 4. Persistence & Metadata
- [ ] **Offset Persistence:** Remember the last offset setting for a song. 
    - [ ] Phase 1: Store in browser `localStorage`.
    - [ ] Phase 2: Store server-side in `offset.txt` or `metadata.json` within the track folder.

## Milestone: Advanced Lyrics & AI

### 1. Word-Level Tracking (Whisper Integration)
- [ ] Scavenge word-level reparsing logic from `../Ultrastar/WhisperTimeSync`.
- [ ] **UI Toggle:** Add an optional "Get Word Tracking" button in the preparation/player UI.
- [ ] Implement a robust fallback system if word tracking is unavailable or fails.
- [ ] **LRC Enhancement:** Use Whisper alignment to enable support for `lrclib` lyrics that lack any timestamping (sentence or word level).

### 2. Audio "Pre-warm" & Stability
- [ ] Implement a retry/buffer check before switching the UI from "100%" to "Play".
- [ ] Ensure the `.mp3` file is fully flushed to disk and readable by the OS to prevent player stutters.
- [ ] Handle potential 404s during the micro-window between "process exit" and "file availability".
