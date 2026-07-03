<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import { AreaChart } from 'layerchart';

	let {
		data
	}: {
		data: { minute: number; homeXg: number; awayXg: number }[];
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
		<AreaChart
			{data}
			x="minute"
			series={[
				{ key: 'homeXg', label: 'Home xG', color: 'hsl(var(--football-green))' },
				{ key: 'awayXg', label: 'Away xG', color: 'hsl(var(--football-blue))' }
			]}
			axis
			grid
			legend
			tooltip={{ mode: 'bisect-x' }}
			props={{
				area: {
					fillOpacity: 0.2
				},
				tooltip: {
					item: { format: 'decimal' }
				}
			}}
		/>
	{:else}
		<div class="flex h-full items-center justify-center border border-dashed border-border/60 bg-muted/20 text-xs font-mono text-muted-foreground">
			Preparing xG timeline…
		</div>
	{/if}
</div>
