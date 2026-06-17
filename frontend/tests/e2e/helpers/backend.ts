import type { E2EEnv } from './types';

const DEFAULT_FRONTEND_URL = 'http://127.0.0.1:5175';
const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8001';

export function getE2EEnv(): E2EEnv {
	return {
		frontendURL: process.env.E2E_FRONTEND_URL ?? DEFAULT_FRONTEND_URL,
		backendURL: process.env.E2E_BACKEND_URL ?? DEFAULT_BACKEND_URL,
		mode: process.env.E2E_MODE === 'live' ? 'live' : 'hybrid',
		liveScrapeTimeoutMs: Number(process.env.E2E_LIVE_SCRAPE_TIMEOUT_SECONDS || '240') * 1000
	};
}

export function getE2EConfig(): E2EEnv {
	return getE2EEnv();
}

export interface ApiError {
	status: number;
	statusText: string;
	detail?: string;
}

export async function backendProbe<T>(path: string, init: RequestInit = {}): Promise<{ status: number; json: T } | { status: number; error: ApiError }> {
	const { backendURL } = getE2EEnv();
	try {
		const response = await fetch(new URL(path, backendURL).toString(), init);
		const data = (await response.json().catch(() => ({}))) as T;
		return { status: response.status, ...(response.ok ? { json: data as T } : { error: { status: response.status, statusText: response.statusText, detail: (data as { detail?: string })?.detail } }) };
	} catch (error) {
		return {
			status: 0,
			error: {
				status: 0,
				statusText: error instanceof Error ? error.message : 'Network error'
			}
		};
	}
}

export async function backendRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
	const { backendURL } = getE2EEnv();
	const response = await fetch(new URL(path, backendURL).toString(), init);

	if (!response.ok) {
		const detail = await response.text().catch(() => response.statusText);
		throw new Error(`Backend request failed: ${path} (${response.status}) ${detail}`);
	}

	return (await response.json()) as T;
}

export async function assertBackendHealthy(): Promise<void> {
	const result = await backendProbe('/api/v1/health');
	if (!('json' in result) || result.status !== 200) {
		const details = 'error' in result ? result.error.statusText : 'Unexpected response';
		throw new Error(`Backend health check failed: ${result.status} ${details}`);
	}
}

export async function waitForBackendReady(timeoutMs = 30_000): Promise<void> {
	const deadline = Date.now() + timeoutMs;
	while (Date.now() < deadline) {
		try {
			const result = await backendProbe('/api/v1/health');
			if (result.status === 200) {
				return;
			}

			const response = await fetch(new URL('/api/v1/auth/me', getE2EEnv().backendURL), {
				method: 'GET',
				redirect: 'manual'
			});

			if (response.status === 401 || response.status === 403 || response.status === 200) {
				return;
			}
		} catch {
			// ignore while waiting
		}

		await new Promise((resolve) => setTimeout(resolve, 500));
	}

	throw new Error('Backend was not reachable in time');
}

export function withBearerToken(token: string): HeadersInit {
	return {
		Authorization: `Bearer ${token}`
	};
}

export async function poll<T>(
	check: () => Promise<T>,
	isDone: (value: T) => boolean,
	timeoutMs = 30_000,
	intervalMs = 1_000
): Promise<T> {
	const deadline = Date.now() + timeoutMs;
	let lastError: unknown = null;

	while (Date.now() < deadline) {
		try {
			const value = await check();
			if (isDone(value)) {
				return value;
			}
		} catch (error) {
			lastError = error;
		}

		await new Promise((resolve) => setTimeout(resolve, intervalMs));
	}

	if (lastError instanceof Error) {
		throw lastError;
	}

	throw new Error(`Polling timed out after ${timeoutMs}ms`);
}

export async function waitFor<T>(
	check: () => Promise<T>,
	isDone: (value: T) => boolean,
	timeoutMs = 30_000,
	intervalMs = 1_000
): Promise<T> {
	return poll(check, isDone, timeoutMs, intervalMs);
}
