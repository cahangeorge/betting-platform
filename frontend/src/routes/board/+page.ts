import type { PageLoad } from './$types';
import type { Match } from '$lib/types';
import { loadBoardMatches } from './load-matches';

export const load: PageLoad = async ({ fetch }): Promise<{ matches: Match[] }> => {
	try {
		const matches = await loadBoardMatches(fetch);
		return { matches };
	} catch {
		return { matches: [] };
	}
};
