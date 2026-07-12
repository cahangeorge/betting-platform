export function shouldAutoLoadTicketsData(input: {
	serverTickets?: unknown[];
	serverMatches?: unknown[];
	serverStats?: { total: number; won: number; lost: number; profit_loss: number };
	serverBankrolls?: unknown[];
	serverBatches?: unknown[];
	hasRequestedInitialLoad: boolean;
}): boolean {
	if (input.hasRequestedInitialLoad) {
		return false;
	}

	return (
		input.serverTickets === undefined ||
		input.serverMatches === undefined ||
		input.serverStats === undefined ||
		input.serverBankrolls === undefined ||
		input.serverBatches === undefined
	);
}

export function formatResultsRefreshQueuedMessage(input: {
	jobId: number;
	runId: number | null | undefined;
	matchCount: number;
}): string {
	const scope = input.matchCount === 1 ? '1 open-ticket match' : `${input.matchCount} open-ticket matches`;
	const run = input.runId ? ` (run #${input.runId})` : '';
	return `Queued final-results refresh job #${input.jobId}${run} for ${scope}. It has not refreshed scores or settled tickets yet.`;
}

export function verificationActionState(input: {
	settlementChecking: boolean;
	resultsRefreshing: boolean;
	watchingResultsRefresh: boolean;
}): { disabled: boolean; label: string } {
	if (input.settlementChecking) {
		return { disabled: true, label: 'Verifying and settling...' };
	}

	if (input.resultsRefreshing) {
		return { disabled: true, label: 'Refreshing final results...' };
	}

	if (input.watchingResultsRefresh) {
		return { disabled: true, label: 'Waiting for final-results refresh...' };
	}

	return { disabled: false, label: 'Verify and settle' };
}
