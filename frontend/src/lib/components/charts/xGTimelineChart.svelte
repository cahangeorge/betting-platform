<script lang="ts">
	type XgTimelinePoint = {
		minute: number;
		homeXg: number;
		awayXg: number;
	};

	let { data }: { data: XgTimelinePoint[] } = $props();

	const width = 360;
	const height = 180;
	const padding = { top: 16, right: 16, bottom: 28, left: 38 };
	const plotWidth = width - padding.left - padding.right;
	const plotHeight = height - padding.top - padding.bottom;

	const chartData = $derived(
		data
			.filter(
				(point) =>
					Number.isFinite(point.minute) &&
					Number.isFinite(point.homeXg) &&
					Number.isFinite(point.awayXg)
			)
			.sort((a, b) => a.minute - b.minute)
	);
	const maxMinute = $derived(Math.max(90, ...chartData.map((point) => point.minute)));
	const maxXg = $derived(Math.max(1, ...chartData.flatMap((point) => [point.homeXg, point.awayXg])) * 1.1);
	const xTicks = $derived([0, Math.round(maxMinute / 2), maxMinute]);
	const yTicks = $derived([0, Math.round((maxXg / 2) * 10) / 10, Math.round(maxXg * 10) / 10]);

	function scaleX(minute: number) {
		return padding.left + (minute / maxMinute) * plotWidth;
	}

	function scaleY(xg: number) {
		return padding.top + plotHeight - (xg / maxXg) * plotHeight;
	}

	const homePoints = $derived(
		chartData.map((point) => `${scaleX(point.minute)},${scaleY(point.homeXg)}`).join(' ')
	);
	const awayPoints = $derived(
		chartData.map((point) => `${scaleX(point.minute)},${scaleY(point.awayXg)}`).join(' ')
	);
	const latest = $derived(chartData.at(-1));
</script>

<div class="w-full rounded border border-border/60 bg-muted/10 p-2" style="height: 200px;">
	{#if chartData.length > 0}
		<svg class="h-full w-full overflow-visible" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Expected goals timeline">
			<line x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} class="stroke-border" />
			<line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} class="stroke-border" />

			{#each yTicks as tick (tick)}
				{@const y = scaleY(tick)}
				<line x1={padding.left} y1={y} x2={width - padding.right} y2={y} class="stroke-border/50" stroke-dasharray="3 3" />
				<text x={padding.left - 8} y={y + 4} text-anchor="end" class="fill-muted-foreground text-[10px]">{tick.toFixed(1)}</text>
			{/each}

			{#each xTicks as tick (tick)}
				{@const x = scaleX(tick)}
				<text x={x} y={height - 8} text-anchor="middle" class="fill-muted-foreground text-[10px]">{tick}'</text>
			{/each}

			<polyline points={homePoints} fill="none" stroke="hsl(var(--football-green))" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />
			<polyline points={awayPoints} fill="none" stroke="hsl(var(--football-blue))" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />

			{#if latest}
				<circle cx={scaleX(latest.minute)} cy={scaleY(latest.homeXg)} r="3" fill="hsl(var(--football-green))" />
				<circle cx={scaleX(latest.minute)} cy={scaleY(latest.awayXg)} r="3" fill="hsl(var(--football-blue))" />
			{/if}
		</svg>

		<div class="mt-1 flex items-center justify-center gap-4 text-[10px] font-mono text-muted-foreground">
			<span class="flex items-center gap-1"><span class="h-2 w-2 bg-football-green"></span>Home xG</span>
			<span class="flex items-center gap-1"><span class="h-2 w-2 bg-football-blue"></span>Away xG</span>
		</div>
	{:else}
		<div class="flex h-full items-center justify-center border border-dashed border-border/60 bg-muted/20 text-xs font-mono text-muted-foreground">
			No xG timeline available
		</div>
	{/if}
</div>
