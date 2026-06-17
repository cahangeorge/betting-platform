import { ApiClient } from './client';
import type { Strategy } from '$lib/types';

class StrategiesApi extends ApiClient {
	async list(): Promise<Strategy[]> {
		return this.get<Strategy[]>('/api/v1/strategies');
	}

	async create(data: {
		name: string;
		model_type: string;
		description?: string;
		parameters?: Record<string, unknown>;
		weights?: Record<string, unknown>;
	}): Promise<Strategy> {
		return this.post<Strategy>('/api/v1/strategies', data as unknown as Record<string, unknown>);
	}

	async getById(id: number): Promise<Strategy> {
		return this.get<Strategy>(`/api/v1/strategies/${id}`);
	}

	async update(
		id: number,
		data: Partial<{
			name: string;
			description: string;
			parameters: Record<string, unknown>;
			weights: Record<string, unknown>;
			is_active: boolean;
		}>
	): Promise<Strategy> {
		return this.put<Strategy>(
			`/api/v1/strategies/${id}`,
			data as unknown as Record<string, unknown>
		);
	}

	async remove(id: number): Promise<void> {
		return this.del<void>(`/api/v1/strategies/${id}`);
	}

	async run(
		id: number,
		data: {
			match_ids: number[];
			markets?: string[];
			parameters?: Record<string, unknown>;
		}
	): Promise<unknown> {
		return this.post(
			`/api/v1/strategies/${id}/run`,
			data as unknown as Record<string, unknown>
		);
	}
}

export const strategiesApi = new StrategiesApi();
