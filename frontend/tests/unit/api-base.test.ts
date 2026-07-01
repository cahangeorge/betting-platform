import test from 'node:test';
import assert from 'node:assert/strict';

import { apiBaseUrl } from '../../src/lib/api/base.ts';

test('keeps API same-origin for local frontend ports so Vite proxy can forward auth cookies', () => {
	assert.equal(apiBaseUrl(new URL('http://127.0.0.1:5175/scrape')), '');
	assert.equal(apiBaseUrl(new URL('http://localhost:5174/predict')), '');
});

test('keeps API same-origin when app is served through nginx', () => {
	assert.equal(apiBaseUrl(new URL('http://127.0.0.1:8081/scrape')), '');
});
