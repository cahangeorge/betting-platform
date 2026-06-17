import type { ApiError } from '$lib/types';

// Use empty base URL (same-origin) so auth cookies set by SvelteKit are sent
// with API requests. The Vite dev server proxies /api/* to the backend.
const BASE_URL: string = '';

export class ApiClient {
	private baseUrl: string;

	constructor(baseUrl: string = BASE_URL) {
		this.baseUrl = baseUrl;
	}

	private async request<T>(
		method: string,
		path: string,
		body?: Record<string, unknown> | FormData,
		options?: { timeout?: number },
		fetchFn?: typeof fetch
	): Promise<T> {
		const url = `${this.baseUrl}${path}`;
		const controller = new AbortController();
		const timeoutId = options?.timeout
			? setTimeout(() => controller.abort(), options.timeout)
			: undefined;

		const headers: Record<string, string> = {};

		let requestBody: string | FormData | undefined;

		if (body instanceof FormData) {
			requestBody = body;
		} else if (body !== undefined) {
			headers['Content-Type'] = 'application/json';
			requestBody = JSON.stringify(body);
		}

		const fetchImpl = fetchFn || fetch;

		try {
			const response = await fetchImpl(url, {
				method,
				headers,
				body: requestBody,
				credentials: 'include',
				signal: controller.signal
			});

			clearTimeout(timeoutId);

			if (!response.ok) {
				let errorDetail: string;
				try {
					const errorBody = await response.json();
					errorDetail = (errorBody as ApiError).detail || `HTTP ${response.status}`;
				} catch {
					errorDetail = `HTTP ${response.status}: ${response.statusText}`;
				}
				throw new ApiClientError(errorDetail, response.status);
			}

			if (response.status === 204) {
				return undefined as T;
			}

			return (await response.json()) as T;
		} catch (err) {
			clearTimeout(timeoutId);
			if (err instanceof ApiClientError) {
				throw err;
			}
			if ((err as Error).name === 'AbortError') {
				throw new ApiClientError('Request timed out', 408);
			}
			throw new ApiClientError(
				(err as Error).message || 'Network error',
				0
			);
		}
	}

	protected async get<T>(path: string, options?: { timeout?: number }, fetchFn?: typeof fetch): Promise<T> {
		return this.request<T>('GET', path, undefined, options, fetchFn);
	}

	protected async post<T>(
		path: string,
		body?: Record<string, unknown> | FormData,
		options?: { timeout?: number }
	): Promise<T> {
		return this.request<T>('POST', path, body, options);
	}

	protected async put<T>(
		path: string,
		body?: Record<string, unknown>,
		options?: { timeout?: number }
	): Promise<T> {
		return this.request<T>('PUT', path, body, options);
	}

	protected async patch<T>(
		path: string,
		body?: Record<string, unknown>,
		options?: { timeout?: number }
	): Promise<T> {
		return this.request<T>('PATCH', path, body, options);
	}

	protected async del<T>(path: string, options?: { timeout?: number }): Promise<T> {
		return this.request<T>('DELETE', path, undefined, options);
	}
}

export class ApiClientError extends Error {
	public statusCode: number;

	constructor(message: string, statusCode: number) {
		super(message);
		this.name = 'ApiClientError';
		this.statusCode = statusCode;
	}
}
