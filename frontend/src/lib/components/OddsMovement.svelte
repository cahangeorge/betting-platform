<script lang="ts">
	import OddsMovementChart from './charts/OddsMovementChart.svelte';

	let {
		history,
		width = 100,
		height = 30
	}: {
		history: { timestamp: string; odds: number }[];
		width?: number;
		height?: number;
	} = $props();
</script>

<OddsMovementChart {history} {width} {height} />
