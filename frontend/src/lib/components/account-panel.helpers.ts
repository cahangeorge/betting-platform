export function shouldAutoLoadAccountData(input: {
	serverBankrolls?: unknown[];
	serverAccounts?: unknown[];
	serverLedger?: unknown[];
	hasRequestedInitialLoad: boolean;
}): boolean {
	if (input.hasRequestedInitialLoad) {
		return false;
	}

	return (
		input.serverBankrolls === undefined ||
		input.serverAccounts === undefined ||
		input.serverLedger === undefined
	);
}

export function parseBankrollId(value: string | number | null | undefined): number | null {
	if (value === null || value === undefined || value === '') return null;
	const parsed = typeof value === 'number' ? value : Number(value);
	return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}
