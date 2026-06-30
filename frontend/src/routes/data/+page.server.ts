import type { PageServerLoad } from './$types';
import { redirect } from '@sveltejs/kit';
import { createBackendPageLoader, summarizeBackendLoad } from '$lib/server/backend-load';

export const load: PageServerLoad = async ({ cookies, fetch }) => {
	const token = cookies.get('access_token');
	if (!token) {
		redirect(302, '/login');
	}

	const apiBase = process.env.BET_API_URL || 'http://localhost:8001';
	const { fetchJson } = createBackendPageLoader(apiBase, token, fetch);

	const [matchesResult, ticketsResult, predictionsResult] = await Promise.all([
		fetchJson('/matches?page=1&per_page=10', { matches: [], total: 0, page: 1, per_page: 10 }, 'matches'),
		fetchJson('/tickets/page?page=1&per_page=10', { items: [], total: 0, page: 1, per_page: 10 }, 'tickets'),
		fetchJson('/predictions/runs/page?page=1&per_page=10', { items: [], total: 0, page: 1, per_page: 10 }, 'prediction runs')
	]);

	const matches = Array.isArray(matchesResult.data?.matches) ? matchesResult.data.matches : [];
	const tickets = Array.isArray(ticketsResult.data?.items) ? ticketsResult.data.items : [];
	const predictionRuns = Array.isArray(predictionsResult.data?.items) ? predictionsResult.data.items : [];

	return {
		matches,
		matchesTotal: typeof matchesResult.data?.total === 'number' ? matchesResult.data.total : matches.length,
		tickets,
		ticketsTotal: typeof ticketsResult.data?.total === 'number' ? ticketsResult.data.total : tickets.length,
		predictionRuns,
		predictionRunsTotal:
			typeof predictionsResult.data?.total === 'number' ? predictionsResult.data.total : predictionRuns.length,
		backendStatus: summarizeBackendLoad([matchesResult, ticketsResult, predictionsResult])
	};
};
