<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

	export let lyrics: string;
	export let audioSrc: string;

	interface LyricLine {
		time: number;
		text: string;
	}

	let lines: LyricLine[] = [];
	let currentLineIndex = 0;
	let audio: HTMLAudioElement | null = null;
	let isPlaying = false;
	let currentTime = 0;

	function parseLrc(lrc: string): LyricLine[] {
		const result: LyricLine[] = [];
		const pattern = /\[(\d+):(\d+\.?\d*)\](.*)/g;
		
		for (const line of lrc.split('\n')) {
			const match = pattern.exec(line);
			if (match) {
				const mins = parseInt(match[1]);
				const secs = parseFloat(match[2]);
				const text = match[3].trim();
				if (text) {
					result.push({ time: mins * 60 + secs, text });
				}
			}
			pattern.lastIndex = 0;
		}
		
		return result.sort((a, b) => a.time - b.time);
	}

	function updateLyrics() {
		if (!audio || lines.length === 0) return;
		
		currentTime = audio.currentTime;
		
		for (let i = lines.length - 1; i >= 0; i--) {
			if (lines[i].time <= currentTime) {
				currentLineIndex = i;
				break;
			}
		}
	}

	onMount(() => {
		lines = parseLrc(lyrics);
		audio = document.querySelector('audio');
		
		if (audio) {
			audio.addEventListener('timeupdate', updateLyrics);
		}
	});

	onDestroy(() => {
		if (audio) {
			audio.removeEventListener('timeupdate', updateLyrics);
		}
	});

	$: displayLines = [
		lines[currentLineIndex - 1] || null,
		lines[currentLineIndex] || null,
		lines[currentLineIndex + 1] || null
	];
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
</div>

<style>
	.karaoke {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2rem;
		padding: 2rem;
	}
	
	audio {
		width: 100%;
		max-width: 600px;
	}
	
	.lyrics-display {
		text-align: center;
		min-height: 200px;
	}
	
	.line {
		font-size: 2rem;
		margin: 0.5rem 0;
		transition: all 0.3s ease;
		color: #666;
	}
	
	.line.current {
		color: #fff;
		font-size: 2.5rem;
		font-weight: bold;
	}
	
	.line.empty {
		visibility: hidden;
	}
</style>