import { ApiClient } from './client';
import type {
	Country,
	FootballCatalogDiscoveryValidationResponse,
	LeagueInfo
} from '$lib/types';

class CatalogApi extends ApiClient {
	async getCountries(): Promise<Country[]> {
		return this.get<Country[]>('/api/v1/catalog/countries');
	}

	async getLeagues(country?: string): Promise<LeagueInfo[]> {
		const qs = country ? `?country=${encodeURIComponent(country)}` : '';
		return this.get<LeagueInfo[]>(`/api/v1/catalog/leagues${qs}`);
	}

	async getAllLeagues(): Promise<Country[]> {
		return this.get<Country[]>('/api/v1/catalog/leagues/all');
	}

	async discoverAndValidate(
		countries: string[],
		maxAttempts: number,
		batchSize: number
	): Promise<FootballCatalogDiscoveryValidationResponse> {
		return this.post<FootballCatalogDiscoveryValidationResponse>(
			'/api/v1/catalog/football/discover-validate',
			{
				countries,
				max_attempts: maxAttempts,
				batch_size: batchSize
			}
		);
	}
}

export const catalogApi = new CatalogApi();
