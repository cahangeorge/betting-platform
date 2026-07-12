<script lang="ts">
	import { ArrowRight, BarChart3, SlidersHorizontal, Sparkles } from 'lucide-svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import WorkflowHeader from '$lib/components/WorkflowHeader.svelte';
</script>

<svelte:head><title>Analyze selections · Betfront</title></svelte:head>

<section class="workbench-page">
	<WorkflowHeader eyebrow="Step 2 of 4" title="Analyze with a single clear run" description="Choose a date window and strategy, run the model once, then move directly to the selections that are ready for review." />
	<div class="grid gap-4 lg:grid-cols-[1.35fr_0.65fr]">
		<Card class="workbench-surface">
			<div class="flex h-10 w-10 items-center justify-center bg-primary/10 text-primary"><BarChart3 class="h-5 w-5" /></div>
			<h2 class="mt-5 text-xl font-semibold text-foreground">Run an analysis</h2>
			<p class="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">The analysis workspace keeps selection filters, strategy choice, and run status together. Results are sorted by edge, confidence, and reliability.</p>
			<a class="mt-6 inline-flex" href="/predict"><Button>Open analysis workspace <ArrowRight class="ml-2 h-4 w-4" /></Button></a>
		</Card>
		<Card class="workbench-surface">
			<div class="flex h-10 w-10 items-center justify-center bg-muted text-muted-foreground"><SlidersHorizontal class="h-5 w-5" /></div>
			<h2 class="mt-5 text-base font-semibold text-foreground">Automation belongs in Monitoring</h2>
			<p class="mt-2 text-sm leading-6 text-muted-foreground">Keep this screen focused on a deliberate run. Create, pause, and inspect schedules from one shared place.</p>
			<a class="mt-5 inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline" href="/monitoring">Open monitoring <ArrowRight class="h-4 w-4" /></a>
		</Card>
	</div>
	<Card class="workbench-surface border-primary/30 bg-primary/5"><div class="flex items-start gap-3"><Sparkles class="mt-0.5 h-5 w-5 text-primary" /><div><h2 class="font-semibold text-foreground">What happens next</h2><p class="mt-1 text-sm text-muted-foreground">When a run completes, review the eligible selections in Opportunities before adding anything to a ticket.</p></div></div></Card>
</section>
