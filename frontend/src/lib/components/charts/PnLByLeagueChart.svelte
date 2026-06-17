<script lang="ts">
	import { BarChart } from 'layerchart';

	let {
		data
	}: {
		data: { league: string; profit: number }[];
	} = $props();

	const chartData = $derived(
		data.map((d) => ({
			...d,
			color: d.profit >= 0 ? 'hsl(var(--football-green))' : 'hsl(var(--destructive))'
		}))
	);
</script>

<div class="w-full" style="height: 250px;">
	<BarChart
		data={chartData}
		x="league"
		y="profit"
		series={[{ key: 'profit', label: 'Profit', color: 'hsl(var(--football-green))' }]}
		axis
		grid
		legend={false}
		tooltip={{ mode: 'band' }}
		props={{
			tooltip: {
				item: { format: 'currency' }
			}
		}}
	/>
</div>
