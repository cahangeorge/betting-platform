import test from 'node:test';
import assert from 'node:assert/strict';

import { formatApiErrorDetail } from '../../src/lib/api/error-detail.ts';

test('formats structured backend details without leaking object stringification', () => {
	assert.equal(
		formatApiErrorDetail({
			message: 'Dataset match resolution is incomplete; analysis was not started',
			resolved_records_count: 38,
			unresolved_records_count: 2
		}),
		'Dataset match resolution is incomplete; analysis was not started (38 rezolvate, 2 nerezolvate)'
	);
});

test('keeps string errors and provides a stable fallback for unknown payloads', () => {
	assert.equal(formatApiErrorDetail('No active strategies are available'), 'No active strategies are available');
	assert.equal(formatApiErrorDetail({ dataset_id: 33 }), 'Cererea a eșuat din cauza unui răspuns API invalid.');
});
