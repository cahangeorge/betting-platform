import type { PageServerLoad } from './$types';
import { redirect } from '@sveltejs/kit';
import { createBackendPageLoader, summarizeBackendLoad } from '$lib/server/backend-load';
import type { Bankroll, BookmakerAccount, LedgerEntry } from '$lib/types';

export const load: PageServerLoad = async ({ cookies, fetch }) => {
	const token = cookies.get('access_token');
	if (!token) {
		redirect(302, '/login');
	}

	const apiBase = process.env.BET_API_URL || 'http://localhost:8001';
	const { fetchJson } = createBackendPageLoader(apiBase, token, fetch);
	const bankrollsResult = await fetchJson<Bankroll[]>('/bankroll', [], 'bankrolls');
	const primaryBankrollId = bankrollsResult.data[0]?.id;

	const [accountsResult, ledgerResult] = primaryBankrollId
		? await Promise.all([
				fetchJson<BookmakerAccount[]>(`/bankroll/${primaryBankrollId}/accounts`, [], 'bookmaker accounts'),
				fetchJson<LedgerEntry[]>(`/bankroll/${primaryBankrollId}/ledger`, [], 'ledger')
			])
		: [
				{ data: [] as BookmakerAccount[], ok: true, endpointLabel: 'bookmaker accounts' },
				{ data: [] as LedgerEntry[], ok: true, endpointLabel: 'ledger' }
			];

	return {
		bankrolls: bankrollsResult.data,
		accounts: accountsResult.data,
		ledger: ledgerResult.data,
		backendStatus: summarizeBackendLoad([bankrollsResult, accountsResult, ledgerResult])
	};
};
