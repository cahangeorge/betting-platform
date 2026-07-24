import test from 'node:test';
import assert from 'node:assert/strict';

import {
	countFinalScoreConflicts,
	finalScoreConflictPolicyMessage
} from '../../src/lib/result-refresh.helpers.ts';

test('counts only explicit final-score conflict log actions', () => {
	assert.equal(
		countFinalScoreConflicts([
			{ action: 'job_completed' },
			{ action: 'final_score_conflict' },
			{ action: 'final_score_conflict' }
		]),
		2
	);
});

test('states that recorded conflicts retain final scores and do not apply corrections', () => {
	const message = finalScoreConflictPolicyMessage({
		status: 'completed',
		conflictCount: 1,
		logsAvailable: true
	});

	assert.match(message, /1 final-score conflict recorded/);
	assert.match(message, /persisted final scores were retained/);
	assert.match(message, /Corrections require a dedicated audited endpoint/);
});

test('does not infer conflicts before a refresh job completes', () => {
	const message = finalScoreConflictPolicyMessage({ status: 'running' });

	assert.match(message, /Refresh is running/);
	assert.match(message, /Any conflicting final score is retained if this refresh reaches source data/);
	assert.doesNotMatch(message, /conflicts are recorded/);
});
