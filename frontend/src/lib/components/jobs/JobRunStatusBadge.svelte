<script lang="ts">
	import { jobRunStatusTone, normalizeJobRunStatus } from '$lib/job-runs.helpers';
	import type { ScheduledJobRunStatus } from '$lib/types';

	let { status }: { status: ScheduledJobRunStatus | null | undefined } = $props();

	const normalized = $derived(normalizeJobRunStatus(status));
	const tone = $derived(jobRunStatusTone(status));
</script>

<span class={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide badge-${tone}`}>
	{normalized}
</span>

<style>
	.badge-success {
		background: rgba(34, 197, 94, 0.14);
		color: rgb(74, 222, 128);
	}
	.badge-warning {
		background: rgba(245, 158, 11, 0.14);
		color: rgb(251, 191, 36);
	}
	.badge-danger {
		background: rgba(239, 68, 68, 0.14);
		color: rgb(248, 113, 113);
	}
	.badge-info {
		background: rgba(59, 130, 246, 0.14);
		color: rgb(96, 165, 250);
	}
	.badge-muted {
		background: rgba(148, 163, 184, 0.14);
		color: rgb(203, 213, 225);
	}
</style>
