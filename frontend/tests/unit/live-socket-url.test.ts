import test from 'node:test';
import assert from 'node:assert/strict';

import { buildLiveWebSocketUrl } from '../../src/lib/stores/liveSocket.ts';

test('uses backend websocket port when app is served directly from the local frontend container', () => {
	const url = buildLiveWebSocketUrl(new URL('http://127.0.0.1:5175/dashboard'));
	assert.equal(url, 'ws://127.0.0.1:8001/api/v1/live/ws');
});

test('keeps same-origin websocket URL when app is served through nginx', () => {
	const url = buildLiveWebSocketUrl(new URL('http://127.0.0.1:8081/dashboard'));
	assert.equal(url, 'ws://127.0.0.1:8081/api/v1/live/ws');
});

test('uses explicitly configured public API URL when provided', () => {
	const url = buildLiveWebSocketUrl(
		new URL('http://127.0.0.1:5175/dashboard'),
		'https://api.example.test'
	);
	assert.equal(url, 'wss://api.example.test/api/v1/live/ws');
});
