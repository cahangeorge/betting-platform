<script lang="ts">
	import { onMount } from 'svelte';
	import { Activity, CalendarClock, RefreshCw } from 'lucide-svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import ScheduledJobRunTable from '$lib/components/jobs/ScheduledJobRunTable.svelte';
	import WorkflowHeader from '$lib/components/WorkflowHeader.svelte';
	import { jobsApi } from '$lib/api/jobs';
	import { dataApi } from '$lib/api/data';
	import { countFinalScoreConflicts, finalScoreConflictPolicyMessage } from '$lib/result-refresh.helpers';
	import type { JobStatus, ScheduledJob } from '$lib/types';

	let jobs = $state<ScheduledJob[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let togglingId = $state<number | null>(null);
	let resultRefreshPolicies = $state<{ jobId: number; status: JobStatus; message: string }[]>([]);
	let resultRefreshPoliciesError = $state('');

	async function loadResultRefreshPolicies() {
		resultRefreshPoliciesError = '';
		try {
			const refreshJobs = (await dataApi.getJobs())
				.filter((job) => job.job_type === 'refresh_results' || job.params?.result_refresh === true)
				.sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())
				.slice(0, 5);
			const policies = await Promise.all(
				refreshJobs.map(async (job) => {
					if (job.status !== 'completed') {
						return { jobId: job.id, status: job.status, message: finalScoreConflictPolicyMessage({ status: job.status }) };
					}
					try {
						const logs = await dataApi.getJobLogs(job.id);
						return {
							jobId: job.id,
							status: job.status,
							message: finalScoreConflictPolicyMessage({
								status: job.status,
								conflictCount: countFinalScoreConflicts(logs.items),
								logsAvailable: true
							})
						};
					} catch {
						return {
							jobId: job.id,
							status: job.status,
							message: finalScoreConflictPolicyMessage({ status: job.status, logsAvailable: false })
						};
					}
				})
			);
			resultRefreshPolicies = policies;
		} catch (cause) {
			resultRefreshPolicies = [];
			resultRefreshPoliciesError = cause instanceof Error ? cause.message : 'Could not load final-score refresh status.';
		}
	}

	async function loadJobs() {
		loading = true;
		error = null;
		try { jobs = await jobsApi.getScheduledJobs(); await loadResultRefreshPolicies(); } catch (cause) { error = cause instanceof Error ? cause.message : 'Could not load monitoring data.'; } finally { loading = false; }
	}

	async function toggle(job: ScheduledJob) {
		togglingId = job.id;
		try { const updated = await jobsApi.toggleJob(job.id); jobs = jobs.map((item) => item.id === updated.id ? updated : item); } catch (cause) { error = cause instanceof Error ? cause.message : 'Could not update this schedule.'; } finally { togglingId = null; }
	}

	function formatSchedule(value: string | null): string { return value ? new Date(value).toLocaleString() : 'Not scheduled'; }

	onMount(() => { void loadJobs(); });
</script>

<svelte:head><title>Monitoring · Betfront</title></svelte:head>

<section class="workbench-page">
	<WorkflowHeader eyebrow="Step 4 of 4" title="Monitoring and automation" description="Manage scheduled work in one place. Keep the execution flow focused; return here for schedules, run history, and operational follow-up.">
		{#snippet actions()}<Button variant="secondary" onclick={loadJobs} disabled={loading}><RefreshCw class="mr-2 h-4 w-4" />Refresh</Button>{/snippet}
	</WorkflowHeader>
	<Card class="workbench-surface">
		<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
			<div>
				<h2 class="font-semibold text-foreground">Refresh final results</h2>
				<p class="mt-1 text-sm text-muted-foreground">Queue a targeted source refresh from Tickets. It tracks the selected open-ticket matches as a scrape job, then you can verify and settle only after it completes.</p>
			</div>
			<a class="text-sm font-medium text-primary hover:underline" href="/tickets">Open Tickets</a>
		</div>
	</Card>
	<Card class="workbench-surface">
		<h2 class="font-semibold text-foreground">Final-score conflict policy</h2>
		<p class="mt-1 text-sm text-muted-foreground">When a completed-score conflict is recorded in a refresh job log, the existing final score is retained. This interface does not apply score corrections; a dedicated audited correction endpoint is still required.</p>
		{#if resultRefreshPoliciesError}
			<p class="mt-3 text-xs text-muted-foreground">Could not inspect result-refresh jobs: {resultRefreshPoliciesError}</p>
		{:else if resultRefreshPolicies.length === 0}
			<p class="mt-3 text-xs text-muted-foreground">No result-refresh jobs are available to inspect yet.</p>
		{:else}
			<ul class="mt-3 space-y-2 text-xs text-muted-foreground">
				{#each resultRefreshPolicies as policy (policy.jobId)}
					<li><span class="font-mono text-foreground">Job #{policy.jobId}</span> · {policy.message}</li>
				{/each}
			</ul>
		{/if}
	</Card>
	{#if error}<div class="border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">{error}</div>{/if}
	{#if loading}<Card class="workbench-surface"><p class="text-sm text-muted-foreground">Loading schedules…</p></Card>
	{:else if jobs.length === 0}<Card class="workbench-surface"><div class="flex items-start gap-3"><CalendarClock class="mt-0.5 h-5 w-5 text-muted-foreground" /><div><h2 class="font-semibold text-foreground">No schedules yet</h2><p class="mt-1 text-sm text-muted-foreground">Create a schedule from the data preparation, analysis, or tickets workspace when you are ready to automate a repeated task.</p></div></div></Card>
	{:else}
		<div class="grid gap-4 lg:grid-cols-2">{#each jobs as job (job.id)}<Card class="workbench-surface"><div class="flex items-start justify-between gap-4"><div><div class="flex items-center gap-2"><Activity class="h-4 w-4 {job.enabled ? 'text-primary' : 'text-muted-foreground'}" /><h2 class="font-semibold text-foreground">{job.name}</h2></div><p class="mt-2 text-xs uppercase tracking-wide text-muted-foreground">{job.task_type} · {job.cron_expression}</p></div><Button variant={job.enabled ? 'secondary' : 'primary'} size="sm" disabled={togglingId === job.id} onclick={() => toggle(job)}>{job.enabled ? 'Pause' : 'Resume'}</Button></div><dl class="mt-5 grid grid-cols-2 gap-3 border-t border-border pt-4 text-sm"><div><dt class="text-xs text-muted-foreground">Last run</dt><dd class="mt-1 text-foreground">{formatSchedule(job.last_run)}</dd></div><div><dt class="text-xs text-muted-foreground">Next run</dt><dd class="mt-1 text-foreground">{formatSchedule(job.next_run)}</dd></div></dl></Card>{/each}</div>
		<ScheduledJobRunTable {jobs} title="Recent automation runs" />
	{/if}
</section>
