import type { CatalogResponse, Country, LeagueInfo } from '$lib/types';

export type CatalogAvailability = 'validated' | 'discovered' | 'unavailable' | null;

export type ScrapeCatalog = {
	countries: Country[];
	source: string | null;
	status: CatalogAvailability;
	lastRefreshedAt: string | null;
};

type CatalogMetadata = {
	source?: string | null;
	status?: string | null;
	last_refreshed_at?: string | null;
	last_seen_at?: string | null;
};

function isCatalogEnvelope(value: unknown): value is CatalogResponse {
	return (
		typeof value === 'object' &&
		value !== null &&
		'countries' in value &&
		Array.isArray((value as { countries?: unknown }).countries)
	);
}

/**
 * Normalise the original array payload and the dynamic catalog envelope into
 * one UI shape. This keeps existing deployments working while catalog refresh
 * metadata becomes available gradually.
 */
export function parseScrapeCatalog(value: unknown): ScrapeCatalog {
	if (Array.isArray(value)) {
		const countries = value as Country[];
		return { countries, ...getCatalogMetadataFromCountries(countries) };
	}

	if (!isCatalogEnvelope(value)) {
		return { countries: [], source: null, status: null, lastRefreshedAt: null };
	}

	const inferredMetadata = getCatalogMetadataFromCountries(value.countries);
	return {
		countries: value.countries,
		source: value.source ?? inferredMetadata.source,
		status: normaliseCatalogAvailability(value.status) ?? inferredMetadata.status,
		lastRefreshedAt: value.last_refreshed_at ?? inferredMetadata.lastRefreshedAt
	};
}

/** Parses optional catalog refresh metadata without making a missing endpoint fatal. */
export function parseCatalogMetadata(value: unknown): Omit<ScrapeCatalog, 'countries'> {
	if (typeof value !== 'object' || value === null) {
		return { source: null, status: null, lastRefreshedAt: null };
	}

	const metadata = value as CatalogMetadata;
	return {
		source: metadata.source ?? null,
		status: normaliseCatalogAvailability(metadata.status),
		lastRefreshedAt: metadata.last_refreshed_at ?? metadata.last_seen_at ?? null
	};
}

function getCatalogMetadataFromCountries(countries: Country[]): Omit<ScrapeCatalog, 'countries'> {
	const leagues = countries.flatMap((country) => country.leagues);
	const sources = new Set(leagues.map((league) => league.source).filter((source): source is string => Boolean(source)));
	const statuses = new Set(
		leagues
			.map(getLeagueCatalogAvailability)
			.filter((status): status is Exclude<CatalogAvailability, null> => status !== null)
	);
	const refreshTimes = leagues
		.map((league) => league.last_refreshed_at ?? league.last_seen_at)
		.filter((timestamp): timestamp is string => Boolean(timestamp))
		.sort();

	return {
		source: sources.size === 1 ? [...sources][0] : null,
		status: statuses.size === 1 ? [...statuses][0] : null,
		lastRefreshedAt: refreshTimes.at(-1) ?? null
	};
}

/** Dynamic catalog providers may use common status aliases; keep presentation stable. */
export function normaliseCatalogAvailability(status?: string | null): CatalogAvailability {
	switch (status?.trim().toLocaleLowerCase()) {
		case 'validated':
		case 'available':
		case 'ready':
			return 'validated';
		case 'discovered':
		case 'pending':
		case 'pending_validation':
		case 'validating':
			return 'discovered';
		case 'unavailable':
		case 'failed':
		case 'disabled':
			return 'unavailable';
		default:
			return null;
	}
}

export function getLeagueCatalogAvailability(league: Pick<LeagueInfo, 'status'>): CatalogAvailability {
	return normaliseCatalogAvailability(league.status);
}

export function catalogAvailabilityLabel(status: CatalogAvailability): string | null {
	switch (status) {
		case 'validated':
			return 'Ready to scrape';
		case 'discovered':
			return 'In validation';
		case 'unavailable':
			return 'Unavailable';
		default:
			return null;
	}
}

