import { ApiClient } from './client';
import type { PnlPoint } from '$lib/types';

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
}

export const analyticsApi = new AnalyticsApi();
