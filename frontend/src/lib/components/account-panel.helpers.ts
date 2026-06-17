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
