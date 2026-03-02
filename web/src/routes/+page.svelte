<script lang="ts">
  import KaraokePlayer from "$lib/KaraokePlayer.svelte";
  import { browser } from "$app/environment";

  let query = "";
  let results: any[] = [];
  let loading = false;
  let selectedTrack: any = null;
  let lyrics = "";
  let preparing = false;
  let currentTask: any = null;
  let instrumentalUrl = "";
  let showPlayer = false;

  async function search() {
    if (!query.trim()) return;
    loading = true;
    results = [];
    try {
      const res = await fetch(
        `/api/search-lyrics?q=${encodeURIComponent(query)}`,
      );
      const data = await res.json();
      results = data.results || [];
    } catch (e) {
      console.error(e);
    }
    loading = false;
  }

  async function selectTrack(track: any) {
    selectedTrack = track;
    try {
      const res = await fetch(`/api/lyrics?id=${track.id}`);
      const data = await res.json();
      lyrics = data.synced_lyrics || "";
    } catch (e) {
      console.error(e);
    }
  }

  async function startKaraoke() {
    if (!selectedTrack) return;
    preparing = true;
    currentTask = { step: "Starting...", progress: 0 };

    try {
      const res = await fetch(`/api/prepare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          artist: selectedTrack.artist_name,
          title: selectedTrack.name,
        }),
      });
      const { taskId } = await res.json();

      if (taskId) {
        const poll = setInterval(async () => {
          try {
            const taskRes = await fetch(`/api/tasks/${taskId}`);
            const task = await taskRes.json();
            currentTask = task;

            if (task.status === "completed") {
              clearInterval(poll);
              instrumentalUrl = task.resultUrl;
              showPlayer = true;
              preparing = false;
            } else if (task.status === "failed") {
              clearInterval(poll);
              alert("Preparation failed: " + task.error);
              preparing = false;
            }
          } catch (e) {
            console.error("Polling error:", e);
          }
        }, 1000);
      } else {
        alert("Failed to start preparation");
        preparing = false;
      }
    } catch (e) {
      console.error(e);
      preparing = false;
    }
  }

  function formatDuration(seconds: number | null): string {
    if (!seconds) return "--:--";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }

  function goBack() {
    showPlayer = false;
    instrumentalUrl = "";
  }
</script>

<svelte:head>
  <title>Karao</title>
</svelte:head>

<div class="container">
  {#if showPlayer}
    <button class="back" onclick={goBack}>← Back</button>
    <KaraokePlayer {lyrics} audioSrc={instrumentalUrl} />
  {:else}
    <h1>Karao</h1>

    <div class="search">
      <input
        type="text"
        bind:value={query}
        placeholder="Search for a song..."
        onkeydown={(e) => e.key === "Enter" && search()}
      />
      <button onclick={search} disabled={loading}>
        {loading ? "..." : "Search"}
      </button>
    </div>

    {#if results.length > 0}
      <ul class="results">
        {#each results as track}
          <li
            onclick={() => selectTrack(track)}
            onkeydown={(e) => e.key === "Enter" && selectTrack(track)}
            role="button"
            tabindex="0"
            class:selected={selectedTrack?.id === track.id}
          >
            <span class="artist">{track.artist_name}</span>
            <span class="title">{track.name}</span>
            <span class="duration">{formatDuration(track.duration)}</span>
            <a href="/song/{track.id}/{encodeURIComponent(track.name)}" class="permalink" onclick={(e) => e.stopPropagation()}>🔗</a>
          </li>
        {/each}
      </ul>
    {/if}

    {#if selectedTrack}
      <div class="selected">
        <h2>{selectedTrack.artist_name} - {selectedTrack.name}</h2>

        {#if lyrics}
          <div class="lyrics-preview">
            {lyrics.split("\n").slice(0, 10).join("\n")}...
          </div>

          <div class="actions">
            {#if preparing && currentTask}
              <div class="progress-container">
                <div class="progress-header">
                  <span>{currentTask.step}</span>
                  <span>{Math.round(currentTask.progress)}%</span>
                </div>
                <div class="progress-bar">
                  <div
                    class="progress-fill"
                    style="width: {currentTask.progress}%"
                  ></div>
                </div>
              </div>
            {:else}
              <button onclick={startKaraoke} disabled={preparing}>
                Start Karaoke
              </button>
            {/if}
          </div>
        {:else}
          <p>No synced lyrics available</p>
        {/if}
      </div>
    {/if}
  {/if}
</div>

<style>
  :global(body) {
    background: #0a0a0a;
    color: #eee;
    font-family: system-ui, sans-serif;
    margin: 0;
  }

  .container {
    max-width: 800px;
    margin: 0 auto;
    padding: 2rem;
  }

  h1 {
    text-align: center;
    font-size: 2.5rem;
    margin-bottom: 2rem;
  }

  .back {
    background: none;
    border: 1px solid #444;
    color: #888;
    padding: 0.5rem 1rem;
    cursor: pointer;
    margin-bottom: 1rem;
  }

  .search {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  input {
    flex: 1;
    padding: 0.75rem;
    font-size: 1rem;
    background: #111;
    border: 1px solid #333;
    color: #eee;
    border-radius: 4px;
  }

  input:focus {
    outline: none;
    border-color: #666;
  }

  button {
    padding: 0.75rem 1.5rem;
    font-size: 1rem;
    cursor: pointer;
    background: #222;
    border: 1px solid #444;
    color: #eee;
    border-radius: 4px;
  }

  button:hover:not(:disabled) {
    background: #333;
  }
  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .results {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .results li {
    padding: 0.75rem;
    cursor: pointer;
    border-bottom: 1px solid #222;
    display: flex;
    gap: 0.5rem;
  }

  .results li:hover {
    background: #111;
  }
  .results li.selected {
    background: #1a1a2e;
    border-left: 3px solid #646cff;
  }

  .artist {
    color: #888;
  }
  .title {
    font-weight: bold;
  }
  .duration {
    margin-left: auto;
    color: #555;
  }

  .permalink {
    text-decoration: none;
    font-size: 0.8rem;
    padding: 0 0.5rem;
    color: #444;
    transition: color 0.2s;
  }

  .permalink:hover {
    color: #888;
  }

  .selected {
    background: #111;
    padding: 1.5rem;
    border-radius: 8px;
    margin-top: 1rem;
  }

  .selected h2 {
    margin-top: 0;
  }

  .lyrics-preview {
    background: #0a0a0a;
    padding: 1rem;
    font-family: monospace;
    white-space: pre-wrap;
    margin: 1rem 0;
    font-size: 0.9rem;
    color: #888;
    border-radius: 4px;
    max-height: 200px;
    overflow: hidden;
  }

  .actions {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    width: 100%;
  }

  .progress-container {
    width: 100%;
    background: #1a1a1a;
    padding: 1rem;
    border-radius: 4px;
    border: 1px solid #333;
  }

  .progress-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.5rem;
    font-size: 0.9rem;
    color: #aaa;
  }

  .progress-bar {
    width: 100%;
    height: 8px;
    background: #333;
    border-radius: 4px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: #646cff;
    transition: width 0.3s ease;
  }
</style>

