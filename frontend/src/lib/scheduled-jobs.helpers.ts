import type { ScheduledJob } from '$lib/types';

export type ScheduledJobArea = 'scrape' | 'prediction' | 'verification' | 'orchestration' | 'tickets';

function jobHaystack(job: ScheduledJob): string {
	const config = job.config ?? {};
	return [
		job.name,
		job.task_type,
		String(config.source_page ?? ''),
		String(config.area ?? ''),
		String(config.mode ?? ''),
		String(config.workflow ?? '')
	]
		.join(' ')
		.toLowerCase();
}

function matchesAreaTokens(haystack: string, tokens: string[]): boolean {
	return tokens.some((token) => haystack.includes(token));
}

export function scheduledJobsForArea(jobs: ScheduledJob[], area: ScheduledJobArea): ScheduledJob[] {
	const tokensByArea: Record<ScheduledJobArea, string[]> = {
		scrape: ['scrape', 'scraping', 'odds'],
		prediction: ['predict', 'prediction', 'strategy'],
		verification: ['verify', 'verification', 'settlement', 'settle', 'reconcile', 'results'],
		orchestration: [
			'orchestration',
			'pipeline',
			'workflow',
			'scrape_predict',
			'scrape_then_predict',
			'composite'
		],
		tickets: ['ticket', 'tickets', 'slip', 'batch']
	};

	return jobs.filter((job) => {
		const haystack = jobHaystack(job);
		const isVerification = matchesAreaTokens(haystack, tokensByArea.verification);
		const isOrchestration = matchesAreaTokens(haystack, tokensByArea.orchestration);
		const isTickets = matchesAreaTokens(haystack, tokensByArea.tickets);

		if (area === 'verification') return isVerification;
		if (area === 'orchestration') return isOrchestration;
		if (area === 'tickets') return !isOrchestration && isTickets;
		if (area === 'scrape') {
			return !isVerification && !isOrchestration && !isTickets && matchesAreaTokens(haystack, tokensByArea.scrape);
		}
		return !isVerification && !isOrchestration && !isTickets && matchesAreaTokens(haystack, tokensByArea.prediction);
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