export function formatCatalogRefreshTime(timestamp?: string | null): string | null {
	if (!timestamp) return null;
	const date = new Date(timestamp);
	if (Number.isNaN(date.getTime())) return null;
	return new Intl.DateTimeFormat(undefined, {
		dateStyle: 'medium',
		timeStyle: 'short'
	}).format(date);
}

export const HISTORY_PRESET_OPTIONS = [
	{ value: '5', label: 'Last 5 years' },
	{ value: '10', label: 'Last 10 years' },
	{ value: '15', label: 'Last 15 years' },
	{ value: '20', label: 'Last 20 years' },
	{ value: '30', label: 'Last 30 years' },
	{ value: '40', label: 'Last 40 years' }
];

export function isLeagueScrapeSelectable(league: Pick<LeagueInfo, 'scrape_slug' | 'status'>): boolean {
	const availability = getLeagueCatalogAvailability(league);
	return (
		typeof league.scrape_slug === 'string' &&
		league.scrape_slug.length > 0 &&
		availability !== 'discovered' &&
		availability !== 'unavailable'
	);
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

/**
 * Keep the complete catalog returned by the API visible while making a large
 * OddsHarvester catalog practical to browse. Country selection is an optional
 * narrowing filter; search matches the country, display name and scraper slug.
 */
export function filterScrapeLeagueGroups(
	countries: Country[],
	selectedCountries: string[],
	query: string
): Country[] {
	const selectedCountrySet = new Set(selectedCountries);
	const normalizedQuery = query.trim().toLocaleLowerCase();

	return countries
		.filter((country) => selectedCountrySet.size === 0 || selectedCountrySet.has(country.country))
		.map((country) => ({
			...country,
			leagues: country.leagues.filter((league) => {
				if (!normalizedQuery) return true;
				return `${country.country} ${league.name} ${league.scrape_slug ?? ''}`
					.toLocaleLowerCase()
					.includes(normalizedQuery);
			})
		}))
		.filter((country) => country.leagues.length > 0);
}

export type LargeScrapeScopeWarning = {
	key: string;
	queuedHistoricJobs: number;
	estimatedLeagueSeasonWork: number;
	message: string;
};

/**
 * Historical scraping queues one backend job per season. A broad catalog
 * selection can still make each job process hundreds of league-season
 * combinations. Keep this visible without hiding or limiting any
 * OddsHarvester league.
 */
export function getLargeScrapeScopeWarning(
	supportedLeagueCount: number,
	historicSeasonCount: number
): LargeScrapeScopeWarning | null {
	if (supportedLeagueCount <= 0 || historicSeasonCount <= 0) return null;

	const isBroadLeagueScope = supportedLeagueCount >= 25;
	const isLongHistory = historicSeasonCount >= 20;
	if (!isBroadLeagueScope && !isLongHistory) return null;

	const estimatedLeagueSeasonWork = supportedLeagueCount * historicSeasonCount;
	return {
		key: `${supportedLeagueCount}:${historicSeasonCount}`,
		queuedHistoricJobs: historicSeasonCount,
		estimatedLeagueSeasonWork,
		message: `This queues ${historicSeasonCount} historical backend job${historicSeasonCount === 1 ? '' : 's'} covering up to ${estimatedLeagueSeasonWork} league-season combinations (${supportedLeagueCount} supported league${supportedLeagueCount === 1 ? '' : 's'} × ${historicSeasonCount} seasons).`
	};
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

export function buildWorldCupSeasonsFromDateRange(from: string, to: string, today = new Date()): string[] {
	if (!from || !to) return [];

	const startYear = new Date(`${from}T00:00:00`).getFullYear();
	const endYear = new Date(`${to}T00:00:00`).getFullYear();
	if (Number.isNaN(startYear) || Number.isNaN(endYear) || startYear > endYear) return [];

	const seasons: string[] = [];
	const currentYear = today.getFullYear();
	for (let year = endYear; year >= startYear; year -= 1) {
		if (year >= currentYear) continue;
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
