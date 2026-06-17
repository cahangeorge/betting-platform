<script lang="ts">
	import { BarChart } from 'layerchart';

	let {
		data
	}: {
		data: { bookmaker: string; odds: number }[];
	} = $props();

	const maxOdds = $derived(Math.max(...data.map((d) => d.odds)));

	const chartData = $derived(
		data.map((d) => ({
			...d,
			isBest: d.odds === maxOdds,
			color:
				d.odds === maxOdds
					? 'hsl(var(--football-green))'
					: 'hsl(var(--muted-foreground))'
		}))
	);
</script>

<div class="w-full" style="height: 200px;">
	<BarChart
		data={chartData}
		x="bookmaker"
		y="odds"
		series={[{ key: 'odds', label: 'Odds', color: 'hsl(var(--football-blue))' }]}
		axis
		grid
		legend={false}
		tooltip={{ mode: 'band' }}
		props={{
			tooltip: {
				item: { format: 'decimal' }
			}
		}}
	/>
</div>
