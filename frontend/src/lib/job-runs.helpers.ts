import type { ScheduledJobRun, ScheduledJobRunStatus } from '$lib/types';

const RUN_SORT_TIMESTAMPS = [
	'finished_at',
	'started_at',
	'queued_at',
	'created_at',
	'due_at'
] as const satisfies readonly (keyof ScheduledJobRun)[];

export function normalizeJobRunStatus(status: ScheduledJobRunStatus | null | undefined): ScheduledJobRunStatus {
	return status || 'pending';
}

export function jobRunStatusTone(
	status: ScheduledJobRunStatus | null | undefined
): 'success' | 'warning' | 'danger' | 'info' | 'muted' {
	switch (normalizeJobRunStatus(status)) {
		case 'completed':
			return 'success';
		case 'partial':
		case 'skipped':
			return 'warning';
		case 'failed':
		case 'enqueue_failed':
		case 'cancelled':
			return 'danger';
		case 'queued':
		case 'pending':
		case 'running':
			return 'info';
		default:
			return 'muted';
	}
}

export function jobRunSortTimestamp(run: ScheduledJobRun): number {
	for (const field of RUN_SORT_TIMESTAMPS) {
		const value = run[field];
		if (typeof value !== 'string' || value.length === 0) continue;
		const parsed = Date.parse(value);
		if (!Number.isNaN(parsed)) return parsed;
	}

	return 0;
}

export function formatRunDuration(run: ScheduledJobRun): string {
	if (typeof run.duration_ms === 'number') {
		if (run.duration_ms < 1000) return `${run.duration_ms}ms`;
		return `${(run.duration_ms / 1000).toFixed(1)}s`;
	}
	if (!run.started_at || !run.finished_at) return '—';
	const started = Date.parse(run.started_at);
	const finished = Date.parse(run.finished_at);
	if (Number.isNaN(started) || Number.isNaN(finished)) return '—';
	return `${Math.max(0, Math.round((finished - started) / 1000))}s`;
}

export function artifactSummary(run: ScheduledJobRun): string {
	const artifacts = run.artifacts || {};
	const parts: string[] = [];
	for (const key of ['scrape_job_ids', 'prediction_run_ids', 'ticket_ids', 'ticket_batch_ids']) {
		const value = artifacts[key];
		if (Array.isArray(value) && value.length > 0) {
			parts.push(`${key.replace(/_ids$/, '').replaceAll('_', ' ')}: ${value.join(', ')}`);
		}
	}
	return parts.join(' · ') || 'No artifacts yet';
}
