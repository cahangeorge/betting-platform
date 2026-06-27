import test from 'node:test';
import assert from 'node:assert/strict';

import config from '../../svelte.config.js';

test('allows local Podman frontend and nginx origins for form actions', () => {
	const trustedOrigins = config.kit?.csrf?.trustedOrigins ?? [];
	for (const origin of [
		'http://127.0.0.1:5174',
		'http://127.0.0.1:5175',
		'http://127.0.0.1:8080',
		'http://127.0.0.1:8081'
	]) {
		assert.ok(trustedOrigins.includes(origin), `${origin} should be trusted`);
	}
});
