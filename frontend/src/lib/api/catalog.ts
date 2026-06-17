import { ApiClient } from './client';
import type { Country, LeagueInfo } from '$lib/types';

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
}

export const catalogApi = new CatalogApi();
