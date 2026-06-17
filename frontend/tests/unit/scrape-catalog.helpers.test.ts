import test from 'node:test';
import assert from 'node:assert/strict';

import {
	buildScrapeLeagueSlugs,
	isLeagueScrapeSelectable
} from '../../src/routes/scrape/catalog.helpers.ts';

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
