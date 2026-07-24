<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		eyebrow,
		title,
		description,
		actions
	}: {
		eyebrow: string;
		title: string;
		description: string;
		actions?: Snippet;
	} = $props();
</script>

<header class="flex flex-col gap-4 border-b border-border pb-6 sm:flex-row sm:items-end sm:justify-between">
	<div class="max-w-2xl">
		<p class="workbench-eyebrow">{eyebrow}</p>
		<h1 class="workbench-heading mt-2">{title}</h1>
		<p class="mt-3 text-sm leading-6 text-muted-foreground sm:text-base">{description}</p>
	</div>
	{#if actions}
		<div class="flex shrink-0 flex-wrap items-center gap-2">{@render actions()}</div>
	{/if}
</header>
