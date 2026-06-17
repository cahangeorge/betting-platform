import { backendRequest, waitFor, withBearerToken } from './backend';
import type { AuthSession, ScrapeJob } from './types';

export async function listScrapeJobs(session: AuthSession): Promise<ScrapeJob[]> {
	return await backendRequest<ScrapeJob[]>('/api/v1/data/scrape', {
		headers: withBearerToken(session.token.access_token)
	});
}

export async function createScrapeJob(
	session: AuthSession,
	jobType: string,
	options?: {
		league?: string;
		params?: Record<string, unknown>;
	}
): Promise<ScrapeJob> {
	return await backendRequest<ScrapeJob>('/api/v1/data/scrape', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			...withBearerToken(session.token.access_token)
		},
		body: JSON.stringify({
			job_type: jobType,
			league: options?.league,
			params: options?.params
		})
	});
}

export async function executeScrapeJob(session: AuthSession, jobId: number): Promise<ScrapeJob> {
	await waitFor(
		async () => {
			const jobs = await listScrapeJobs(session);
			return jobs.find((candidate) => candidate.id === jobId) ?? null;
		},
		(job) => job !== null,
		10_000,
		250
	);

	return await backendRequest<ScrapeJob>(`/api/v1/data/scrape/${jobId}/execute`, {
		method: 'POST',
		headers: withBearerToken(session.token.access_token)
	});
}

export async function waitForScrapeTerminalState(
	session: AuthSession,
	jobId: number,
	timeoutMs = 240_000
): Promise<ScrapeJob> {
	return waitFor(
		async () => {
			const jobs = await listScrapeJobs(session);
			const job = jobs.find((candidate) => candidate.id === jobId);
			if (!job) {
				throw new Error(`Scrape job ${jobId} not found in list response`);
			}
			return job;
		},
		(job) => job.status === 'completed' || job.status === 'failed',
		timeoutMs
	);
}
