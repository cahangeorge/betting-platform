<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { Activity, CalendarClock, CircleAlert, DatabaseZap, RefreshCw, ServerCog, TrendingUp } from 'lucide-svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import ScheduledJobRunTable from '$lib/components/jobs/ScheduledJobRunTable.svelte';
	import WorkflowHeader from '$lib/components/WorkflowHeader.svelte';
	import { jobsApi } from '$lib/api/jobs';
	import { dataApi } from '$lib/api/data';
	import { analyticsApi, type ClvReport } from '$lib/api/analytics';
	import { providerRuntimeApi } from '$lib/api/provider-runtime';
	import { countFinalScoreConflicts, finalScoreConflictPolicyMessage } from '$lib/result-refresh.helpers';
	import type { JobStatus, ProviderRuntimeSnapshot, ProviderRuntimeSource, ScheduledJob } from '$lib/types';

	let jobs = $state<ScheduledJob[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let togglingId = $state<number | null>(null);
	let resultRefreshPolicies = $state<{ jobId: number; status: JobStatus; message: string }[]>([]);
	let resultRefreshPoliciesError = $state('');
	let clvReport = $state<ClvReport | null>(null);
	let clvError = $state('');
	let providerRuntime = $state<ProviderRuntimeSnapshot | null>(null);
	let providerRuntimeError = $state('');
	let providerRuntimeLoading = $state(true);
	const isAdmin = $derived(Boolean($page.data.user?.is_admin));

	function formatMetric(value: number | null, suffix = '%'): string {
		return value === null ? '—' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}${suffix}`;
	}

	async function loadClv() {
		clvError = '';
		try {
			clvReport = await analyticsApi.getClv();
		} catch (cause) {
			clvReport = null;
			clvError = cause instanceof Error ? cause.message : 'Could not load CLV evidence.';
		}
	}

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

	async function loadProviderRuntime() {
		providerRuntimeLoading = true;
		providerRuntimeError = '';
		try {
			providerRuntime = await providerRuntimeApi.getSnapshot();
		} catch {
			providerRuntime = null;
			providerRuntimeError = 'Could not load the redacted provider runtime snapshot.';
		} finally {
			providerRuntimeLoading = false;
		}
	}

	async function loadJobs() {
		loading = true;
		error = null;
		try { jobs = await jobsApi.getScheduledJobs(); await Promise.all([loadResultRefreshPolicies(), loadClv()]); } catch (cause) { error = cause instanceof Error ? cause.message : 'Could not load monitoring data.'; } finally { loading = false; }
	}

	async function refreshMonitoring() {
		if (!isAdmin) {
			providerRuntime = null;
			providerRuntimeError = '';
			providerRuntimeLoading = false;
			await loadJobs();
			return;
		}
		await Promise.all([loadJobs(), loadProviderRuntime()]);
	}

	async function toggle(job: ScheduledJob) {
		togglingId = job.id;
		try { const updated = await jobsApi.toggleJob(job.id); jobs = jobs.map((item) => item.id === updated.id ? updated : item); } catch (cause) { error = cause instanceof Error ? cause.message : 'Could not update this schedule.'; } finally { togglingId = null; }
	}

	function formatSchedule(value: string | null): string { return value ? new Date(value).toLocaleString() : 'Not scheduled'; }
	function formatQueueAge(milliseconds: number): string {
		if (milliseconds < 1_000) return `${milliseconds} ms`;
		if (milliseconds < 60_000) return `${(milliseconds / 1_000).toFixed(1)} s`;
		return `${(milliseconds / 60_000).toFixed(1)} min`;
	}
	function providerStateVariant(state: string): 'success' | 'warning' | 'danger' | 'neutral' {
		return state === 'closed' ? 'success' : state === 'half_open' ? 'warning' : state === 'unknown' ? 'neutral' : 'danger';
	}
	function alertVariant(severity: string): 'warning' | 'danger' {
		return severity === 'critical' ? 'danger' : 'warning';
	}
	function phaseVariant(status: string): 'success' | 'warning' | 'danger' | 'neutral' {
		if (status === 'running') return 'success';
		if (status === 'queued') return 'warning';
		if (status === 'attention') return 'danger';
		return 'neutral';
	}
	function freshnessVariant(state: ProviderRuntimeSource['freshness_state']): 'success' | 'warning' | 'danger' | 'neutral' {
		if (state === 'fresh') return 'success';
		if (state === 'stale') return 'danger';
		if (state === 'no_data') return 'warning';
		return 'neutral';
	}
	function cacheVariant(state: ProviderRuntimeSource['cache_state']): 'success' | 'warning' | 'neutral' {
		if (state === 'hit') return 'success';
		if (state === 'miss' || state === 'mixed') return 'warning';
		return 'neutral';
	}

	onMount(() => { void refreshMonitoring(); });
</script>

<svelte:head><title>Monitoring · Betfront</title></svelte:head>

<section class="workbench-page">
	<WorkflowHeader eyebrow="Step 4 of 4" title="Monitoring and automation" description="Manage scheduled work in one place. Keep the execution flow focused; return here for schedules, run history, and operational follow-up.">
		{#snippet actions()}<Button variant="secondary" onclick={refreshMonitoring} disabled={loading || providerRuntimeLoading}><RefreshCw class="mr-2 h-4 w-4" />Refresh</Button>{/snippet}
	</WorkflowHeader>
	{#if isAdmin}
		<Card class="workbench-surface" data-testid="provider-runtime-panel">
		<div class="flex items-start gap-3">
			<ServerCog class="mt-0.5 size-5 text-primary" aria-hidden="true" />
			<div class="min-w-0 flex-1">
				<h2 class="font-semibold text-foreground">Provider runtime</h2>
				<p class="mt-1 text-sm text-muted-foreground">Source-scoped health, quota accounting and lane pressure. Credentials, upstream payloads and raw provider errors are never shown here.</p>
			</div>
		</div>
		{#if providerRuntimeLoading}
			<p class="mt-4 text-sm text-muted-foreground" role="status" aria-live="polite">Loading provider runtime…</p>
		{:else if providerRuntimeError}
			<p class="mt-4 text-sm text-muted-foreground" role="alert">{providerRuntimeError}</p>
		{:else if providerRuntime}
			<div class="mt-4 border-b border-border pb-5" data-testid="provider-pipeline-phases">
				<div class="flex items-center gap-2"><Activity class="size-4 text-primary" aria-hidden="true" /><h3 class="font-medium text-foreground">Pipeline progress</h3></div>
				<p class="mt-1 text-sm text-muted-foreground">Aggregate, provider-agnostic progress across the governed data path.</p>
				<div class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
					{#each providerRuntime.phases as phase (phase.phase)}
						<div class="border border-border p-3" data-testid="provider-phase-card">
							<div class="flex items-center justify-between gap-2"><h4 class="font-medium capitalize text-foreground">{phase.phase}</h4><Badge variant={phaseVariant(phase.status)}>{phase.status}</Badge></div>
							<dl class="mt-3 grid grid-cols-2 gap-2 text-xs"><div><dt class="text-muted-foreground">Queued</dt><dd class="mt-1 font-mono text-foreground">{phase.queued}</dd></div><div><dt class="text-muted-foreground">Running</dt><dd class="mt-1 font-mono text-foreground">{phase.running}</dd></div><div><dt class="text-muted-foreground">Failed / partial</dt><dd class="mt-1 font-mono text-foreground">{phase.failed} / {phase.partial}</dd></div><div><dt class="text-muted-foreground">Attention</dt><dd class="mt-1 font-mono text-foreground">{phase.attention_count}</dd></div></dl>
						</div>
					{:else}
						<p class="text-sm text-muted-foreground">No pipeline progress is available yet.</p>
					{/each}
				</div>
			</div>
			<div class="mt-4 grid gap-3 lg:grid-cols-2">
				{#each providerRuntime.sources as source (`${source.adapter_key}:${source.source_key}`)}
					<div class="border border-border p-3" data-testid="provider-source-card">
						<div class="flex items-start justify-between gap-3">
							<div><h3 class="font-medium text-foreground">{source.adapter_key} · {source.source_key}</h3><p class="mt-1 text-xs text-muted-foreground">Generic source runtime</p></div>
							<div class="flex flex-wrap justify-end gap-2"><Badge variant={cacheVariant(source.cache_state)}>cache {source.cache_state.replace('_', ' ')}</Badge><Badge variant={freshnessVariant(source.freshness_state)}>{source.freshness_state.replace('_', ' ')}</Badge><Badge variant={providerStateVariant(source.circuit_state)}>{source.circuit_state.replace('_', ' ')}</Badge></div>
						</div>
						<dl class="mt-3 grid grid-cols-2 gap-2 text-xs"><div><dt class="text-muted-foreground">Coverage</dt><dd class="mt-1 font-mono text-foreground">{source.coverage_percent.toFixed(1)}%</dd></div><div><dt class="text-muted-foreground">Complete / partial</dt><dd class="mt-1 font-mono text-foreground">{source.complete_snapshot_count} / {source.partial_snapshot_count}</dd></div><div><dt class="text-muted-foreground">Unmapped</dt><dd class="mt-1 font-mono text-foreground">{source.unmapped_observation_count}</dd></div><div><dt class="text-muted-foreground">Latest observation</dt><dd class="mt-1 text-foreground">{formatSchedule(source.latest_observed_at)}</dd></div><div><dt class="text-muted-foreground">Quota used</dt><dd class="mt-1 font-mono text-foreground">{source.quota_consumed}{source.quota_limit === null ? '' : ` / ${source.quota_limit}`}</dd></div><div><dt class="text-muted-foreground">Reserved</dt><dd class="mt-1 font-mono text-foreground">{source.quota_reserved}</dd></div><div><dt class="text-muted-foreground">Failures</dt><dd class="mt-1 font-mono text-foreground">{source.consecutive_failures}</dd></div><div><dt class="text-muted-foreground">Reconciled</dt><dd class="mt-1 text-foreground">{formatSchedule(source.last_reconciled_at)}</dd></div></dl>
					</div>
				{:else}
					<p class="text-sm text-muted-foreground">No provider sources have emitted runtime state yet.</p>
				{/each}
			</div>
			<div class="mt-5 border-t border-border pt-4">
				<div class="flex items-center gap-2"><DatabaseZap class="size-4 text-primary" aria-hidden="true" /><h3 class="font-medium text-foreground">Worker lanes</h3></div>
				<div class="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
					{#each providerRuntime.lanes as lane (lane.lane)}
						<div class="border border-border p-3" data-testid="provider-lane-card"><p class="font-mono text-sm text-foreground">{lane.lane}</p><dl class="mt-2 grid grid-cols-2 gap-2 text-xs"><div><dt class="text-muted-foreground">Queued</dt><dd class="font-mono text-foreground">{lane.queued}</dd></div><div><dt class="text-muted-foreground">Running</dt><dd class="font-mono text-foreground">{lane.running}</dd></div><div><dt class="text-muted-foreground">Oldest wait</dt><dd class="font-mono text-foreground">{formatQueueAge(lane.oldest_queue_age_ms)}</dd></div><div><dt class="text-muted-foreground">Freshness</dt><dd class="font-mono text-foreground">{lane.freshness_failures} failed</dd></div></dl></div>
					{:else}
						<p class="text-sm text-muted-foreground">No worker lane snapshot is available yet.</p>
					{/each}
				</div>
			</div>
			<div class="mt-5 border-t border-border pt-4" data-testid="provider-runtime-alerts">
				<div class="flex items-center gap-2"><CircleAlert class="size-4 text-primary" aria-hidden="true" /><h3 class="font-medium text-foreground">Active alerts</h3></div>
				{#if providerRuntime.alerts.length === 0}<p class="mt-2 text-sm text-muted-foreground">No active runtime alerts.</p>
				{:else}<ul class="mt-3 space-y-2">{#each providerRuntime.alerts as alert (`${alert.scope}:${alert.scope_key}:${alert.code}`)}<li class="flex items-center justify-between gap-3 border border-border p-2 text-sm"><span class="min-w-0 text-foreground">{alert.scope_key} · {alert.code.replaceAll('_', ' ')}</span><Badge variant={alertVariant(alert.severity)}>{alert.severity}</Badge></li>{/each}</ul>{/if}
			</div>
		{/if}
		</Card>
	{/if}
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
		<div class="flex items-start gap-3">
			<TrendingUp class="mt-0.5 size-5 text-primary" />
			<div class="min-w-0 flex-1">
				<h2 class="font-semibold text-foreground">Closing line value</h2>
				<p class="mt-1 text-sm text-muted-foreground">Cota lipsă rămâne lipsă. Coverage-ul arată cât din istoric are dovadă reală la închidere.</p>
			</div>
		</div>
		{#if clvError}
			<p class="mt-4 text-sm text-muted-foreground">{clvError}</p>
		{:else if clvReport}
			<div class="mt-4 grid gap-3 sm:grid-cols-3">
				<div class="border border-border p-3"><p class="text-xs text-muted-foreground">Same-book average</p><p class="mt-1 font-mono text-lg">{formatMetric(clvReport.summary.average_same_book_clv_pct)}</p><p class="text-xs text-muted-foreground">Coverage {clvReport.summary.same_book_coverage_pct.toFixed(1)}%</p></div>
				<div class="border border-border p-3"><p class="text-xs text-muted-foreground">Market-best average</p><p class="mt-1 font-mono text-lg">{formatMetric(clvReport.summary.average_market_best_clv_pct)}</p><p class="text-xs text-muted-foreground">Coverage {clvReport.summary.market_best_coverage_pct.toFixed(1)}%</p></div>
				<div class="border border-border p-3"><p class="text-xs text-muted-foreground">Consensus shift</p><p class="mt-1 font-mono text-lg">{formatMetric(clvReport.summary.average_consensus_clv_pp, ' pp')}</p><p class="text-xs text-muted-foreground">Coverage {clvReport.summary.consensus_coverage_pct.toFixed(1)}%</p></div>
			</div>
		{/if}
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
