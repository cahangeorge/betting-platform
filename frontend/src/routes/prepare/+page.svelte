<script lang="ts">
	import { ArrowRight, CheckCircle2, Clock3, Database, Settings2 } from 'lucide-svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import WorkflowHeader from '$lib/components/WorkflowHeader.svelte';

	const steps = [
		{
			number: '01',
			title: 'Choose competitions',
			detail: 'Select leagues and the data source you want to refresh.',
			icon: Database,
			href: '/scrape#selection'
		},
		{
			number: '02',
			title: 'Set coverage',
			detail: 'Define history and upcoming windows before work is queued.',
			icon: Clock3,
			href: '/scrape#coverage'
		},
		{
			number: '03',
			title: 'Review and run',
			detail: 'Confirm deduplication and start a single, traceable job.',
			icon: CheckCircle2,
			href: '/scrape#controls'
		}
	];
</script>

<svelte:head><title>Prepare data · Betfront</title></svelte:head>

<section class="workbench-page">
	<WorkflowHeader eyebrow="Step 1 of 4" title="Prepare reliable match data" description="Start with a clear scope. Advanced scraping controls and historical job logs stay available without competing with the next decision." />

	<div class="grid gap-4 lg:grid-cols-3">
		{#each steps as step (step.number)}
			<a
				href={step.href}
				class="group block min-h-56 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
				aria-label={`${step.title}: open data preparation workspace`}
			>
				<Card class="workbench-surface h-full transition-shadow motion-safe:duration-200 group-hover:shadow-lg">
					<div class="flex items-start justify-between gap-4">
						<div class="flex h-10 w-10 items-center justify-center bg-primary/10 text-primary"><step.icon class="h-5 w-5" /></div>
						<span class="font-mono text-xs text-muted-foreground">{step.number}</span>
					</div>
					<h2 class="mt-6 text-lg font-semibold text-foreground">{step.title}</h2>
					<p class="mt-2 text-sm leading-6 text-muted-foreground">{step.detail}</p>
					<span class="mt-6 inline-flex items-center gap-2 text-sm font-medium text-primary group-hover:underline">
						Continue <ArrowRight class="h-4 w-4" />
					</span>
				</Card>
			</a>
		{/each}
	</div>

	<Card class="workbench-surface" padded={false}>
		<div class="flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:justify-between">
			<div class="flex gap-3"><Settings2 class="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" /><div><h2 class="font-semibold text-foreground">Need the full scraping workspace?</h2><p class="mt-1 text-sm text-muted-foreground">Use advanced sources, automation, specialist pipelines, and raw job logs in the existing operational view.</p></div></div>
			<a
				href="/scrape"
				class="inline-flex h-10 items-center justify-center whitespace-nowrap bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
			>
				Open data preparation
			</a>
		</div>
	</Card>
</section>
