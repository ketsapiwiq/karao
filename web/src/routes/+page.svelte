<script lang="ts">
  import { goto } from "$app/navigation";

  let query = $state("");
  let results = $state<any[]>([]);
  let loading = $state(false);

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

  function selectTrack(track: any) {
    goto(`/song/${track.id}/${encodeURIComponent(track.name)}`);
  }

  function formatDuration(seconds: number | null): string {
    if (!seconds) return "--:--";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }
</script>

<svelte:head>
  <title>Karao</title>
</svelte:head>

<div class="container">
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
        >
          <span class="artist">{track.artist_name}</span>
          <span class="title">{track.name}</span>
          <span class="duration">{formatDuration(track.duration)}</span>
          <a href="/song/{track.id}/{encodeURIComponent(track.name)}" class="permalink" onclick={(e) => e.stopPropagation()}>🔗</a>
        </li>
      {/each}
    </ul>
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
    align-items: center;
  }

  .results li:hover {
    background: #111;
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
</style>
