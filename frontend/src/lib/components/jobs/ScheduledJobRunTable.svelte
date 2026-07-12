<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { jobsApi } from '$lib/api/jobs';
	import { ApiClientError } from '$lib/api/client';
	import { artifactSummary, formatRunDuration, jobRunSortTimestamp } from '$lib/job-runs.helpers';
	import type { ScheduledJob, ScheduledJobRun } from '$lib/types';
	import JobRunStatusBadge from './JobRunStatusBadge.svelte';

	let { jobs, title = 'Recent scheduled runs' }: { jobs: ScheduledJob[]; title?: string } = $props();

	let runs = $state<ScheduledJobRun[]>([]);
	let loading = $state(false);
	let error = $state('');
	let notice = $state('');
	let deniedJobIds = $state<number[]>([]);
	let loadedKey = $state('');

	const jobIdsKey = $derived(jobs.map((job) => job.id).sort((a, b) => a - b).join(','));
	const readableJobs = $derived(jobs.filter((job) => !deniedJobIds.includes(job.id)));
	const deniedJobCount = $derived(jobs.filter((job) => deniedJobIds.includes(job.id)).length);

	async function loadRuns(force = false) {
		if (!jobIdsKey || (!force && loadedKey === jobIdsKey)) return;
		loading = true;
		error = '';
		notice = '';

		try {
			const jobsToLoad = readableJobs;
			const results = await Promise.allSettled(
				jobsToLoad.map((job) => jobsApi.getScheduledJobRuns(job.id, 1, 5))
			);

			const nextRuns: ScheduledJobRun[] = [];
			const newlyDeniedJobIds: number[] = [];
			let fatalError: Error | null = null;

			for (const [index, result] of results.entries()) {
				if (result.status === 'fulfilled') {
					nextRuns.push(...result.value.runs);
					continue;
				}

				const reason = result.reason;
				if (reason instanceof ApiClientError && reason.statusCode === 403) {
					const deniedJob = jobsToLoad[index];
					if (deniedJob) newlyDeniedJobIds.push(deniedJob.id);
					continue;
				}

				if (!fatalError) {
					fatalError = reason instanceof Error ? reason : new Error('Could not load scheduled run history');
				}
			}

			if (newlyDeniedJobIds.length > 0) {
				deniedJobIds = [...new Set([...deniedJobIds, ...newlyDeniedJobIds])];
			}

			runs = nextRuns
				.sort((a, b) => jobRunSortTimestamp(b) - jobRunSortTimestamp(a))
				.slice(0, 12);
			loadedKey = jobIdsKey;

			const notes: string[] = [];
			if (newlyDeniedJobIds.length > 0) {
				notes.push(
					`Skipped ${newlyDeniedJobIds.length} job${newlyDeniedJobIds.length === 1 ? '' : 's'} you cannot access.`
				);
			}
			if (fatalError) {
				if (nextRuns.length === 0 && notes.length === 0) {
					throw fatalError;
				}
				notes.push(`Some run history could not be loaded: ${fatalError.message}`);
			}
			notice = notes.join(' ');
		} catch (err) {
			error = err instanceof Error ? err.message : 'Could not load scheduled run history';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		void loadRuns();
	});

	$effect(() => {
		if (jobIdsKey && loadedKey !== jobIdsKey) {
			untrack(() => {
				void loadRuns();
			});
		}
	});
</script>

<div class="space-y-3 border border-border bg-muted/20 p-3">
	<div class="flex items-center justify-between gap-2">
		<div>
			<p class="text-sm font-semibold text-foreground">{title}</p>
			<p class="text-xs text-muted-foreground">Execution history from Postgres-backed job runs.</p>
		</div>
		<button
			class="text-xs text-football-blue hover:underline disabled:opacity-50"
			disabled={loading || !jobIdsKey}
			onclick={() => loadRuns(true)}
		>
			{loading ? 'Loading…' : 'Refresh'}
		</button>
	</div>

	{#if error}
		<p class="text-xs text-destructive">{error}</p>
	{:else if !jobIdsKey}
		<p class="text-xs text-muted-foreground">Save an automatic job to see run history.</p>
	{:else if deniedJobCount === jobs.length && runs.length === 0}
		<p class="text-xs text-muted-foreground">Run history is unavailable for the selected jobs.</p>
	{:else if loading && runs.length === 0}
		<p class="text-xs text-muted-foreground">Loading run history…</p>
	{:else if runs.length === 0}
		<p class="text-xs text-muted-foreground">No runs recorded yet.</p>
	{:else}
		<div class="overflow-x-auto">
			<table class="w-full text-left text-xs">
				<thead class="text-[10px] uppercase tracking-wide text-muted-foreground">
					<tr>
						<th class="py-2 pr-3">Run</th>
						<th class="py-2 pr-3">Status</th>
						<th class="py-2 pr-3">Duration</th>
						<th class="py-2 pr-3">Artifacts</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-border">
					{#each runs as run (run.id)}
						<tr>
							<td class="py-2 pr-3 font-mono text-muted-foreground">#{run.id}</td>
							<td class="py-2 pr-3"><JobRunStatusBadge status={run.status} /></td>
							<td class="py-2 pr-3 text-muted-foreground">{formatRunDuration(run)}</td>
							<td class="py-2 pr-3 text-muted-foreground" title={run.detail || run.error || ''}>
								{artifactSummary(run)}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

	{#if notice}
		<p class="text-xs text-muted-foreground">{notice}</p>
	{/if}
</div>
