<script lang="ts">
	import type { PageData } from './$types';
	import type { PageData as LivePageData } from '../live/$types';
	import type { PageData as ValuePageData } from '../value-bets/$types';
	import LiveOpportunities from '$lib/features/opportunities/LiveOpportunities.svelte';
	import ValueOpportunities from '$lib/features/opportunities/ValueOpportunities.svelte';

	let { data }: { data: PageData } = $props();
	const liveData = $derived(data.payload as LivePageData);
	const valueData = $derived(data.payload as ValuePageData);
</script>

<svelte:head><title>Opportunities · Betfront</title></svelte:head>

<nav class="mb-4 flex border-b border-border" aria-label="Opportunity views">
	<a href="/opportunities?view=value" aria-current={data.view === 'value' ? 'page' : undefined} class={["border-b-2 px-4 py-3 text-sm font-medium", data.view === 'value' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground']}>Value</a>
	<a href="/opportunities?view=live" aria-current={data.view === 'live' ? 'page' : undefined} class={["border-b-2 px-4 py-3 text-sm font-medium", data.view === 'live' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground']}>Live</a>
</nav>

{#key data.view}
	{#if data.view === 'live'}
		<LiveOpportunities data={liveData} />
	{:else}
		<ValueOpportunities data={valueData} />
	{/if}
{/key}
