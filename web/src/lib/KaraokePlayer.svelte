<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

	let { lyrics, audioSrc, trackName = "" } = $props<{ lyrics: string; audioSrc: string; trackName?: string }>();

	interface LyricLine {
		time: number;
		text: string;
	}

	let lines = $state<LyricLine[]>([]);
	let currentLineIndex = $state(-1);
	let audio = $state<HTMLAudioElement | null>(null);
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
		if (e.key === '[') adjustOffset(-0.1);
		if (e.key === ']') adjustOffset(0.1);
		if (e.key === '{') adjustOffset(-1.0);
		if (e.key === '}') adjustOffset(1.0);
		
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
		
		if (trackName) {
			const savedOffset = localStorage.getItem(`offset_${trackName}`);
			if (savedOffset) offset = parseFloat(savedOffset);
		}

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

	// Calculate progress to next line for the cursor
	let nextLineProgress = $derived.by(() => {
		if (!lines.length) return 0;
		const nextLine = lines[currentLineIndex + 1];
		if (!nextLine) return 0;
		
		const currentLineTime = currentLineIndex >= 0 ? lines[currentLineIndex].time : 0;
		const totalWait = nextLine.time - currentLineTime;
		const elapsed = (currentTime + offset) - currentLineTime;
		
		return Math.min(Math.max(elapsed / totalWait, 0), 1);
	});
</script>

<div class="karaoke">
	<audio controls src={audioSrc}></audio>
	
	<div class="lyrics-display">
		{#each displayLines as line, i}
			{#if line}
				<p class="line {i === 1 ? 'current' : ''}">
					{#if i === 1 && lines[currentLineIndex + 1]}
						<div class="cursor-track">
							<div class="cursor" style="width: {nextLineProgress * 100}%"></div>
						</div>
					{/if}
					{line.text}
				</p>
			{:else}
				<p class="line empty">&nbsp;</p>
			{/if}
		{/each}
	</div>

	{#if toast}
		<div class="toast" key={toast.id}>
			{toast.text}
		</div>
	{/if}

	<div class="sync-controls">
		<span class="offset-label">Sync: {offset > 0 ? '+' : ''}{offset.toFixed(1)}s</span>
		<div class="buttons">
			<button onclick={() => adjustOffset(-1)} title="-1s">-1</button>
			<button onclick={() => adjustOffset(-0.1)} title="-0.1s">-0.1</button>
			<button onclick={() => adjustOffset(0.1)} title="+0.1s">+0.1</button>
			<button onclick={() => adjustOffset(1)} title="+1s">+1</button>
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
		width: 100%;
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

	.cursor-track {
		position: absolute;
		top: -5px;
		left: 20%;
		right: 20%;
		height: 3px;
		background: rgba(255, 255, 255, 0.1);
		border-radius: 2px;
		overflow: hidden;
	}

	.cursor {
		height: 100%;
		background: #646cff;
		box-shadow: 0 0 10px #646cff;
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
</style>
