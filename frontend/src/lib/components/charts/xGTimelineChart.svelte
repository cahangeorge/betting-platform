<script lang="ts">
	import { AreaChart } from 'layerchart';

	let {
		data
	}: {
		data: { minute: number; homeXg: number; awayXg: number }[];
	} = $props();
</script>

<div class="w-full" style="height: 200px;">
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
</div>
