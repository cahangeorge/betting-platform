<script lang="ts">
	import LegacyAccount from '../../account/+page.svelte';
	let { data, form, params } = $props();
	const legacyData = $derived(data as import('../../account/$types').PageData);
</script>

<svelte:head><title>Account settings · Betfront</title></svelte:head>
<LegacyAccount data={legacyData} {form} {params} />
