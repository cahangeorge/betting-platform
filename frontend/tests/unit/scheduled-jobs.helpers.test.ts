import test from 'node:test';
import assert from 'node:assert/strict';

import {
	cronFromInterval,
	describeScheduledJob,
	scheduledJobsForArea
} from '../../src/lib/scheduled-jobs.helpers.ts';
import type { ScheduledJob } from '../../src/lib/types.ts';

function makeJob(overrides: Partial<ScheduledJob>): ScheduledJob {
	return {
		id: 1,
		name: 'Job',
		cron_expression: '0 */6 * * *',
		task_type: 'unknown',
		config: null,
		enabled: true,
		last_run: null,
		next_run: null,
		created_at: '2026-06-24T00:00:00Z',
		...overrides
	};
}

test('filters scheduled jobs by scrape and prediction areas', () => {
	const jobs = [
		makeJob({ id: 1, name: 'Auto scrape Premier League', task_type: 'scrape_odds' }),
		makeJob({ id: 2, name: 'Auto prediction Poisson', task_type: 'run_predictions' }),
		makeJob({ id: 3, name: 'Other maintenance', task_type: 'cleanup' })
	];

	assert.deepEqual(
		scheduledJobsForArea(jobs, 'scrape').map((job) => job.id),
		[1]
	);
	assert.deepEqual(
		scheduledJobsForArea(jobs, 'prediction').map((job) => job.id),
		[2]
	);
});

test('builds cron expressions from UI interval controls', () => {
	assert.equal(cronFromInterval('6', 'Hours'), '0 */6 * * *');
	assert.equal(cronFromInterval('2', 'Days'), '0 0 */2 * *');
	assert.equal(cronFromInterval('3', 'Weeks'), '0 0 * * 1');
	assert.equal(cronFromInterval('0', 'Hours'), '0 */1 * * *');
});

test('describes scheduled jobs as user-facing action buttons', () => {
	assert.equal(
		describeScheduledJob(makeJob({ name: 'Auto scrape Romania', enabled: false })),
		'Auto scrape Romania · paused · 0 */6 * * *'
	);
});
