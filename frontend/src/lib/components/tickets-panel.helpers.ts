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
