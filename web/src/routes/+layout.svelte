<script lang="ts">
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<div class="app-container">
	{@render children()}
	
	<footer>
		<span class="commit-hash">v08d201a</span>
	</footer>
</div>

<style>
	:global(body) {
		margin: 0;
		padding: 0;
		background-color: #0f0f0f;
		color: #e0e0e0;
		font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
	}

	.app-container {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}

	footer {
		margin-top: auto;
		padding: 1rem;
		text-align: right;
		opacity: 0.3;
		pointer-events: none;
	}

	.commit-hash {
		font-family: monospace;
		font-size: 0.7rem;
		color: #666;
	}
</style>
