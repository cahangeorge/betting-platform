<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import { BarChart } from 'layerchart';

	let {
		data
	}: {
		data: { edge: string; count: number }[];
	} = $props();

	let isClientReady = $state(false);

	onMount(() => {
		const frame = requestAnimationFrame(() => {
			isClientReady = true;
		});

		return () => {
			cancelAnimationFrame(frame);
		};
	});

	const shouldRenderChart = $derived(browser && isClientReady && data.length > 0);
</script>

<div class="w-full" style="height: 200px;">
	{#if shouldRenderChart}
		<BarChart
			{data}
			x="edge"
			y="count"
			series={[{ key: 'count', label: 'Count', color: 'hsl(var(--football-green))' }]}
			axis
			grid
			legend={false}
			tooltip={{ mode: 'band' }}
			props={{
				tooltip: {
					item: { format: 'integer' }
				}
			}}
		/>
	{:else}
		<div class="flex h-full items-center justify-center border border-dashed border-border/60 bg-muted/20 text-xs font-mono text-muted-foreground">
			Preparing edge distribution…
		</div>
	{/if}
</div>
