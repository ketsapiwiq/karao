import asyncio
import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

DB_PATH = os.environ.get("LRCLIB_DB", "/lrclib.sqlite3")
DATA_DIR = os.environ.get("DATA_DIR", "/data")
PORT = int(os.environ.get("PORT", "3001"))

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
db.row_factory = sqlite3.Row
print("Database connected")

tasks: dict = {}
_start_time = time.time()


# ── DB helpers ────────────────────────────────────────────────────────────────

def _search_lyrics(q: str, page: int, limit: int) -> list:
    t0 = time.perf_counter()
    terms = ['"' + t.replace('"', '""') + '"' for t in q.split() if t]
    fts_query = " ".join(terms)
    offset = (page - 1) * limit
    sql = """
        SELECT t.id, t.name, t.artist_name, t.album_name, t.duration,
               l.has_synced_lyrics, l.has_plain_lyrics
        FROM tracks_fts fts
        CROSS JOIN tracks t ON fts.rowid = t.id
        CROSS JOIN lyrics l ON t.last_lyrics_id = l.id
        WHERE tracks_fts MATCH ?
          AND l.has_synced_lyrics = 1
          AND l.synced_lyrics IS NOT NULL
          AND l.synced_lyrics != ''
        LIMIT ? OFFSET ?
    """
    rows = [dict(r) for r in db.execute(sql, (fts_query, limit, offset)).fetchall()]
    elapsed = (time.perf_counter() - t0) * 1000
    print(f'Search for "{q}" (page {page}) took {elapsed:.2f}ms, found {len(rows)} results')
    return rows


def _get_lyrics(track_id: int) -> Optional[dict]:
    sql = """
        SELECT t.id, t.name, t.artist_name, t.album_name, t.duration,
               l.synced_lyrics, l.plain_lyrics
        FROM tracks t
        LEFT JOIN lyrics l ON t.last_lyrics_id = l.id
        WHERE t.id = ?
    """
    row = db.execute(sql, (track_id,)).fetchone()
    return dict(row) if row else None


# ── yt-dlp ────────────────────────────────────────────────────────────────────

async def _run_yt_dlp(
    query_or_url: str, output_dir: str, slug: str, task_id: str, provider: str = "ytsearch"
) -> dict:
    if not isinstance(query_or_url, str):
        query_or_url = str(query_or_url)

    if query_or_url.startswith("http"):
        target = query_or_url
    elif provider.startswith("http"):
        from urllib.parse import quote
        target = f"{provider}{quote(query_or_url)}"
    else:
        target = f"{provider}1:{query_or_url}"

    audio_path = os.path.join(output_dir, f"{slug}.mp3")
    args = [
        "python3", "-m", "yt_dlp",
        "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--postprocessor-args", "ffmpeg:-movflags +faststart",
        "--no-playlist",
        "--newline",
        "-o", os.path.join(output_dir, f"{slug}.%(ext)s"),
        "--exec", f'ffmpeg -y -i {{}} -vn -acodec libmp3lame -q:a 0 "{audio_path}"',
        target,
    ]

    print(f"[yt-dlp] Starting with target: {target!r}")
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stderr_lines: list[str] = []

    async def _drain_stdout():
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").strip()
            if "[download]" in line:
                m = re.search(r"(\d+\.\d+)%", line)
                if m and task_id in tasks:
                    tasks[task_id] = {**tasks[task_id], "status": "processing", "step": "Downloading", "progress": float(m.group(1))}

    async def _drain_stderr():
        async for raw in proc.stderr:
            text = raw.decode(errors="replace")
            stderr_lines.append(text)
            print(f"[yt-dlp] stderr: {text}", end="")

    await asyncio.gather(_drain_stdout(), _drain_stderr())
    code = await proc.wait()
    print(f"[yt-dlp] exited with code {code} for target: {target}")

    video_path = os.path.join(output_dir, f"{slug}.mp4")
    if code != 0:
        return {"success": False, "details": "".join(stderr_lines)}
    if os.path.exists(audio_path):
        return {"success": True, "path": audio_path, "videoPath": video_path if os.path.exists(video_path) else None}
    return {"success": False, "details": "Audio file not found after successful download."}


# ── Download ──────────────────────────────────────────────────────────────────

