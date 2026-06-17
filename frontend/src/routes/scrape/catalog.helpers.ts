import type { LeagueInfo } from '$lib/types';

export function isLeagueScrapeSelectable(league: Pick<LeagueInfo, 'scrape_slug'>): boolean {
	return typeof league.scrape_slug === 'string' && league.scrape_slug.length > 0;
}

export function buildScrapeLeagueSlugs(
	leagues: Pick<LeagueInfo, 'id' | 'scrape_slug'>[],
	selectedLeagueIds: string[]
): string[] {
	const selectedIds = new Set(selectedLeagueIds);

	return leagues
		.filter((league) => selectedIds.has(league.id))
		.map((league) => league.scrape_slug)
		.filter((slug): slug is string => typeof slug === 'string' && slug.length > 0);
}
