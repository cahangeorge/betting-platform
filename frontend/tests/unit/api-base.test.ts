import test from 'node:test';
import assert from 'node:assert/strict';

import { apiBaseUrl } from '../../src/lib/api/base.ts';

test('uses backend API port when app is served directly from local frontend ports', () => {
	assert.equal(apiBaseUrl(new URL('http://127.0.0.1:5175/scrape')), 'http://127.0.0.1:8001');
	assert.equal(apiBaseUrl(new URL('http://localhost:5174/predict')), 'http://localhost:8001');
});

test('keeps API same-origin when app is served through nginx', () => {
	assert.equal(apiBaseUrl(new URL('http://127.0.0.1:8081/scrape')), '');
});
