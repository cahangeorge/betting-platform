import type { ScheduledJob } from '$lib/types';

export type ScheduledJobArea = 'scrape' | 'prediction';

export function scheduledJobsForArea(jobs: ScheduledJob[], area: ScheduledJobArea): ScheduledJob[] {
	const tokens =
		area === 'scrape'
			? ['scrape', 'scraping', 'odds', 'world_cup_pipeline']
			: ['predict', 'prediction', 'strategy'];

	return jobs.filter((job) => {
		const config = job.config ?? {};
		const haystack = [
			job.name,
			job.task_type,
			String(config.source_page ?? ''),
			String(config.area ?? '')
		]
			.join(' ')
			.toLowerCase();

		return tokens.some((token) => haystack.includes(token));
	});
}

export function cronFromInterval(value: string, unit: string): string {
	const interval = Math.max(1, Number.parseInt(value, 10) || 1);
	const normalizedUnit = unit.toLowerCase();

	if (normalizedUnit.startsWith('week')) return '0 0 * * 1';
	if (normalizedUnit.startsWith('day')) return `0 0 */${interval} * *`;
	return `0 */${interval} * * *`;
}

export function describeScheduledJob(job: ScheduledJob): string {
	const state = job.enabled ? 'running' : 'paused';
	return `${job.name} · ${state} · ${job.cron_expression}`;
}
