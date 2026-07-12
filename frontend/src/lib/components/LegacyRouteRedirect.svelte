<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	let { target, fixedParams = {} }: { target: string; fixedParams?: Record<string, string> } = $props();

	onMount(() => {
		if (!browser) return;
		const params = new URLSearchParams(window.location.search);
		for (const [key, value] of Object.entries(fixedParams)) params.set(key, value);
		const query = params.toString();
		const hash = window.location.hash;
		void goto(`${target}${query ? `?${query}` : ''}${hash}`, { replaceState: true });
	});
</script>

<svelte:head><meta name="robots" content="noindex" /></svelte:head>

<p class="p-6 text-sm text-muted-foreground" role="status">Redirecting to the current workspace…</p>
