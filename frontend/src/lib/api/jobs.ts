import { ApiClient } from './client';
import type { ScheduledJob, ScheduledJobCreateRequest, ScheduledJobRun, ScheduledJobRunPage } from '$lib/types';

class JobsApi extends ApiClient {
	async getScheduledJobs(): Promise<ScheduledJob[]> {
		return this.get<ScheduledJob[]>('/api/v1/jobs');
	}

	async getScheduledJob(id: number): Promise<ScheduledJob> {
		return this.get<ScheduledJob>(`/api/v1/jobs/${id}`);
	}

	async createScheduledJob(data: ScheduledJobCreateRequest): Promise<ScheduledJob> {
		return this.post<ScheduledJob>('/api/v1/jobs', data as unknown as Record<string, unknown>);
	}

	async updateScheduledJob(id: number, data: Partial<ScheduledJobCreateRequest>): Promise<ScheduledJob> {
		// Backend only supports toggling enabled state.
		return this.patch<ScheduledJob>(`/api/v1/jobs/${id}/toggle`, data as unknown as Record<string, unknown>);
	}

	async deleteScheduledJob(id: number): Promise<void> {
		// Backend doesn't have delete — no-op
		return undefined as void;
	}

	async toggleJob(id: number): Promise<ScheduledJob> {
		return this.patch<ScheduledJob>(`/api/v1/jobs/${id}/toggle`);
	}

	async getScheduledJobRuns(id: number, page = 1, perPage = 10): Promise<ScheduledJobRunPage> {
		const search = new URLSearchParams({ page: String(page), per_page: String(perPage) });
		return this.get<ScheduledJobRunPage>(`/api/v1/jobs/${id}/runs?${search.toString()}`);
	}

	async getJobRun(id: number): Promise<ScheduledJobRun> {
		return this.get<ScheduledJobRun>(`/api/v1/job-runs/${id}`);
	}
}

export const jobsApi = new JobsApi();
