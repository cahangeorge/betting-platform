import { ApiClient } from './client';
import type { Match, MatchFilter, PaginatedResponse } from '$lib/types';

type MatchListResponse = {
	matches: Match[];
	total: number;
	page: number;
	per_page: number;
};

type LiveOverviewQuery = {
	status?: string;
	league?: string;
	max_matches?: number;
	min_live_value_edge?: number;
	include_live_value?: boolean;
};

type LiveMatchListResponse = {
	matches: Match[];
	source: string;
	is_demo: boolean;
	generated_at: string;
	data_age_seconds: number | null;
	is_data_stale: boolean;
	jobs_active: number;
};

type LiveHeartbeatResponse = {
	schema_version: string;
	jobs_active: number;
	bridge_ready: boolean;
	bridge_issues: string[];
	timestamp: string;
	last_success: string | null;
	source: string;
};

class MatchesApi extends ApiClient {
	async getMatches(filter?: MatchFilter): Promise<Match[]> {
		const response = await this.getMatchesPage(filter);
		return response.items;
	}

	async getMatchesPage(filter?: MatchFilter): Promise<PaginatedResponse<Match>> {
		const params = new URLSearchParams();
		if (filter?.league) params.set('league', filter.league);
		if (filter?.status) params.set('status', filter.status);
		if (filter?.date_from) params.set('date_from', filter.date_from);
		if (filter?.date_to) params.set('date_to', filter.date_to);
		if (filter?.page !== undefined) params.set('page', String(filter.page));
		if (filter?.per_page !== undefined) params.set('per_page', String(filter.per_page));
		const qs = params.toString();
		const response = await this.get<MatchListResponse>(`/api/v1/matches${qs ? `?${qs}` : ''}`);
		return {
			items: response.matches ?? [],
			total: response.total ?? 0,
			page: response.page ?? filter?.page ?? 1,
			per_page: response.per_page ?? filter?.per_page ?? 50
		};
	}

	async getMatch(id: number): Promise<Match> {
		return this.get<Match>(`/api/v1/matches/${id}`);
	}

	async getOdds(matchId: number): Promise<Match['odds']> {
		return this.get<Match['odds']>(`/api/v1/matches/${matchId}/odds`);
	}

	async getLeagues(): Promise<string[]> {
		// Backend doesn't have a dedicated leagues endpoint yet
		return [];
	}

	async getLiveOverview(fetchFn?: typeof fetch, query?: LiveOverviewQuery): Promise<LiveMatchListResponse> {
		const params = new URLSearchParams();
		if (query?.status) params.set('status', query.status);
		if (query?.league) params.set('league', query.league);
		if (query?.max_matches !== undefined) params.set('max_matches', String(query.max_matches));
		if (query?.min_live_value_edge !== undefined) params.set('min_live_value_edge', String(query.min_live_value_edge));
		if (query?.include_live_value !== undefined) params.set('include_live_value', String(query.include_live_value));
		const qs = params.toString();
		return this.get<LiveMatchListResponse>(`/api/v1/live/overview${qs ? `?${qs}` : ''}`, undefined, fetchFn);
	}

	async getLiveHeartbeat(fetchFn?: typeof fetch): Promise<LiveHeartbeatResponse> {
		return this.get<LiveHeartbeatResponse>('/api/v1/live/heartbeat', undefined, fetchFn);
	}
}

export const matchesApi = new MatchesApi();