async def _handle_download(
    artist: str, title: str, task_id: Optional[str] = None, custom_url: Optional[str] = None
) -> dict:
    slug = task_id or re.sub(r"[^a-zA-Z0-9 \-]", "", f"{artist} - {title}")
    actual_task_id = task_id or slug
    output_dir = os.path.join(DATA_DIR, "audio", slug)
    final_path = os.path.join(output_dir, f"{slug}.mp3")
    video_path = os.path.join(output_dir, f"{slug}.mp4")

    os.makedirs(output_dir, exist_ok=True)

    if os.path.exists(final_path):
        if task_id:
            tasks[task_id] = {**tasks.get(task_id, {}), "status": "processing", "step": "Download (Cached)", "progress": 100}
        return {"status": "cached", "path": final_path, "videoPath": video_path if os.path.exists(video_path) else None}

    if custom_url:
        if task_id:
            tasks[task_id] = {**tasks.get(task_id, {}), "status": "processing", "step": "Downloading custom URL...", "progress": 0, "stepSource": "Manual URL"}
        attempt = await _run_yt_dlp(custom_url, output_dir, slug, actual_task_id)
        if attempt["success"] and attempt.get("path"):
            return {"status": "downloaded", "path": attempt["path"], "videoPath": attempt.get("videoPath")}
        return {"error": "Custom URL download failed", "details": attempt.get("details")}

    quoted = f'"{artist}" "{title}"'
    normal = f"{artist} {title}"

    print(f'[api] Attempt 1: Searching YouTube for "{quoted}"')
    if task_id:
        tasks[task_id] = {"status": "processing", "step": "Searching YouTube (Precise)...", "progress": 0, "stepSource": "YouTube"}
    a1 = await _run_yt_dlp(quoted, output_dir, slug, actual_task_id, "ytsearch")
    if a1["success"] and a1.get("path"):
        return {"status": "downloaded", "path": a1["path"]}

    print(f'[api] Attempt 1 failed. Attempt 2: Searching YouTube for "{normal}"')
    if task_id:
        tasks[task_id] = {"status": "processing", "step": "Searching YouTube...", "progress": 0, "stepSource": "YouTube"}
    a2 = await _run_yt_dlp(normal, output_dir, slug, actual_task_id, "ytsearch")
    if a2["success"] and a2.get("path"):
        return {"status": "downloaded", "path": a2["path"]}

    return {"error": "Download failed", "details": a2.get("details") or a1.get("details")}


# ── Demucs worker ─────────────────────────────────────────────────────────────

async def _ensure_worker_running() -> bool:
    socket_path = "/tmp/demucs_worker.sock"
    if os.path.exists(socket_path):
        return True

    print("[api] Starting demucs worker...")
    subprocess.Popen(["python3", "demucs_worker.py"])

    for _ in range(30):
        if os.path.exists(socket_path):
            return True
        await asyncio.sleep(1)
    return False


async def _handle_separate(audio_path: str, task_id: Optional[str] = None) -> dict:
    basename = task_id or Path(audio_path).stem
    actual_task_id = task_id or basename
    instrumental_path = os.path.join(DATA_DIR, "separated", "htdemucs", basename, "no_vocals.mp3")
    url = f"/api/audio/separated/htdemucs/{basename}/no_vocals.mp3"

    if os.path.exists(instrumental_path):
        if task_id:
            tasks[task_id] = {**tasks.get(task_id, {}), "status": "processing", "step": "Separation (Cached)", "progress": 100}
        return {"status": "cached", "instrumentalPath": instrumental_path, "url": url}

    if task_id:
        tasks[task_id] = {**tasks.get(task_id, {}), "status": "processing", "step": "Separating (Demucs)", "progress": 0}

    if not await _ensure_worker_running():
        return {"error": "Failed to start demucs worker"}

    try:
        reader, writer = await asyncio.open_unix_connection("/tmp/demucs_worker.sock")
    except Exception as e:
        return {"error": "Worker communication error", "details": str(e)}

    writer.write(json.dumps({
        "command": "separate",
        "inputPath": audio_path,
        "outputDir": DATA_DIR,
        "taskId": actual_task_id,
    }).encode())
    await writer.drain()

    result = None
    buf = ""
    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            buf += data.decode(errors="replace")
            lines = buf.split("\n")
            buf = lines.pop()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("type") == "progress":
                        tasks[actual_task_id] = {
                            **tasks.get(actual_task_id, {}),
                            "status": "processing",
                            "step": msg["step"],
                            "progress": msg["progress"],
                        }
                    elif "success" in msg:
                        result = msg
                        break
                except Exception as e:
                    print(f"[api] Failed to parse worker message: {line!r} {e}")
    except Exception as e:
        writer.close()
        return {"error": "Worker communication error", "details": str(e)}

    writer.close()

    if result is None:
        return {"error": "Worker connection closed unexpectedly"}
    if result["success"]:
        return {"status": "separated", "instrumentalPath": instrumental_path, "url": url}
    return {"error": "Separation failed", "details": result.get("error")}


# ── Background prepare ────────────────────────────────────────────────────────

