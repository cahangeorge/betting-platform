import assert from 'node:assert/strict';
import test from 'node:test';
import { cronFromInterval } from '../../src/lib/scheduled-jobs.helpers.ts';
import {
	autoScrapeIntervalHours,
	PREPARE_INTERVAL_UNIT_OPTIONS
} from '../../src/routes/prepare/interval.helpers.ts';

test('Prepare keeps English interval values for cron and Romanian labels for operators', () => {
	assert.deepEqual(PREPARE_INTERVAL_UNIT_OPTIONS, [
		{ value: 'Hours', label: 'Ore' },
		{ value: 'Days', label: 'Zile' },
		{ value: 'Weeks', label: 'Săptămâni' }
	]);
	assert.equal(cronFromInterval('2', 'Hours'), '0 */2 * * *');
	assert.equal(cronFromInterval('2', 'Days'), '0 0 */2 * *');
	assert.equal(cronFromInterval('2', 'Weeks'), '0 0 * * 1');
});

test('Prepare payload conversion preserves every wire interval unit', () => {
	assert.equal(autoScrapeIntervalHours('2', 'Hours'), 2);
	assert.equal(autoScrapeIntervalHours('2', 'Days'), 48);
	assert.equal(autoScrapeIntervalHours('2', 'Weeks'), 336);
});
