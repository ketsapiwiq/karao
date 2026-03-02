<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

	let { lyrics, audioSrc } = $props<{ lyrics: string; audioSrc: string }>();

	interface LyricLine {
		time: number;
		text: string;
	}

	let lines = $state<LyricLine[]>([]);
	let currentLineIndex = $state(0);
	let audio = $state<HTMLAudioElement | null>(null);
	let currentTime = $state(0);
	let offset = $state(0); // Offset in seconds

	function parseLrc(lrc: string): LyricLine[] {
		const result: LyricLine[] = [];
		const pattern = /\[(\d+):(\d+\.?\d*)\](.*)/g;
		
		const rawLines = lrc.split('\n');
		for (const line of rawLines) {
			const match = pattern.exec(line);
			if (match) {
				const mins = parseInt(match[1]);
				const secs = parseFloat(match[2]);
				const text = match[3].trim();
				// We allow empty text for instrumental breaks
				result.push({ time: mins * 60 + secs, text: text || '...' });
			}
			pattern.lastIndex = 0;
		}
		
		return result.sort((a, b) => a.time - b.time);
	}

	function updateLyrics() {
		if (!audio || lines.length === 0) return;
		
		currentTime = audio.currentTime;
		const adjustedTime = currentTime + offset;
		
		// Fix rewind bug: if before the first line, index should be 0 or -1
		if (adjustedTime < lines[0].time) {
			currentLineIndex = -1;
			return;
		}

		for (let i = lines.length - 1; i >= 0; i--) {
			if (lines[i].time <= adjustedTime) {
				currentLineIndex = i;
				break;
			}
		}
	}

	function adjustOffset(amount: number) {
		offset += amount;
	}

	function handleKeydown(e: KeyboardEvent) {
		// Shortcuts for offset
		if (e.key === '[') adjustOffset(-1);
		if (e.key === ']') adjustOffset(1);
		if (e.key === '{') adjustOffset(-5);
		if (e.key === '}') adjustOffset(5);
		
		// Media keys
		if (e.code === 'Space') {
			e.preventDefault();
			if (audio) {
				if (audio.paused) audio.play();
				else audio.pause();
			}
		}
	}

	onMount(() => {
		lines = parseLrc(lyrics);
		audio = document.querySelector('audio');
		
		if (audio) {
			audio.addEventListener('timeupdate', updateLyrics);
		}
		window.addEventListener('keydown', handleKeydown);
	});

	onDestroy(() => {
		if (audio) {
			audio.removeEventListener('timeupdate', updateLyrics);
		}
		window.removeEventListener('keydown', handleKeydown);
	});

	let displayLines = $derived([
		lines[currentLineIndex - 1] || null,
		lines[currentLineIndex] || null,
		lines[currentLineIndex + 1] || null
	]);
</script>

<div class="karaoke">
	<audio controls src={audioSrc}></audio>
	
	<div class="lyrics-display">
		{#each displayLines as line, i}
			{#if line}
				<p class="line {i === 1 ? 'current' : ''}">
					{line.text}
				</p>
			{:else}
				<p class="line empty">&nbsp;</p>
			{/if}
		{/each}
	</div>

	<div class="sync-controls">
		<span class="offset-label">Sync: {offset > 0 ? '+' : ''}{offset.toFixed(1)}s</span>
		<div class="buttons">
			<button onclick={() => adjustOffset(-5)} title="-5s">-5</button>
			<button onclick={() => adjustOffset(-1)} title="-1s">-1</button>
			<button onclick={() => adjustOffset(1)} title="+1s">+1</button>
			<button onclick={() => adjustOffset(5)} title="+5s">+5</button>
			<button class="reset" onclick={() => offset = 0}>Reset</button>
		</div>
	</div>
</div>

<style>
	.karaoke {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2rem;
		padding: 2rem;
		position: relative;
		min-height: 400px;
	}
	
	audio {
		width: 100%;
		max-width: 600px;
	}
	
	.lyrics-display {
		text-align: center;
		min-height: 250px;
		display: flex;
		flex-direction: column;
		justify-content: center;
	}
	
	.line {
		font-size: 2rem;
		margin: 0.8rem 0;
		transition: all 0.2s ease-out;
		color: #444;
	}
	
	.line.current {
		color: #fff;
		font-size: 3rem;
		font-weight: bold;
		text-shadow: 0 0 20px rgba(100, 108, 255, 0.5);
	}
	
	.line.empty {
		visibility: hidden;
	}

	.sync-controls {
		position: fixed;
		bottom: 1.5rem;
		right: 1.5rem;
		background: rgba(20, 20, 20, 0.8);
		padding: 0.75rem;
		border-radius: 8px;
		border: 1px solid #333;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		backdrop-filter: blur(4px);
		z-index: 100;
	}

	.offset-label {
		font-size: 0.8rem;
		color: #888;
		text-align: center;
		font-family: monospace;
	}

	.buttons {
		display: flex;
		gap: 0.25rem;
	}

	.sync-controls button {
		background: #222;
		border: 1px solid #444;
		color: #ccc;
		padding: 0.4rem 0.6rem;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.8rem;
		transition: all 0.2s;
	}

	.sync-controls button:hover {
		background: #333;
		border-color: #666;
		color: #fff;
	}

	.sync-controls button.reset {
		margin-left: 0.5rem;
		background: #1a1a2e;
	}
</style>
