<script lang="ts">
	import { LineChart } from 'layerchart';

	let {
		history,
		width = 100,
		height = 30
	}: {
		history: { timestamp: string; odds: number }[];
		width?: number;
		height?: number;
	} = $props();

	const sorted = $derived(
		[...history].sort(
			(a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
		)
	);

	const values = $derived(sorted.map((p) => p.odds));
	const firstOdds = $derived(values[0] ?? 0);
	const lastOdds = $derived(values[values.length - 1] ?? 0);
	const isTrendingDown = $derived(lastOdds < firstOdds);
	const lineColor = $derived(
		isTrendingDown ? 'hsl(var(--football-green))' : 'hsl(var(--destructive))'
	);
	const directionArrow = $derived(isTrendingDown ? '\u25B2' : '\u25BC');
	const directionColor = $derived(isTrendingDown ? 'text-football-green' : 'text-destructive');
</script>

<div class="relative inline-block" style="width: {width}px;">
	<div style="height: {height}px;">
		<LineChart
			data={sorted}
			x="timestamp"
			series={[{ key: 'odds', label: 'Odds', color: lineColor }]}
			axis={false}
			grid={false}
			legend={false}
			points={false}
			tooltip={{ mode: 'bisect-x' }}
			props={{
				tooltip: {
					header: {
						format: (v: string) =>
							new Date(v).toLocaleTimeString('en-GB', {
								hour: '2-digit',
								minute: '2-digit'
							})
					},
					item: { format: 'decimal' }
				}
			}}
		/>
	</div>

	{#if sorted.length > 1}
		<span class="ml-1 text-[10px] font-mono {directionColor}">
			{directionArrow}
		</span>
	{/if}
</div>
