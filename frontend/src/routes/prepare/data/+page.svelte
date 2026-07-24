<script lang="ts">
	import LegacyDataExplorer from '../../data/+page.svelte';
	let { data, form, params } = $props();
	const legacyData = $derived(data as import('../../data/$types').PageData);
</script>

<svelte:head><title>Data explorer · Betfront</title></svelte:head>
<LegacyDataExplorer data={legacyData} {form} {params} />
