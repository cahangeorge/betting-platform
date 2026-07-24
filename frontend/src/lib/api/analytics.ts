import { ApiClient } from './client';
import type { PnlPoint } from '$lib/types';

export type ClvReport = {
	summary: {
		leg_count: number;
		same_book_coverage_pct: number;
		market_best_coverage_pct: number;
		consensus_coverage_pct: number;
		average_same_book_clv_pct: number | null;
		average_market_best_clv_pct: number | null;
		average_consensus_clv_pp: number | null;
		positive_same_book_pct: number | null;
		positive_market_best_pct: number | null;
		positive_consensus_pct: number | null;
	};
	items: Array<{
		ticket_id: number;
		ticket_leg_id: number;
		reference_stage: 'generation' | 'activation' | null;
		same_book_clv_pct: number | null;
		market_best_clv_pct: number | null;
		consensus_clv_pp: number | null;
		coverage: Record<string, boolean>;
		unavailable_reasons: Record<string, string[]>;
	}>;
};

class AnalyticsApi extends ApiClient {
	async getPnl(period?: string, group_by?: string): Promise<PnlPoint[]> {
		const p = period || '30d';
		const g = group_by || 'day';
		return this.get<PnlPoint[]>(`/api/v1/analytics/pnl?period=${p}&group_by=${g}`);
	}

	async getPnlByLeague(): Promise<
		{ league: string; pnl: number; bets: number; win_rate: number }[]
	> {
		return this.get('/api/v1/analytics/pnl/by-league');
	}

	async getPnlByModel(): Promise<
		{ model: string; pnl: number; bets: number; win_rate: number }[]
	> {
		return this.get('/api/v1/analytics/pnl/by-model');
	}

	async getEquityCurve(period?: string): Promise<
		{ date: string; balance: number }[]
	> {
		const p = period || '30d';
		return this.get(`/api/v1/analytics/equity-curve?period=${p}`);
	}

	async getClv(): Promise<ClvReport> {
		return this.get('/api/v1/analytics/clv');
	}
}

export const analyticsApi = new AnalyticsApi();
