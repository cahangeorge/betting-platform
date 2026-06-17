import { ApiClient } from './client';
import type {
	Bankroll,
	BankrollCreateRequest,
	BookmakerAccount,
	BookmakerAccountCreateRequest,
	LedgerEntry
} from '$lib/types';

class BankrollApi extends ApiClient {
	private async resolveBankrollId(bankrollId?: number): Promise<number | null> {
		if (bankrollId) {
			return bankrollId;
		}

		const bankrolls = await this.getBankrolls();
		return bankrolls[0]?.id ?? null;
	}

	async getBankrolls(): Promise<Bankroll[]> {
		return this.get<Bankroll[]>('/api/v1/bankroll');
	}

	async getBankroll(id: number): Promise<Bankroll> {
		return this.get<Bankroll>(`/api/v1/bankroll/${id}`);
	}

	async createBankroll(data: BankrollCreateRequest): Promise<Bankroll> {
		return this.post<Bankroll>('/api/v1/bankroll', data as unknown as Record<string, unknown>);
	}

	async deleteBankroll(id: number): Promise<void> {
		return this.del<void>(`/api/v1/bankroll/${id}`);
	}

	async getAccounts(bankrollId?: number): Promise<BookmakerAccount[]> {
		const bid = await this.resolveBankrollId(bankrollId);
		if (bid === null) {
			return [];
		}
		return this.get<BookmakerAccount[]>(`/api/v1/bankroll/${bid}/accounts`);
	}

	async createAccount(data: BookmakerAccountCreateRequest): Promise<BookmakerAccount> {
		return this.post<BookmakerAccount>(`/api/v1/bankroll/${data.bankroll_id}/accounts`, data as unknown as Record<string, unknown>);
	}

	async getLedger(bankrollId?: number): Promise<LedgerEntry[]> {
		const bid = await this.resolveBankrollId(bankrollId);
		if (bid === null) {
			return [];
		}
		return this.get<LedgerEntry[]>(`/api/v1/bankroll/${bid}/ledger`);
	}
}

export const bankrollApi = new BankrollApi();
