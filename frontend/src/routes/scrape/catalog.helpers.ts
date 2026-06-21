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

export function formatLocalDate(date: Date): string {
	const year = date.getFullYear();
	const month = String(date.getMonth() + 1).padStart(2, '0');
	const day = String(date.getDate()).padStart(2, '0');
	return `${year}-${month}-${day}`;
}

export function buildHistoryDateRange(years: number, today = new Date()): { from: string; to: string } {
	const end = new Date(today);
	const start = new Date(today);
	start.setFullYear(start.getFullYear() - years);
	return {
		from: formatLocalDate(start),
		to: formatLocalDate(end)
	};
}

export function buildFootballSeasonsFromDateRange(from: string, to: string): string[] {
	if (!from || !to) return [];

	const start = new Date(`${from}T00:00:00`);
	const end = new Date(`${to}T00:00:00`);
	if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) return [];

	const seasons: string[] = [];
	const startSeasonYear = start.getMonth() >= 6 ? start.getFullYear() : start.getFullYear() - 1;
	const endSeasonYear = end.getMonth() >= 6 ? end.getFullYear() : end.getFullYear() - 1;

	for (let year = endSeasonYear; year >= startSeasonYear; year -= 1) {
		seasons.push(`${year}-${year + 1}`);
	}

	return seasons;
}

export function buildWorldCupSeasonsFromDateRange(from: string, to: string): string[] {
	if (!from || !to) return [];

	const startYear = new Date(`${from}T00:00:00`).getFullYear();
	const endYear = new Date(`${to}T00:00:00`).getFullYear();
	if (Number.isNaN(startYear) || Number.isNaN(endYear) || startYear > endYear) return [];

	const seasons: string[] = [];
	for (let year = endYear - 1; year >= startYear; year -= 1) {
		if (year % 4 === 2) seasons.push(String(year));
	}
	return seasons;
}

export function buildHistoricSeasons(
	from: string,
	to: string,
	leagueSlugs: string[]
): string[] {
	if (leagueSlugs.length > 0 && leagueSlugs.every((slug) => slug === 'world-cup')) {
		return buildWorldCupSeasonsFromDateRange(from, to);
	}
	return buildFootballSeasonsFromDateRange(from, to);
}
