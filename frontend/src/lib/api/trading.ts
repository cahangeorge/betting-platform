import { ApiClient } from './client';
import type { TradingAccount, TradingAccountHealth, TradingExecution } from '$lib/types';

class TradingApi extends ApiClient {
	async getAccounts(): Promise<TradingAccount[]> {
		return this.get<TradingAccount[]>('/api/v1/trading/accounts');
	}

	async createPaperAccount(data: { name: string; currency?: string; initial_balance: number }): Promise<TradingAccount> {
		return this.post<TradingAccount>('/api/v1/trading/accounts', data as Record<string, unknown>);
	}

	async getAccountHealth(accountId: number): Promise<TradingAccountHealth> {
		return this.get<TradingAccountHealth>(`/api/v1/trading/accounts/${accountId}/health`);
	}

	async executePaperTicket(accountId: number, ticketId: number, idempotencyKey: string): Promise<TradingExecution> {
		return this.post<TradingExecution>('/api/v1/trading/executions', {
			trading_account_id: accountId,
			ticket_id: ticketId,
			idempotency_key: idempotencyKey,
			side: 'BACK',
			order_type: 'LIMIT'
		});
	}

	async getExecution(executionId: number): Promise<TradingExecution> {
		return this.get<TradingExecution>(`/api/v1/trading/executions/${executionId}`);
	}

	async cancelExecution(executionId: number): Promise<TradingExecution> {
		return this.post<TradingExecution>(`/api/v1/trading/executions/${executionId}/cancel`);
	}
}

export const tradingApi = new TradingApi();
