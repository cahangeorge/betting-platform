import assert from 'node:assert/strict';
import test from 'node:test';
import {
	safeScrapeFailureReason,
	scrapeAttemptNotice,
	type FailedScrapeAttempt
} from '../../src/routes/prepare/scrape-attempts.helpers.ts';

const failed: FailedScrapeAttempt[] = [
	{
		label: 'sezonul 2022/2023',
		params: { season: '2022/2023' },
		idempotencyKey: 'prepare-scrape-test-key',
		reason: 'Sursa nu a răspuns.'
	}
];

test('reports all-failed scrape attempts as actionable retry-only-failed work', () => {
	const notice = scrapeAttemptNotice([], failed);

	assert.match(notice, /Niciun job nu a fost pornit/);
	assert.match(notice, /Reîncearcă doar părțile eșuate/);
	assert.equal(failed[0].params.season, '2022/2023');
});

test('preserves successful job IDs while only failed attempts retain their retry payload', () => {
	const notice = scrapeAttemptNotice([41, 42], failed);

	assert.match(notice, /#41, 42/);
	assert.equal(failed.length, 1);
	assert.equal(failed[0].label, 'sezonul 2022/2023');
});

test('normalizes failure text before rendering it', () => {
	assert.equal(safeScrapeFailureReason(new Error('timeout\n\tfrom upstream')), 'timeout from upstream');
});
