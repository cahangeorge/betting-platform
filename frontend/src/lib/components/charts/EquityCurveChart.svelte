<script lang="ts">
	let {
		data
	}: {
		data: { date: string; bankroll: number }[];
	} = $props();

	const width = 640;
	const height = 200;
	const padding = { top: 18, right: 18, bottom: 30, left: 54 };
	const plotWidth = width - padding.left - padding.right;
	const plotHeight = height - padding.top - padding.bottom;

	const chartData = $derived(
		data
			.filter((point) => Number.isFinite(Date.parse(point.date)) && Number.isFinite(point.bankroll))
			.toSorted((a, b) => Date.parse(a.date) - Date.parse(b.date))
	);
	const minValue = $derived(chartData.length > 0 ? Math.min(...chartData.map((point) => point.bankroll)) : 0);
	const maxValue = $derived(chartData.length > 0 ? Math.max(...chartData.map((point) => point.bankroll)) : 0);
	const valueRange = $derived(Math.max(maxValue - minValue, Math.abs(maxValue) * 0.05, 1));
	const displayMin = $derived(minValue - valueRange * 0.1);
	const displayMax = $derived(maxValue + valueRange * 0.1);
	const firstPoint = $derived(chartData[0]);
	const lastPoint = $derived(chartData.at(-1));
	const yTicks = $derived([displayMin, (displayMin + displayMax) / 2, displayMax]);

	function scaleX(index: number): number {
		return padding.left + (index / Math.max(chartData.length - 1, 1)) * plotWidth;
	}

	function scaleY(value: number): number {
		return padding.top + plotHeight - ((value - displayMin) / Math.max(displayMax - displayMin, 1)) * plotHeight;
	}

	const linePoints = $derived(
		chartData.map((point, index) => `${scaleX(index)},${scaleY(point.bankroll)}`).join(' ')
	);
	const areaPoints = $derived(
		chartData.length > 0
			? `${padding.left},${height - padding.bottom} ${linePoints} ${scaleX(chartData.length - 1)},${height - padding.bottom}`
			: ''
	);

	function formatAmount(value: number): string {
		return new Intl.NumberFormat('ro-RO', { maximumFractionDigits: 0 }).format(value);
	}

	function formatDate(value: string): string {
		return new Intl.DateTimeFormat('ro-RO', { day: '2-digit', month: 'short' }).format(new Date(value));
	}
</script>

<div class="h-[200px] w-full">
	{#if chartData.length > 1 && firstPoint && lastPoint}
		<svg
			class="h-full w-full overflow-visible"
			viewBox={`0 0 ${width} ${height}`}
			role="img"
			aria-label={`Evoluția bankrollului de la ${formatAmount(firstPoint.bankroll)} la ${formatAmount(lastPoint.bankroll)}`}
		>
			<title>Evoluția bankrollului</title>
			<desc>{chartData.length} puncte între {formatDate(firstPoint.date)} și {formatDate(lastPoint.date)}.</desc>

			{#each yTicks as tick (tick)}
				{@const y = scaleY(tick)}
				<line x1={padding.left} y1={y} x2={width - padding.right} y2={y} class="stroke-border/60" stroke-dasharray="4 4" />
				<text x={padding.left - 8} y={y + 4} text-anchor="end" class="fill-muted-foreground text-[11px]">{formatAmount(tick)}</text>
			{/each}

			<polygon points={areaPoints} fill="hsl(var(--football-green) / 0.16)" />
			<polyline points={linePoints} fill="none" stroke="hsl(var(--football-green))" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" />
			<circle cx={scaleX(chartData.length - 1)} cy={scaleY(lastPoint.bankroll)} r="4" fill="hsl(var(--football-green))" />

			<text x={padding.left} y={height - 8} text-anchor="start" class="fill-muted-foreground text-[11px]">{formatDate(firstPoint.date)}</text>
			<text x={width - padding.right} y={height - 8} text-anchor="end" class="fill-muted-foreground text-[11px]">{formatDate(lastPoint.date)}</text>
		</svg>
	{:else}
		<div class="flex h-full items-center justify-center border border-dashed border-border/60 bg-muted/20 text-sm text-muted-foreground">
			Sunt necesare cel puțin două înregistrări pentru grafic.
		</div>
	{/if}
</div>
