<script lang="ts">
	import { AreaChart } from 'layerchart';

	let {
		data
	}: {
		data: { date: string; bankroll: number }[];
	} = $props();
</script>

<div class="w-full" style="height: 200px;">
	<AreaChart
		{data}
		x="date"
		y="bankroll"
		series={[
			{
				key: 'bankroll',
				label: 'Bankroll',
				color: 'hsl(var(--football-green))'
			}
		]}
		axis
		grid
		legend={false}
		tooltip={{ mode: 'bisect-x' }}
		props={{
			area: {
				fillOpacity: 0.3
			},
			tooltip: {
				header: {
					format: (v: string) => new Date(v).toLocaleDateString()
				},
				item: { format: 'currency' }
			}
		}}
	/>
</div>
