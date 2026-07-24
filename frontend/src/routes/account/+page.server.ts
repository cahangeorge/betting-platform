import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';
import { redirect } from '@sveltejs/kit';
import { createBackendPageLoader, summarizeBackendLoad } from '$lib/server/backend-load';
import type { Bankroll, BookmakerAccount, LedgerEntry, TradingAccount } from '$lib/types';

export const load: PageServerLoad = async ({ cookies, fetch }) => {
	const token = cookies.get('access_token');
	if (!token) {
		redirect(302, '/login');
	}

	const apiBase = process.env.BET_API_URL || 'http://localhost:8001';
	const paperTradingEnabled = env.BET_TRADING_PAPER_ENABLED === 'true';
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
	const tradingAccountsResult = paperTradingEnabled
		? await fetchJson<TradingAccount[]>('/trading/accounts', [], 'paper trading accounts')
		: { data: [] as TradingAccount[], ok: true, endpointLabel: 'paper trading accounts' };

	return {
		bankrolls: bankrollsResult.data,
		accounts: accountsResult.data,
		ledger: ledgerResult.data,
		tradingAccounts: tradingAccountsResult.data,
		paperTradingEnabled,
		backendStatus: summarizeBackendLoad([bankrollsResult, accountsResult, ledgerResult, tradingAccountsResult])
	};
};
