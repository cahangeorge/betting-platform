import test from 'node:test';
import assert from 'node:assert/strict';

import { loadBoardMatches } from '../../src/routes/board/load-matches.ts';

test('board load uses the SvelteKit fetch implementation for SSR match loading', async () => {
	const matches = await loadBoardMatches(async (input: RequestInfo | URL) => {
		assert.equal(String(input), '/api/v1/matches');
		return new Response(
			JSON.stringify({
				matches: [
					{
						id: 1,
						league: 'Test League',
						home_team: 'Alpha FC',
						away_team: 'Beta United',
						start_time: '2026-06-17T18:30:00+00:00',
						status: 'scheduled',
						home_score: null,
						away_score: null,
						odds: []
					}
				],
				total: 1,
				page: 1,
				per_page: 50
			}),
			{
				status: 200,
				headers: { 'content-type': 'application/json' }
			}
		);
	});

	assert.equal(matches.length, 1);
	assert.equal(matches[0].home_team, 'Alpha FC');
});
