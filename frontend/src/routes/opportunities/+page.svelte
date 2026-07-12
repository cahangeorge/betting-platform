<script lang="ts">
	import { page } from '$app/stores';
	import { Activity, ArrowRight, Radio, Sparkles } from 'lucide-svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import WorkflowHeader from '$lib/components/WorkflowHeader.svelte';

	const currentView = $derived($page.url.searchParams.get('view') === 'live' ? 'live' : 'value');
</script>

<svelte:head><title>Opportunities · Betfront</title></svelte:head>

<section class="workbench-page">
	<WorkflowHeader eyebrow="Step 3 of 4" title="Review opportunities, not noise" description="Compare trusted value and live selections in one place. Every ticket action should be backed by a visible edge, confidence, and freshness state." />
	<div class="flex border-b border-border" role="tablist" aria-label="Opportunity views">
		<a href="/opportunities?view=value" role="tab" aria-selected={currentView === 'value'} class={["border-b-2 px-4 py-3 text-sm font-medium", currentView === 'value' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground']}>Value</a>
		<a href="/opportunities?view=live" role="tab" aria-selected={currentView === 'live'} class={["border-b-2 px-4 py-3 text-sm font-medium", currentView === 'live' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground']}>Live</a>
	</div>
	{#if currentView === 'value'}
		<Card class="workbench-surface"><div class="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between"><div class="flex gap-3"><Sparkles class="mt-0.5 h-5 w-5 text-primary" /><div><h2 class="font-semibold text-foreground">Value selections</h2><p class="mt-1 max-w-2xl text-sm text-muted-foreground">Filter model-backed candidates, inspect their rationale, and add only eligible selections to the ticket slip.</p></div></div><a href="/value-bets"><Button>Open value feed <ArrowRight class="ml-2 h-4 w-4" /></Button></a></div></Card>
	{:else}
		<Card class="workbench-surface"><div class="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between"><div class="flex gap-3"><Radio class="mt-0.5 h-5 w-5 text-primary" /><div><h2 class="font-semibold text-foreground">Live selections</h2><p class="mt-1 max-w-2xl text-sm text-muted-foreground">Monitor current matches with one clear feed-health summary before acting on a live selection.</p></div></div><a href="/live"><Button>Open live monitor <ArrowRight class="ml-2 h-4 w-4" /></Button></a></div></Card>
	{/if}
	<div class="grid gap-4 sm:grid-cols-3"><Card class="workbench-surface"><Activity class="h-5 w-5 text-primary" /><p class="mt-4 text-sm font-semibold text-foreground">Edge first</p><p class="mt-1 text-sm text-muted-foreground">Sort decision candidates by value before decorative charts.</p></Card><Card class="workbench-surface"><p class="text-sm font-semibold text-foreground">Confidence is visible</p><p class="mt-1 text-sm text-muted-foreground">Reliability and data freshness are primary context, not tooltips.</p></Card><Card class="workbench-surface"><p class="text-sm font-semibold text-foreground">Clear next action</p><p class="mt-1 text-sm text-muted-foreground">Locked selections explain why and point to the recovery path.</p></Card></div>
</section>
