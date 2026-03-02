<script lang="ts">
  import KaraokePlayer from "$lib/KaraokePlayer.svelte";
  import { onMount } from "svelte";

  let { data } = $props();
  let { track } = data;

  let lyrics = $state(track.synced_lyrics || "");
  let preparing = $state(false);
  let currentTask = $state<any>(null);
  let instrumentalUrl = $state("");
  let showPlayer = $state(false);
  let errorMsg = $state("");

  async function startKaraoke() {
    preparing = true;
    errorMsg = "";
    currentTask = { step: "Starting...", progress: 0 };

    try {
      const res = await fetch(`/api/prepare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          artist: track.artist_name,
          title: track.name,
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
              errorMsg = "Preparation failed: " + task.error;
              preparing = false;
            }
          } catch (e) {
            console.error("Polling error:", e);
          }
        }, 1000);
      } else {
        errorMsg = "Failed to start preparation";
        preparing = false;
      }
    } catch (e) {
      console.error(e);
      errorMsg = "An error occurred during preparation";
      preparing = false;
    }
  }

  onMount(() => {
    // Automatically start if we have lyrics
    if (lyrics) {
      startKaraoke();
    }
  });

  function goBack() {
    window.location.href = "/";
  }
</script>

<svelte:head>
  <title>{track.artist_name} - {track.name} | Karao</title>
</svelte:head>

<div class="container">
  {#if showPlayer}
    <button class="back" onclick={goBack}>← Home</button>
    <KaraokePlayer {lyrics} audioSrc={instrumentalUrl} />
  {:else}
    <button class="back" onclick={goBack}>← Home</button>
    
    <div class="selected">
      <h1>{track.artist_name} - {track.name}</h1>

      {#if errorMsg}
        <div class="error">{errorMsg}</div>
        <button onclick={startKaraoke}>Retry</button>
      {:else if preparing && currentTask}
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
      {:else if !lyrics}
        <p>No synced lyrics available for this track.</p>
      {:else}
        <p>Starting preparation...</p>
      {/if}

      {#if lyrics && !showPlayer}
        <div class="lyrics-preview">
          {lyrics.split("\n").slice(0, 15).join("\n")}...
        </div>
      {/if}
    </div>
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

  .back {
    background: none;
    border: 1px solid #444;
    color: #888;
    padding: 0.5rem 1rem;
    cursor: pointer;
    margin-bottom: 1rem;
  }

  .selected {
    background: #111;
    padding: 1.5rem;
    border-radius: 8px;
    margin-top: 1rem;
  }

  .error {
    color: #ff4444;
    margin-bottom: 1rem;
    padding: 1rem;
    background: #2a1111;
    border-radius: 4px;
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
    max-height: 300px;
    overflow: hidden;
  }

  .progress-container {
    width: 100%;
    background: #1a1a1a;
    padding: 1rem;
    border-radius: 4px;
    border: 1px solid #333;
    margin: 1rem 0;
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
