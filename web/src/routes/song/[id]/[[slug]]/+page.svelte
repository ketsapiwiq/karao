<script lang="ts">
  import KaraokePlayer from "$lib/KaraokePlayer.svelte";
  import { onMount } from "svelte";

  let { data } = $props();
  let track = $derived(data.track);

  let lyrics = $state("");
  $effect(() => {
    lyrics = track.synced_lyrics || "";
  });
  let preparing = $state(false);
  let currentTask = $state<any>(null);
  let instrumentalUrl = $state("");
  let videoUrl = $state("");
  let showPlayer = $state(false);
  let errorMsg = $state("");
  let showMenu = $state(false);
  let enableVideo = $state(true);
let showAllLyrics = $state(false);

  onMount(() => {
    const savedVideoPref = localStorage.getItem("enableVideo");
    if (savedVideoPref !== null) {
      enableVideo = savedVideoPref === "true";
    }
  });

  function toggleVideo() {
    enableVideo = !enableVideo;
    localStorage.setItem("enableVideo", enableVideo.toString());
  }

  async function startKaraoke(customUrl?: string, force = false, onlyDownload = false) {
    preparing = true;
    errorMsg = "";
    showMenu = false;
    currentTask = { step: "Starting...", progress: 0 };

    try {
      const res = await fetch(`/api/prepare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          artist: track.artist_name,
          title: track.name,
          youtubeUrl: customUrl,
          force,
          onlyDownload,
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
              instrumentalUrl = (onlyDownload && task.originalUrl) ? task.originalUrl : task.resultUrl;
              videoUrl = task.videoUrl || "";
              showPlayer = true;
              preparing = false;
            } else if (task.status === "failed") {
              clearInterval(poll);
              errorMsg = "Preparation failed: " + task.error;
              preparing = false;
            } else if (onlyDownload && task.originalUrl) {
              // If we only want original and it's already downloaded, we can start
              clearInterval(poll);
              instrumentalUrl = task.originalUrl;
              videoUrl = task.videoUrl || "";
              showPlayer = true;
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

  function promptCustomUrl() {
    const url = prompt("Enter a direct YouTube URL to use for this track:");
    if (url && url.startsWith("http")) {
      startKaraoke(url);
    }
  }
</script>

<svelte:head>
  <title>{track.artist_name} - {track.name} | Karao</title>
</svelte:head>

<div class="container">
  <div class="header-row">
    <button class="back" onclick={goBack}>← Home</button>
    <div class="menu-container">
      <button class="menu-trigger" onclick={() => showMenu = !showMenu}>⋮</button>
              {#if showMenu}
                <div class="menu-dropdown">
                  <button onclick={promptCustomUrl}>Custom YouTube URL</button>
                  <button onclick={() => startKaraoke(undefined, false, true)}>Use Original Audio</button>
                  <button onclick={() => startKaraoke(undefined, true)}>Force Redownload</button>
                  <hr style="border: 0; border-top: 1px solid #333; margin: 0.5rem 0;" />
<button onclick={() => { showAllLyrics = !showAllLyrics; showMenu = false; }}>
  {showAllLyrics ? 'Hide' : 'Show'} All Lyrics
</button>
<button onclick={toggleVideo}>
  {enableVideo ? 'Disable' : 'Enable'} Video Background
</button>
                </div>
              {/if}    </div>
  </div>

  {#if showPlayer}
<KaraokePlayer
  {lyrics}
  audioSrc={instrumentalUrl}
  videoSrc={videoUrl}
  enableVideo={enableVideo}
  trackName={track.artist_name + " - " + track.name}
  bind:showAllLyrics
/>
  {:else}
    <div class="selected">
      <h1>{track.artist_name} - {track.name}</h1>

      {#if errorMsg}
        <div class="error">{errorMsg}</div>
        <button onclick={startKaraoke}>Retry</button>
      {:else if preparing && currentTask}
        <div class="progress-container">
          <div class="progress-header">
            <span>
              {currentTask.progress >= 100 && currentTask.status !== "completed" ? "Finalizing..." : currentTask.step}
              {#if currentTask.stepSource}
                <span class="source-hint">({currentTask.stepSource})</span>
              {/if}
            </span>
            <span>{Math.round(currentTask.progress)}%</span>
          </div>
          <div class="progress-bar">
            <div
              class="progress-fill"
              class:finalizing={currentTask.progress >= 100 && currentTask.status !== "completed"}
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
    padding: 6rem 2rem 2rem 2rem;
    position: relative;
  }

  .header-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1rem;
    position: absolute;
    top: 2rem;
    left: 2rem;
    right: 2rem;
    z-index: 20;
  }

  .back {
    background: #1a1a1a;
    border: 1px solid #444;
    color: #eee;
    padding: 0.5rem 1rem;
    cursor: pointer;
    border-radius: 4px;
    transition: background 0.2s;
  }

  .back:hover {
    background: #2a2a2a;
  }

  .menu-container {
    position: relative;
  }

  .menu-trigger {
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 4px;
    color: #eee;
    font-size: 1.2rem;
    cursor: pointer;
    padding: 0.2rem 0.8rem;
    transition: background 0.2s;
  }

  .menu-trigger:hover {
    background: #2a2a2a;
  }

  .menu-dropdown {
    position: absolute;
    top: 100%;
    right: 0;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 4px;
    padding: 0.5rem 0;
    z-index: 10;
    width: 180px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.5);
  }

  .menu-dropdown button {
    display: block;
    width: 100%;
    padding: 0.5rem 1rem;
    text-align: left;
    background: none;
    border: none;
    color: #eee;
    cursor: pointer;
    font-size: 0.9rem;
  }

  .menu-dropdown button:hover {
    background: #2a2a2a;
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

  .source-hint {
    font-size: 0.75rem;
    color: #555;
    margin-left: 0.5rem;
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

  .progress-fill.finalizing {
    background: #a5a9ff;
    animation: pulse 1.5s infinite ease-in-out;
  }

  @keyframes pulse {
    0% { opacity: 0.6; }
    50% { opacity: 1; }
    100% { opacity: 0.6; }
  }
</style>
