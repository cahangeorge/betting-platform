import { ApiClient, ApiClientError } from './client';
import type { ScrapeJob, ScrapeJobCreateRequest, Dataset, League } from '$lib/types';

class DataApi extends ApiClient {
	async getJobs(status?: string): Promise<ScrapeJob[]> {
		return this.get<ScrapeJob[]>('/api/v1/data/scrape');
	}

	async getJob(id: number): Promise<ScrapeJob> {
		return this.get<ScrapeJob>(`/api/v1/data/scrape/${id}`);
	}

	async createJob(data: ScrapeJobCreateRequest): Promise<ScrapeJob> {
		return this.post<ScrapeJob>('/api/v1/data/scrape', data as unknown as Record<string, unknown>);
	}

	async cancelJob(id: number): Promise<ScrapeJob> {
		throw new ApiClientError('Scrape job cancellation is not supported by the backend yet', 501);
	}

	async getDatasets(): Promise<Dataset[]> {
		return this.get<Dataset[]>('/api/v1/data/datasets');
	}

	async getDataset(id: number): Promise<Dataset> {
		return this.get<Dataset>(`/api/v1/data/datasets/${id}`);
	}

	async getLeagues(): Promise<League[]> {
		return this.get<League[]>('/api/v1/catalog/leagues');
	}
}

export const dataApi = new DataApi();
