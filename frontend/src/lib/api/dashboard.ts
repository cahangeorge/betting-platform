import { ApiClient } from './client';
import type {
	DashboardSummary,
	DashboardTicket,
	DashboardTicketOutcomeResponse,
	UpcomingMatch,
	JobLog
} from '$lib/types';

class DashboardApi extends ApiClient {
	async getSummary(): Promise<DashboardSummary> {
		return this.get<DashboardSummary>('/api/v1/dashboard/summary');
	}

	async getRecentTickets(params?: {
		limit?: number;
		date_from?: string;
		date_to?: string;
	}): Promise<DashboardTicket[]> {
		const sp = new URLSearchParams();
		if (params?.limit !== undefined) sp.set('limit', String(params.limit));
		if (params?.date_from) sp.set('date_from', params.date_from);
		if (params?.date_to) sp.set('date_to', params.date_to);
		const qs = sp.toString();
		return this.get<DashboardTicket[]>(`/api/v1/dashboard/recent-tickets${qs ? `?${qs}` : ''}`);
	}

	async getTicketOutcomes(range = '7d'): Promise<DashboardTicketOutcomeResponse> {
		return this.get<DashboardTicketOutcomeResponse>(
			`/api/v1/dashboard/ticket-outcomes?range=${encodeURIComponent(range)}`
		);
	}

	async getTicketOutcomeTickets(params: {
		date_from: string;
		date_to: string;
		limit?: number;
	}): Promise<DashboardTicket[]> {
		const sp = new URLSearchParams();
		sp.set('date_from', params.date_from);
		sp.set('date_to', params.date_to);
		if (params.limit !== undefined) sp.set('limit', String(params.limit));
		return this.get<DashboardTicket[]>(`/api/v1/dashboard/ticket-outcomes/tickets?${sp.toString()}`);
	}

	async getUpcoming(days?: number): Promise<UpcomingMatch[]> {
		const d = days || 7;
		return this.get<UpcomingMatch[]>(`/api/v1/dashboard/upcoming?days=${d}`);
	}

	async getJobLogs(limit?: number): Promise<JobLog[]> {
		const l = limit || 20;
		return this.get<JobLog[]>(`/api/v1/dashboard/job-logs?limit=${l}`);
	}
}

export const dashboardApi = new DashboardApi();
