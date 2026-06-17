<script lang="ts">
	import { BarChart } from 'layerchart';

	let {
		data
	}: {
		data: { edge: string; count: number }[];
	} = $props();
</script>

<div class="w-full" style="height: 200px;">
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
</div>
