export interface BackendLoadStatus {
	state: 'ready' | 'degraded';
	message: string | null;
	failedEndpoints: string[];
}

interface BackendLoadResult<T> {
	data: T;
	ok: boolean;
	endpointLabel: string;
}

export function createBackendPageLoader(apiBase: string, token: string, fetchImpl: typeof fetch) {
	async function fetchJson<T>(path: string, fallback: T, endpointLabel: string): Promise<BackendLoadResult<T>> {
		try {
			const res = await fetchImpl(`${apiBase}/api/v1${path}`, {
				headers: { Authorization: `Bearer ${token}` }
			});
			if (!res.ok) {
				return { data: fallback, ok: false, endpointLabel };
			}

			return {
				data: (await res.json()) as T,
				ok: true,
				endpointLabel
			};
		} catch {
			return { data: fallback, ok: false, endpointLabel };
		}
	}

	return { fetchJson };
}

export function summarizeBackendLoad(results: Array<BackendLoadResult<unknown>>): BackendLoadStatus {
	const failedEndpoints = results.filter((result) => !result.ok).map((result) => result.endpointLabel);
	if (failedEndpoints.length === 0) {
		return {
			state: 'ready',
			message: null,
			failedEndpoints: []
		};
	}

	const noun = failedEndpoints.length === 1 ? 'feed' : 'feeds';
	return {
		state: 'degraded',
		message: `Backend ${noun} unavailable: ${failedEndpoints.join(', ')}. Showing partial data.`,
		failedEndpoints
	};
}
