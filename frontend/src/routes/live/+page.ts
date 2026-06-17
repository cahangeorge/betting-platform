import type { PageLoad } from './$types';
import { matchesApi } from '$lib/api/matches';

type LiveStatusFilter = 'All' | 'Live' | 'Halftime' | 'Finished';

const parseStatusFilter = (value: string | null): LiveStatusFilter => {
	if (!value?.trim()) {
		return 'Live';
	}

	switch (value.toLowerCase().trim()) {
		case 'live':
		case 'running':
		case 'in_play':
		case 'active':
			return 'Live';
		case 'halftime':
		case 'ht':
			return 'Halftime';
		case 'finished':
		case 'ft':
		case 'fulltime':
			return 'Finished';
		case 'all':
			return 'All';
		default:
			return 'Live';
	}
};

const parseLeagueFilter = (value: string | null): string => {
	if (!value?.trim()) {
		return 'All';
	}
	return value.trim();
};

const toBackendStatus = (status: LiveStatusFilter): 'all' | 'live' | 'halftime' | 'finished' => {
	switch (status) {
		case 'Live':
			return 'live';
		case 'Halftime':
			return 'halftime';
		case 'Finished':
			return 'finished';
		default:
			return 'all';
	}
};

const parseMinLiveValueEdge = (value: string | null): number => {
	if (!value?.trim()) {
		return 1;
	}
	const parsed = Number(value);
	if (!Number.isFinite(parsed)) {
		return 1;
	}
	return parsed;
};

export const load: PageLoad = async ({ url, fetch }) => {
	const statusFilter = parseStatusFilter(url.searchParams.get('status'));
	const selectedLeague = parseLeagueFilter(url.searchParams.get('league'));
	const minLiveValueEdge = parseMinLiveValueEdge(url.searchParams.get('min_live_value_edge'));

	try {
		const [response, heartbeat] = await Promise.all([
			matchesApi.getLiveOverview(fetch, {
				status: toBackendStatus(statusFilter),
				league: selectedLeague === 'All' ? undefined : selectedLeague,
				min_live_value_edge: minLiveValueEdge
			}),
			matchesApi.getLiveHeartbeat(fetch).catch((err) => {
				console.error('Live heartbeat unavailable:', err);
				return null;
			})
		]);
		const heartbeatData = heartbeat === null ? null : heartbeat;
		return {
			matches: response.matches,
				source: response.source,
				statusFilter,
				selectedLeague,
				isDemo: response.is_demo || !(heartbeatData?.bridge_ready ?? true),
				generatedAt: response.generated_at,
			dataAgeSeconds: response.data_age_seconds,
			isDataStale: response.is_data_stale,
			jobsActive: heartbeatData ? heartbeatData.jobs_active : response.jobs_active,
			bridgeReady: heartbeatData?.bridge_ready ?? true,
			bridgeIssues: heartbeatData?.bridge_issues ?? [],
			heartbeatAt: heartbeatData?.timestamp ?? response.generated_at,
			minLiveValueEdge,
			loading: false,
			error: null,
			lastUpdated: response.generated_at
		};
	} catch (error) {
		return {
			matches: [],
				source: 'cache',
				statusFilter,
				selectedLeague,
				isDemo: true,
			generatedAt: new Date().toISOString(),
			dataAgeSeconds: null,
			isDataStale: true,
			jobsActive: 0,
			bridgeReady: false,
			bridgeIssues: ['Failed to load live heartbeat'],
			heartbeatAt: new Date().toISOString(),
			minLiveValueEdge,
			loading: false,
			error: error instanceof Error ? error.message : 'Failed to load live matches.',
			lastUpdated: new Date().toISOString()
		};
	}
};
