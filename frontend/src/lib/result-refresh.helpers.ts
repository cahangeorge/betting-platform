import type { JobStatus, ScrapeJobLogEntry } from '$lib/types';

export function countFinalScoreConflicts(logs: Pick<ScrapeJobLogEntry, 'action'>[]): number {
	return logs.filter((log) => log.action === 'final_score_conflict').length;
}

export function finalScoreConflictPolicyMessage(input: {
	status: JobStatus | string;
	conflictCount?: number;
	logsAvailable?: boolean;
}): string {
	const correctionPolicy = 'Corrections require a dedicated audited endpoint and are not available here.';

	if (input.status === 'completed') {
		if (input.logsAvailable === false) {
			return `Refresh completed, but its conflict logs could not be read. ${correctionPolicy}`;
		}
		if ((input.conflictCount ?? 0) > 0) {
			return `${input.conflictCount} final-score conflict${input.conflictCount === 1 ? '' : 's'} recorded; persisted final scores were retained. ${correctionPolicy}`;
		}
		return `No final-score conflicts are recorded for this completed refresh. ${correctionPolicy}`;
	}

	if (input.status === 'failed' || input.status === 'cancelled') {
		return `Refresh ${input.status}; no final-score correction was applied. ${correctionPolicy}`;
	}

	return `Refresh is ${input.status}. Any conflicting final score is retained if this refresh reaches source data. ${correctionPolicy}`;
}
