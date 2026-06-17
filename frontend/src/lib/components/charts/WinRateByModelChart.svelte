<script lang="ts">
	import { BarChart } from 'layerchart';

	let {
		data
	}: {
		data: { model: string; winRate: number; count: number }[];
	} = $props();

	const modelColors: Record<string, string> = {
		poisson: 'hsl(var(--football-green))',
		bivariate_poisson: 'hsl(var(--football-green))',
		dixon_coles: 'hsl(var(--football-blue))',
		elo: 'hsl(var(--football-blue))',
		xgboost: 'hsl(280 65% 60%)',
		ensemble: 'hsl(var(--football-gold))'
	};

	const chartData = $derived(
		data.map((d) => ({
			...d,
			color: modelColors[d.model] || 'hsl(var(--primary))'
		}))
	);
</script>

<div class="w-full" style="height: 250px;">
	<BarChart
		data={chartData}
		x="model"
		y="winRate"
		series={[{ key: 'winRate', label: 'Win Rate %', color: 'hsl(var(--football-green))' }]}
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
