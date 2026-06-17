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

	const [ticketsResult, matchesResult, statsResult] = await Promise.all([
		fetchJson('/tickets', [], 'tickets'),
		fetchJson('/matches?status=scheduled', { matches: [] }, 'scheduled matches'),
		fetchJson('/tickets/stats', { total: 0, won: 0, lost: 0, profit_loss: 0 }, 'ticket stats')
	]);

	return {
		tickets: ticketsResult.data,
		matches: matchesResult.data.matches ?? [],
		stats: statsResult.data,
		backendStatus: summarizeBackendLoad([ticketsResult, matchesResult, statsResult])
	};
};
