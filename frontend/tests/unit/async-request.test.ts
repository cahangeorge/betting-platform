import test from 'node:test';
import assert from 'node:assert/strict';

import { createRequestGeneration } from '../../src/lib/async-request.ts';

test('only the latest asynchronous request generation remains current', () => {
	const requests = createRequestGeneration();
	const first = requests.next();
	const second = requests.next();

	assert.equal(requests.isCurrent(first), false);
	assert.equal(requests.isCurrent(second), true);
});

test('invalidating a generation rejects all work already in flight', () => {
	const requests = createRequestGeneration();
	const requestId = requests.next();

	requests.invalidate();

	assert.equal(requests.isCurrent(requestId), false);
});