async def _run_prepare_task(
    task_id: str, artist: str, title: str, custom_url: Optional[str], only_download: bool
):
    try:
        print(f"Background task {task_id} started{' with custom URL' if custom_url else ''}")
        dl = await _handle_download(artist, title, task_id, custom_url)
        if dl.get("error"):
            raise RuntimeError(dl["error"])

        original_url = f"/api/audio/audio/{task_id}/{task_id}.mp3"
        video_url = f"/api/audio/audio/{task_id}/{task_id}.mp4" if dl.get("videoPath") else None
        tasks[task_id] = {**tasks[task_id], "originalUrl": original_url, "videoUrl": video_url}

        if only_download:
            print(f"Download for {task_id} finished, skipping separation as requested.")
            tasks[task_id] = {
                "status": "completed", "step": "Finished", "progress": 100,
                "resultUrl": original_url, "originalUrl": original_url, "videoUrl": video_url,
            }
            return

        print(f"Download for {task_id} finished, starting separation: {dl['path']}")
        sep = await _handle_separate(dl["path"], task_id)
        if sep.get("error"):
            raise RuntimeError(sep["error"])

        print(f"Separation for {task_id} finished")
        tasks[task_id] = {
            "status": "completed", "step": "Finished", "progress": 100,
            "resultUrl": sep["url"], "originalUrl": original_url, "videoUrl": video_url,
        }
    except Exception as e:
        print(f"Task {task_id} failed: {e}")
        tasks[task_id] = {"status": "failed", "step": "Error", "progress": 0, "error": str(e)}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "uptime": time.time() - _start_time}


@app.get("/api/search-lyrics")
async def search_lyrics_route(q: str, page: int = 1, limit: int = 50):
    print(f"Searching for: {q} (page: {page}, limit: {limit})")
    return {"results": _search_lyrics(q, page, limit)}


@app.get("/api/lyrics")
async def get_lyrics_route(id: int):
    row = _get_lyrics(id)
    if not row:
        raise HTTPException(status_code=404, detail="Track not found")
    return row


class PrepareBody(BaseModel):
    artist: str
    title: str
    youtubeUrl: Optional[str] = None
    force: bool = False
    onlyDownload: bool = False


@app.post("/api/prepare")
async def prepare_route(body: PrepareBody):
    slug = re.sub(r"[^a-zA-Z0-9 \-]", "", f"{body.artist} - {body.title}")
    task_id = slug

    if body.youtubeUrl or body.force:
        print(f"Forcing re-preparation for {task_id}{f' with custom URL: {body.youtubeUrl}' if body.youtubeUrl else ''}")
        tasks.pop(task_id, None)
        import shutil
        for d in [
            os.path.join(DATA_DIR, "audio", slug),
            os.path.join(DATA_DIR, "separated", "htdemucs", slug),
        ]:
            if os.path.exists(d):
                try:
                    shutil.rmtree(d)
                except Exception as e:
                    print(f"Cleanup failed for {task_id}: {e}")

    if task_id in tasks and tasks[task_id].get("status") != "failed":
        return {"taskId": task_id}

    tasks[task_id] = {"status": "pending", "step": "Initializing", "progress": 0}
    asyncio.create_task(_run_prepare_task(task_id, body.artist, body.title, body.youtubeUrl, body.onlyDownload))
    return {"taskId": task_id}


@app.get("/api/tasks/{task_id:path}")
async def get_task(task_id: str):
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


class DownloadBody(BaseModel):
    artist: str
    title: str


@app.post("/api/download")
async def download_route(body: DownloadBody):
    return await _handle_download(body.artist, body.title)


class SeparateBody(BaseModel):
    audioPath: str


@app.post("/api/separate")
async def separate_route(body: SeparateBody):
    return await _handle_separate(body.audioPath)


@app.get("/api/audio/{file_path:path}")
async def audio_route(file_path: str, request: Request):
    full_path = os.path.join(DATA_DIR, file_path)
    print(f'Serving audio from: "{full_path}"')

    if not os.path.isfile(full_path):
        print(f'Audio file not found: "{full_path}"')
        raise HTTPException(status_code=404, detail="Not found")

    file_size = os.path.getsize(full_path)
    content_type = "audio/wav" if full_path.endswith(".wav") else "audio/mpeg"

    range_header = request.headers.get("range")
    if range_header:
        parts = range_header.replace("bytes=", "").split("-")
        start = int(parts[0])
        end = int(parts[1]) if parts[1] else file_size - 1
        chunk_size = end - start + 1

        def _iter_range():
            with open(full_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            _iter_range(),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
            },
        )

    def _iter_full():
        with open(full_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        _iter_full(),
        media_type=content_type,
        headers={"Content-Length": str(file_size)},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
