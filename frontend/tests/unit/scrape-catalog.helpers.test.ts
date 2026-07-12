import test from 'node:test';
import assert from 'node:assert/strict';

import {
	HISTORY_PRESET_OPTIONS,
	buildFootballSeasonsFromDateRange,
	buildHistoricSeasons,
	buildHistoryDateRange,
	buildScrapeLeagueSlugs,
	buildWorldCupSeasonsFromDateRange,
	catalogAvailabilityLabel,
	filterScrapeLeagueGroups,
	getLargeScrapeScopeWarning,
	isLeagueScrapeSelectable,
	normaliseCatalogAvailability,
	parseCatalogMetadata,
	parseScrapeCatalog
} from '../../src/routes/prepare/catalog.helpers.ts';

test('history presets expose long World Cup backfill ranges', () => {
	assert.deepEqual(
		HISTORY_PRESET_OPTIONS.map((option) => option.value),
		['5', '10', '15', '20', '30', '40']
	);
});

test('maps selected catalog leagues to scrape slugs', () => {
	const slugs = buildScrapeLeagueSlugs(
		[
			{ id: 'premier_league', scrape_slug: 'england-premier-league' },
			{ id: 'world_cup', scrape_slug: 'world-cup' }
		],
		['premier_league', 'world_cup']
	);

	assert.deepEqual(slugs, ['england-premier-league', 'world-cup']);
});

test('omits leagues that do not have scrape support', () => {
	const slugs = buildScrapeLeagueSlugs(
		[
			{ id: 'allsvenskan', scrape_slug: null },
			{ id: 'world_cup', scrape_slug: 'world-cup' }
		],
		['allsvenskan', 'world_cup']
	);

	assert.deepEqual(slugs, ['world-cup']);
	assert.equal(isLeagueScrapeSelectable({ scrape_slug: null }), false);
	assert.equal(
		isLeagueScrapeSelectable({ scrape_slug: 'world-cup' }),
		true
	);
});

test('keeps the legacy catalog array working while consuming dynamic source, status, and refresh fields', () => {
	const catalog = parseScrapeCatalog([
		{
			country: 'Australia',
			leagues: [
				{
					id: 'a-league',
					name: 'A-League',
					matches_count: 0,
					scrape_slug: 'australia-a-league',
					source: 'discovered',
					status: 'validated',
					last_seen_at: '2026-07-12T09:30:00Z'
				}
			]
		}
	]);

	assert.equal(catalog.countries.length, 1);
	assert.equal(catalog.source, 'discovered');
	assert.equal(catalog.status, 'validated');
	assert.equal(catalog.lastRefreshedAt, '2026-07-12T09:30:00Z');
	assert.equal(catalogAvailabilityLabel(catalog.status), 'Ready to scrape');
});

test('makes unvalidated and unavailable dynamic leagues non-selectable without changing legacy behavior', () => {
	assert.equal(normaliseCatalogAvailability('available'), 'validated');
	assert.equal(normaliseCatalogAvailability('pending_validation'), 'discovered');
	assert.equal(isLeagueScrapeSelectable({ scrape_slug: 'australia-a-league', status: 'validated' }), true);
	assert.equal(isLeagueScrapeSelectable({ scrape_slug: 'australia-npl', status: 'discovered' }), false);
	assert.equal(isLeagueScrapeSelectable({ scrape_slug: 'australia-state', status: 'unavailable' }), false);
	assert.deepEqual(parseCatalogMetadata({ source: 'oddsportal', status: 'available', last_seen_at: '2026-07-12T10:00:00Z' }), {
		source: 'oddsportal',
		status: 'validated',
		lastRefreshedAt: '2026-07-12T10:00:00Z'
	});
});

test('keeps every returned league in country groups and searches by country, name, or scraper slug', () => {
	const countries = [
		{
			country: 'England',
			leagues: [
				{ id: 'premier', name: 'Premier League', matches_count: 380, scrape_slug: 'england-premier-league' },
				{ id: 'league-one', name: 'League One', matches_count: 552, scrape_slug: 'england-league-one' }
			]
		},
		{
			country: 'Romania',
			leagues: [{ id: 'superliga', name: 'SuperLiga', matches_count: 240, scrape_slug: 'romania-superliga' }]
		}
	];

	assert.deepEqual(
		filterScrapeLeagueGroups(countries, [], '').map((country) => country.leagues.map((league) => league.id)),
		[['premier', 'league-one'], ['superliga']]
	);
	assert.deepEqual(filterScrapeLeagueGroups(countries, [], 'one').map((country) => country.country), ['England']);
	assert.deepEqual(filterScrapeLeagueGroups(countries, [], 'romania-superliga').map((country) => country.country), ['Romania']);
	assert.deepEqual(filterScrapeLeagueGroups(countries, ['England'], '').map((country) => country.country), ['England']);
});

test('requires acknowledgement only for broad or long historical scrape scopes', () => {
	assert.equal(getLargeScrapeScopeWarning(24, 19), null);
	assert.deepEqual(getLargeScrapeScopeWarning(25, 10), {
		key: '25:10',
		queuedHistoricJobs: 10,
		estimatedLeagueSeasonWork: 250,
		message: 'This queues 10 historical backend jobs covering up to 250 league-season combinations (25 supported leagues × 10 seasons).'
	});
	assert.deepEqual(getLargeScrapeScopeWarning(1, 20), {
		key: '1:20',
		queuedHistoricJobs: 20,
		estimatedLeagueSeasonWork: 20,
		message: 'This queues 20 historical backend jobs covering up to 20 league-season combinations (1 supported league × 20 seasons).'
	});
});

test('builds a concrete date range for history presets', () => {
	assert.deepEqual(buildHistoryDateRange(10, new Date('2026-06-20T12:00:00Z')), {
		from: '2016-06-20',
		to: '2026-06-20'
	});
});

test('builds football season ranges from explicit history dates', () => {
	assert.deepEqual(buildFootballSeasonsFromDateRange('2023-08-01', '2026-06-20'), [
		'2025-2026',
		'2024-2025',
		'2023-2024'
	]);
});

test('builds World Cup seasons as single tournament years', () => {
	assert.deepEqual(
		buildWorldCupSeasonsFromDateRange('2011-06-20', '2026-06-20', new Date('2026-06-24T00:00:00Z')),
		[
			'2022',
			'2018',
			'2014'
		]
	);
	assert.deepEqual(
		buildWorldCupSeasonsFromDateRange('1998-01-01', '2026-06-20', new Date('2026-06-24T00:00:00Z')),
		[
			'2022',
			'2018',
			'2014',
			'2010',
			'2006',
			'2002',
			'1998'
		]
	);
	assert.deepEqual(
		buildWorldCupSeasonsFromDateRange('2022-01-01', '2022-12-31', new Date('2026-06-24T00:00:00Z')),
		['2022']
	);
	assert.deepEqual(buildHistoricSeasons('2016-06-20', '2026-06-20', ['world-cup']), [
		'2022',
		'2018'
	]);
});
