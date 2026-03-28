<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

let { lyrics, audioSrc, videoSrc = "", enableVideo = true, trackName = "", showAllLyrics = $bindable(false) } = $props<{
	lyrics: string;
	audioSrc: string;
	videoSrc?: string;
	enableVideo?: boolean;
	trackName?: string;
	showAllLyrics?: boolean;
}>();

interface LyricLine {
	time: number;
	text: string;
}

let lines = $state<LyricLine[]>([]);
let currentLineIndex = $state(-1);
let audio = $state<HTMLAudioElement | null>(null);
let video = $state<HTMLVideoElement | null>(null);
let currentTime = $state(0);
let offset = $state(0); // Offset in seconds
let toast = $state<{ text: string; id: number } | null>(null);
let toastTimeout: any;

function showToast(text: string) {
		if (toastTimeout) clearTimeout(toastTimeout);
		toast = { text, id: Date.now() };
		toastTimeout = setTimeout(() => {
			toast = null;
		}, 1500);
	}

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
		
		// Sync video if present
		if (video) {
			if (Math.abs(video.currentTime - audio.currentTime) > 0.3) {
				video.currentTime = audio.currentTime;
			}
			if (audio.paused !== video.paused) {
				if (audio.paused) video.pause();
				else video.play();
			}
		}

		let newIndex = -1;
		for (let i = lines.length - 1; i >= 0; i--) {
			if (lines[i].time <= adjustedTime) {
				newIndex = i;
				break;
			}
		}
		if (newIndex !== currentLineIndex) {
			currentLineIndex = newIndex;
		}
	}

	function adjustOffset(amount: number) {
		offset += amount;
		showToast(`${amount > 0 ? '+' : ''}${amount.toFixed(1)}s Sync`);
		if (trackName) {
			localStorage.setItem(`offset_${trackName}`, offset.toString());
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		// Shortcuts for offset
		if (e.key === '[') adjustOffset(-1.0);
		if (e.key === ']') adjustOffset(1.0);
		if (e.key === '{') adjustOffset(-5.0);
		if (e.key === '}') adjustOffset(5.0);
		
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
		video = document.querySelector('video.bg-video');
		
		if (trackName) {
			const savedOffset = localStorage.getItem(`offset_${trackName}`);
			if (savedOffset) offset = parseFloat(savedOffset);
		}

		if (audio) {
			audio.addEventListener('timeupdate', updateLyrics);
			audio.addEventListener('play', () => video?.play());
			audio.addEventListener('pause', () => video?.pause());
			audio.addEventListener('seeking', () => {
				if (video) video.currentTime = audio.currentTime;
			});
		}
		window.addEventListener('keydown', handleKeydown);
	});

	onDestroy(() => {
		if (audio) {
			audio.removeEventListener('timeupdate', updateLyrics);
		}
		window.removeEventListener('keydown', handleKeydown);
	});

	let displayLines = $derived(
		showAllLyrics
			? lines
			: [
					lines[currentLineIndex - 1] || null,
					lines[currentLineIndex] || null,
					lines[currentLineIndex + 1] || null
				]
	);

	// Calculate progress for the initial buildup bar
	let showLoadingBar = $derived.by(() => {
		if (!lines.length || currentLineIndex !== -1) return false;
		const nextLine = lines[0];
		if (!nextLine) return false;
		
		const adjustedTime = currentTime + offset;
		// Hide when the first line starts
		return adjustedTime < nextLine.time;
	});

	let loadingProgress = $derived.by(() => {
		if (!showLoadingBar) return 0;
		const nextLine = lines[0];
		// Reach 100% one second before the line starts
		const targetTime = Math.max(0.1, nextLine.time - 1);
		const elapsed = currentTime + offset;
		
		return Math.min(Math.max(elapsed / targetTime, 0), 1);
	});
</script>

