import type { Match } from '../../lib/types';

type MatchListResponse = {
	matches?: Match[];
};

export async function loadBoardMatches(fetchFn: typeof fetch): Promise<Match[]> {
	const response = await fetchFn('/api/v1/matches');
	if (!response.ok) {
		throw new Error(`Failed to load matches: ${response.status}`);
	}

	const payload = (await response.json()) as MatchListResponse;
	return payload.matches ?? [];
}
