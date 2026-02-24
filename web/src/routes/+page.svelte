<script lang="ts">
	import KaraokePlayer from '$lib/KaraokePlayer.svelte';
	import { browser } from '$app/environment';

	const API_URL = 'http://localhost:3017';

	let query = '';
	let results: any[] = [];
	let loading = false;
	let selectedTrack: any = null;
	let lyrics = '';
	let downloading = false;
	let separating = false;
	let audioPath = '';
	let instrumentalUrl = '';
	let showPlayer = false;

	async function search() {
		if (!query.trim()) return;
		loading = true;
		results = [];
		try {
			const res = await fetch(`${API_URL}/search?q=${encodeURIComponent(query)}`);
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
			const res = await fetch(`${API_URL}/lyrics/${track.id}`);
			const data = await res.json();
			lyrics = data.synced_lyrics || '';
		} catch (e) {
			console.error(e);
		}
	}

	async function download() {
		if (!selectedTrack) return;
		downloading = true;
		try {
			const res = await fetch(`${API_URL}/download`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ artist: selectedTrack.artist_name, title: selectedTrack.name })
			});
			const data = await res.json();
			audioPath = data.path;
		} catch (e) {
			console.error(e);
		}
		downloading = false;
	}

	async function separate() {
		if (!audioPath) return;
		separating = true;
		try {
			const res = await fetch(`${API_URL}/separate`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ audioPath })
			});
			const data = await res.json();
			instrumentalUrl = `${API_URL}${data.url}`;
			showPlayer = true;
		} catch (e) {
			console.error(e);
		}
		separating = false;
	}

	function formatDuration(seconds: number | null): string {
		if (!seconds) return '--:--';
		const mins = Math.floor(seconds / 60);
		const secs = Math.floor(seconds % 60);
		return `${mins}:${secs.toString().padStart(2, '0')}`;
	}

	function goBack() {
		showPlayer = false;
		instrumentalUrl = '';
	}
</script>

<svelte:head>
	<title>Karaokeke</title>
</svelte:head>

<div class="container">
	{#if showPlayer}
		<button class="back" onclick={goBack}>← Back</button>
		<KaraokePlayer {lyrics} audioSrc={instrumentalUrl} />
	{:else}
		<h1>Karaokeke</h1>

		<div class="search">
			<input 
				type="text" 
				bind:value={query} 
				placeholder="Search for a song..."
				onkeydown={(e) => e.key === 'Enter' && search()}
			/>
			<button onclick={search} disabled={loading}>
				{loading ? '...' : 'Search'}
			</button>
		</div>

		{#if results.length > 0}
			<ul class="results">
				{#each results as track}
					<li 
						onclick={() => selectTrack(track)} 
						onkeydown={(e) => e.key === 'Enter' && selectTrack(track)}
						role="button"
						tabindex="0"
						class:selected={selectedTrack?.id === track.id}
					>
						<span class="artist">{track.artist_name}</span>
						<span class="title">{track.name}</span>
						<span class="duration">{formatDuration(track.duration)}</span>
					</li>
				{/each}
			</ul>
		{/if}

		{#if selectedTrack}
			<div class="selected">
				<h2>{selectedTrack.artist_name} - {selectedTrack.name}</h2>
				
				{#if lyrics}
					<div class="lyrics-preview">
						{lyrics.split('\n').slice(0, 10).join('\n')}...
					</div>
					
					<div class="actions">
						<button onclick={download} disabled={downloading}>
							{downloading ? '...' : 'Download MP3'}
						</button>
						
						{#if audioPath}
							<button onclick={separate} disabled={separating}>
								{separating ? '...' : 'Create Instrumental'}
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
	
	.container { max-width: 800px; margin: 0 auto; padding: 2rem; }
	
	h1 { text-align: center; font-size: 2.5rem; margin-bottom: 2rem; }
	
	.back {
		background: none;
		border: 1px solid #444;
		color: #888;
		padding: 0.5rem 1rem;
		cursor: pointer;
		margin-bottom: 1rem;
	}
	
	.search { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
	
	input { 
		flex: 1; 
		padding: 0.75rem; 
		font-size: 1rem; 
		background: #111;
		border: 1px solid #333;
		color: #eee;
		border-radius: 4px;
	}
	
	input:focus { outline: none; border-color: #666; }
	
	button { 
		padding: 0.75rem 1.5rem; 
		font-size: 1rem; 
		cursor: pointer;
		background: #222;
		border: 1px solid #444;
		color: #eee;
		border-radius: 4px;
	}
	
	button:hover:not(:disabled) { background: #333; }
	button:disabled { opacity: 0.5; cursor: not-allowed; }
	
	.results { list-style: none; padding: 0; margin: 0; }
	
	.results li { 
		padding: 0.75rem; 
		cursor: pointer; 
		border-bottom: 1px solid #222;
		display: flex;
		gap: 0.5rem;
	}
	
	.results li:hover { background: #111; }
	.results li.selected { background: #1a1a2e; border-left: 3px solid #646cff; }
	
	.artist { color: #888; }
	.title { font-weight: bold; }
	.duration { margin-left: auto; color: #555; }
	
	.selected {
		background: #111;
		padding: 1.5rem;
		border-radius: 8px;
		margin-top: 1rem;
	}
	
	.selected h2 { margin-top: 0; }
	
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
	
	.actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
</style>