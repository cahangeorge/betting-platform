import { ApiClient } from './client';
import type { ScheduledJob, ScheduledJobCreateRequest } from '$lib/types';

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
}

export const jobsApi = new JobsApi();
