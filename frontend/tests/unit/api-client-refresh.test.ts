import test from 'node:test';
import assert from 'node:assert/strict';

import { ApiClient, ApiClientError, waitForSessionRefresh } from '../../src/lib/api/client.ts';

class TestApiClient extends ApiClient {
	read<T>(path: string, fetchFn: typeof fetch): Promise<T> {
		return this.get<T>(path, undefined, fetchFn);
	}
}

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

test('refreshes an expired session once and retries the original request', async () => {
	const client = new TestApiClient('http://api.test');
	let dataRequests = 0;
	let refreshRequests = 0;
	const fetchFn = (async (input: RequestInfo | URL) => {
		const url = String(input);
		if (url.endsWith('/api/v1/auth/refresh')) {
			refreshRequests += 1;
			return jsonResponse(200, { refreshed: true });
		}
		dataRequests += 1;
		return dataRequests === 1
			? jsonResponse(401, { detail: 'Expired session' })
			: jsonResponse(200, { ok: true });
	}) as typeof fetch;

	assert.deepEqual(await client.read('/api/v1/tickets', fetchFn), { ok: true });
	assert.equal(dataRequests, 2);
	assert.equal(refreshRequests, 1);
});

test('deduplicates refresh requests across concurrent 401 responses', async () => {
	const client = new TestApiClient('http://api.test');
	let sessionReady = false;
	let refreshRequests = 0;
	let releaseRefresh!: () => void;
	const refreshGate = new Promise<void>((resolve) => {
		releaseRefresh = resolve;
	});
	const fetchFn = (async (input: RequestInfo | URL) => {
		const url = String(input);
		if (url.endsWith('/api/v1/auth/refresh')) {
			refreshRequests += 1;
			await refreshGate;
			sessionReady = true;
			return jsonResponse(200, { refreshed: true });
		}
		return sessionReady
			? jsonResponse(200, { path: url })
			: jsonResponse(401, { detail: 'Expired session' });
	}) as typeof fetch;

	const first = client.read('/api/v1/tickets', fetchFn);
	const second = client.read('/api/v1/bankroll', fetchFn);
	await new Promise((resolve) => setTimeout(resolve, 0));
	releaseRefresh();

	const responses = await Promise.all([first, second]);
	assert.equal(responses.length, 2);
	assert.equal(refreshRequests, 1);
});

test('does not refresh auth endpoints or retry after refresh failure', async () => {
	const client = new TestApiClient('http://api.test');
	let refreshRequests = 0;
	const fetchFn = (async (input: RequestInfo | URL) => {
		const url = String(input);
		if (url.endsWith('/api/v1/auth/refresh')) {
			refreshRequests += 1;
			return jsonResponse(401, { detail: 'Refresh expired' });
		}
		return jsonResponse(401, { detail: 'Unauthorized' });
	}) as typeof fetch;

	await assert.rejects(
		client.read('/api/v1/auth/me', fetchFn),
		(error: unknown) => error instanceof ApiClientError && error.statusCode === 401
	);
	assert.equal(refreshRequests, 0);

	await assert.rejects(
		client.read('/api/v1/tickets', fetchFn),
		(error: unknown) => error instanceof ApiClientError && error.statusCode === 401
	);
	assert.equal(refreshRequests, 1);
});

test('logout coordination waits for an in-flight session refresh', async () => {
	const client = new TestApiClient('http://api.test');
	let releaseRefresh!: () => void;
	let refreshStarted = false;
	let logoutMayProceed = false;
	const refreshGate = new Promise<void>((resolve) => {
		releaseRefresh = resolve;
	});
	const fetchFn = (async (input: RequestInfo | URL) => {
		if (String(input).endsWith('/api/v1/auth/refresh')) {
			refreshStarted = true;
			await refreshGate;
			return jsonResponse(200, { refreshed: true });
		}
		return jsonResponse(401, { detail: 'Expired session' });
	}) as typeof fetch;

	const request = client.read('/api/v1/tickets', fetchFn).catch(() => undefined);
	while (!refreshStarted) await new Promise((resolve) => setTimeout(resolve, 0));
	const logoutBarrier = waitForSessionRefresh(fetchFn).then(() => {
		logoutMayProceed = true;
	});
	await new Promise((resolve) => setTimeout(resolve, 0));
	assert.equal(logoutMayProceed, false);

	releaseRefresh();
	await Promise.all([request, logoutBarrier]);
	assert.equal(logoutMayProceed, true);
});
