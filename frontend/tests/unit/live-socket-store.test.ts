import test, { afterEach, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { get } from 'svelte/store';

import { liveSocket, matchEvents, oddsUpdates, predictionUpdates } from '../../src/lib/stores/liveSocket.ts';

class FakeWebSocket {
	static CONNECTING = 0;
	static OPEN = 1;
	static CLOSED = 3;
	static instances: FakeWebSocket[] = [];

	url: string;
	readyState = FakeWebSocket.CONNECTING;
	sent: string[] = [];
	onopen: (() => void) | null = null;
	onmessage: ((event: { data: string }) => void) | null = null;
	onclose: (() => void) | null = null;
	onerror: (() => void) | null = null;

	constructor(url: string) {
		this.url = url;
		FakeWebSocket.instances.push(this);
	}

	send(data: string) {
		this.sent.push(data);
	}

	open() {
		this.readyState = FakeWebSocket.OPEN;
		this.onopen?.();
	}

	emit(message: unknown) {
		this.onmessage?.({ data: JSON.stringify(message) });
	}

	close() {
		this.readyState = FakeWebSocket.CLOSED;
	}
}

const testGlobal = globalThis as unknown as Record<string, unknown>;
const originalWindow = testGlobal.window;
const originalWebSocket = testGlobal.WebSocket;

beforeEach(() => {
	FakeWebSocket.instances = [];
	testGlobal.window = { location: new URL('http://127.0.0.1:5175/live') };
	testGlobal.WebSocket = FakeWebSocket;
	liveSocket.disconnect();
});

afterEach(() => {
	liveSocket.disconnect();
	if (originalWindow === undefined) {
		delete testGlobal.window;
	} else {
		testGlobal.window = originalWindow;
	}
	if (originalWebSocket === undefined) {
		delete testGlobal.WebSocket;
	} else {
		testGlobal.WebSocket = originalWebSocket;
	}
});

test('connects to the backend live websocket and publishes typed update stores', () => {
	liveSocket.connect();

	const socket = FakeWebSocket.instances.at(-1);
	assert.ok(socket);
	assert.equal(socket.url, 'ws://127.0.0.1:8001/api/v1/live/ws');
	assert.equal(get(liveSocket).status, 'connecting');

	socket.open();
	assert.equal(get(liveSocket).status, 'connected');
	assert.deepEqual(socket.sent.map((payload) => JSON.parse(payload)), [
		{ action: 'subscribe', channel: 'all' }
	]);

	socket.emit({
		type: 'odds_update',
		match_id: 42,
		data: { market: '1x2', home_odds: 2.1 },
		timestamp: 123
	});
	assert.equal(get(oddsUpdates)?.match_id, 42);
	assert.equal(get(predictionUpdates), null);
	assert.equal(get(matchEvents), null);

	socket.emit({
		type: 'prediction_update',
		run_id: 7,
		status: 'completed',
		progress: 1,
		timestamp: 124
	});
	assert.equal(get(predictionUpdates)?.run_id, 7);
	assert.equal(get(oddsUpdates), null);

	socket.emit({
		type: 'match_event',
		match_id: 42,
		event: 'goal',
		data: { team: 'home' },
		timestamp: 125
	});
	assert.equal(get(matchEvents)?.event, 'goal');
	assert.equal(get(predictionUpdates), null);
});
