import type { ProviderRuntimeSnapshot } from '$lib/types';
import { ApiClient } from './client';

class ProviderRuntimeApi extends ApiClient {
	async getSnapshot(): Promise<ProviderRuntimeSnapshot> {
		return this.get<ProviderRuntimeSnapshot>('/api/v1/provider/runtime');
	}
}

export const providerRuntimeApi = new ProviderRuntimeApi();
