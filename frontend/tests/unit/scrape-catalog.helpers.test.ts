import test from 'node:test';
import assert from 'node:assert/strict';

import {
	HISTORY_PRESET_OPTIONS,
	buildFootballSeasonsFromDateRange,
	buildHistoricSeasons,
	buildHistoryDateRange,
	buildScrapeLeagueSlugs,
	buildWorldCupSeasonsFromDateRange,
	isLeagueScrapeSelectable
} from '../../src/routes/scrape/catalog.helpers.ts';

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
