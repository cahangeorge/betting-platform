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
		fetchJson('/matches', { matches: [] }, 'matches'),
		fetchJson('/tickets', [] as unknown[], 'tickets'),
		fetchJson('/predictions/runs', [] as unknown[], 'prediction runs')
	]);

	const matches = Array.isArray(matchesResult.data?.matches) ? matchesResult.data.matches : [];

	return {
		matches,
		tickets: ticketsResult.data,
		predictionRuns: predictionsResult.data,
		backendStatus: summarizeBackendLoad([matchesResult, ticketsResult, predictionsResult])
	};
};
