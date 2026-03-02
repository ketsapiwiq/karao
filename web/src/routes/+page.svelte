<script lang="ts">
  import { goto } from "$app/navigation";

  let query = $state("");
  let results = $state<any[]>([]);
  let loading = $state(false);
  let page = $state(1);
  let hasMore = $state(false);
  let hasSearched = $state(false);

  async function search(reset = true) {
    if (!query.trim()) return;
    loading = true;
    if (reset) {
      results = [];
      page = 1;
      hasSearched = true;
    }
    try {
      const res = await fetch(
        `/api/search-lyrics?q=${encodeURIComponent(query)}&page=${page}&limit=50`,
      );
      const data = await res.json();
      const newResults = data.results || [];
      if (reset) {
        results = newResults;
      } else {
        results = [...results, ...newResults];
      }
      hasMore = newResults.length === 50;
    } catch (e) {
      console.error(e);
    }
    loading = false;
  }

  function loadMore() {
    page += 1;
    search(false);
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
    {#if hasMore}
      <div class="pagination">
        <button onclick={loadMore} disabled={loading}>
          {loading ? "Loading more..." : "Load more results"}
        </button>
      </div>
    {/if}
  {:else if hasSearched && !loading}
    <div class="no-results">
      <p>No synced lyrics found for "{query}".</p>
      <p class="small">Try different keywords or check the spelling.</p>
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

  h1 {
    text-align: center;
    font-size: 2.5rem;
    margin-bottom: 2rem;
  }

  .search {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 2rem;
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
    transition: background 0.2s;
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
    padding: 1rem;
    cursor: pointer;
    border-bottom: 1px solid #1a1a1a;
    display: flex;
    gap: 1rem;
    align-items: center;
    transition: background 0.2s;
  }

  .results li:hover {
    background: #111;
  }

  .artist {
    color: #888;
    width: 200px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .title {
    font-weight: 500;
    flex: 1;
  }
  .duration {
    color: #555;
    font-variant-numeric: tabular-nums;
  }

  .permalink {
    text-decoration: none;
    font-size: 0.8rem;
    padding: 0 0.5rem;
    color: #333;
    transition: color 0.2s;
  }

  .permalink:hover {
    color: #666;
  }

  .no-results {
    text-align: center;
    padding: 4rem 2rem;
    color: #666;
  }

  .no-results p {
    margin: 0.5rem 0;
  }

  .no-results .small {
    font-size: 0.9rem;
    opacity: 0.7;
  }

  .pagination {
    display: flex;
    justify-content: center;
    padding: 2rem 0;
  }
</style>