<div class="karaoke">
	{#if videoSrc && enableVideo}
		<video
			class="bg-video"
			src={videoSrc}
			muted
			playsinline
			loop
		></video>
		<div class="overlay"></div>
	{/if}

	<audio controls src={audioSrc}></audio>
	
	<div class="lyrics-display" class:show-all={showAllLyrics}>
		{#if showLoadingBar && !showAllLyrics}
			<div class="break-indicator">
				<div class="loader-track">
					<div class="loader-bar" style="width: {loadingProgress * 100}%"></div>
				</div>
			</div>
		{/if}

		{#if showAllLyrics}
			<div class="lyrics-scroll-container">
				{#each displayLines as line, i}
					<p class="line {i === currentLineIndex ? 'current' : ''}">
						{line.text}
					</p>
				{/each}
			</div>
		{:else}
			{#each displayLines as line, i}
				{#if line}
					<p class="line {i === 1 ? 'current' : ''}">
						{line.text}
					</p>
				{:else}
					<p class="line empty">&nbsp;</p>
				{/if}
			{/each}
		{/if}
	</div>

	{#if toast}
		<div class="toast" key={toast.id}>
			{toast.text}
		</div>
	{/if}

	<div class="sync-controls">
		<span class="offset-label">Sync: {offset > 0 ? '+' : ''}{offset.toFixed(1)}s</span>
		<div class="buttons">
			<button onclick={() => adjustOffset(-5)} title="-5s">-5</button>
			<button onclick={() => adjustOffset(-1)} title="-1s">-1</button>
			<button onclick={() => adjustOffset(1)} title="+1s">+1</button>
			<button onclick={() => adjustOffset(5)} title="+5s">+5</button>
			<button class="reset" onclick={() => {
				offset = 0;
				if (trackName) localStorage.removeItem(`offset_${trackName}`);
				showToast("Sync Reset");
			}}>Reset</button>
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
		width: 100%;
		overflow: hidden;
	}

	.bg-video {
		position: fixed;
		top: 0;
		left: 0;
		width: 100vw;
		height: 100vh;
		object-fit: cover;
		opacity: 0.25;
		z-index: -2;
		pointer-events: none;
	}

	.overlay {
		position: fixed;
		top: 0;
		left: 0;
		width: 100vw;
		height: 100vh;
		background: #000;
		z-index: -3;
	}
	
	audio {
		width: 100%;
		max-width: 600px;
	}
	
	.lyrics-display {
		text-align: center;
		min-height: 350px;
		display: flex;
		flex-direction: column;
		justify-content: center;
		width: 100%;
		position: relative;
	}
	
	.line {
		font-size: 2rem;
		margin: 1.5rem 0;
		transition: all 0.2s ease-out;
		color: #444;
		position: relative;
		padding-top: 10px;
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

	.break-indicator {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		width: 100%;
		max-width: 250px;
		pointer-events: none;
		opacity: 0.6;
		z-index: 5;
	}

	.loader-track {
		height: 2px;
		background: rgba(255, 255, 255, 0.05);
		border-radius: 10px;
		overflow: hidden;
	}

	.loader-bar {
		height: 100%;
		background: linear-gradient(90deg, #444, #fff, #444);
		background-size: 200% 100%;
		animation: shimmer 2s infinite linear;
		border-radius: 10px;
	}

	@keyframes shimmer {
		0% { background-position: 200% 0; }
		100% { background-position: -200% 0; }
	}

	.toast {
		position: fixed;
		top: 2rem;
		left: 50%;
		transform: translateX(-50%);
		background: #646cff;
		color: white;
		padding: 0.5rem 1.5rem;
		border-radius: 20px;
		font-weight: bold;
		box-shadow: 0 4px 12px rgba(0,0,0,0.5);
		z-index: 1000;
		pointer-events: none;
		animation: slideDown 0.2s ease-out;
	}

	@keyframes slideDown {
		from { transform: translate(-50%, -20px); opacity: 0; }
		to { transform: translate(-50%, 0); opacity: 1; }
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

	.lyrics-display.show-all {
		min-height: 400px;
		max-height: 500px;
		overflow: hidden;
	}

	.lyrics-scroll-container {
		max-height: 450px;
		overflow-y: auto;
		padding-right: 1rem;
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.lyrics-scroll-container::-webkit-scrollbar {
		width: 6px;
	}

	.lyrics-scroll-container::-webkit-scrollbar-track {
		background: rgba(255, 255, 255, 0.05);
		border-radius: 3px;
	}

	.lyrics-scroll-container::-webkit-scrollbar-thumb {
		background: #444;
		border-radius: 3px;
	}

	.lyrics-scroll-container::-webkit-scrollbar-thumb:hover {
		background: #666;
	}

	.lyrics-scroll-container .line {
		font-size: 1.5rem;
		margin: 0.75rem 0;
		color: #ccc;
		opacity: 0.6;
		transition: all 0.3s ease;
	}

	.lyrics-scroll-container .line.current {
		color: #fff;
		opacity: 1;
		font-size: 2rem;
		font-weight: bold;
	}
</style>
