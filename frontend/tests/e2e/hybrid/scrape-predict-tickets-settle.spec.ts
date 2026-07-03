import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { backendRequest, waitFor, withBearerToken } from '../helpers/backend';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { forceScheduledJobDue, markMatchFinished, seedHybridFixtures } from '../helpers/seed';

type StrategyResponse = {
	id: number;
	name: string;
	model_type: string;
};

type ScheduledJobResponse = {
	id: number;
	name: string;
	task_type: string;
	enabled: boolean;
};

type ScheduledRunResult = {
	job_id: number;
	task_type: string;
	status: string;
	detail: string | null;
};

type TicketResponse = {
	id: number;
	status: string;
	batch_id: number | null;
};

test('scheduled scrape -> predict -> tickets flow can be created and later settled successfully', async ({
	page,
	context
}) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);

		const strategy = await backendRequest<StrategyResponse>('/api/v1/strategies', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				...withBearerToken(session.token.access_token)
			},
			body: JSON.stringify({
				name: `E2E Strategy ${session.namespace}`,
				model_type: 'poisson',
				description: 'Hybrid E2E scheduled orchestration strategy',
				parameters: {}
			})
		});

		const orchestrationJob = await backendRequest<ScheduledJobResponse>('/api/v1/jobs', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				...withBearerToken(session.token.access_token)
			},
			body: JSON.stringify({
				name: `E2E orchestration ${session.namespace}`,
				task_type: 'scrape_predict_tickets',
				cron_expression: '0 */1 * * *',
				config: {
					source_page: 'scrape',
					area: 'orchestration',
					workflow: 'scrape_predict_tickets',
					params: {
						command: 'noop',
						countries: [],
						leagues: []
					},
					prediction: {
						strategy_ids: [strategy.id],
						match_ids: [fixtures.scheduledMatchId],
						markets: ['1x2'],
						avoid_reprediction: true
					},
					tickets: {
						bankroll_id: session.bankroll.id,
						ticket_count: 1,
						difficulty: 'safe',
						market_types: ['1x2'],
						min_odds: 1.01,
						max_odds: 10,
						stake: 10
					}
				}
			})
		});

		const verificationJob = await backendRequest<ScheduledJobResponse>('/api/v1/jobs', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				...withBearerToken(session.token.access_token)
			},
			body: JSON.stringify({
				name: `E2E verification ${session.namespace}`,
				task_type: 'verify_results',
				cron_expression: '0 */1 * * *',
				config: {
					source_page: 'tickets',
					area: 'verification',
					verify_predictions: false,
					settle_tickets: true,
					ticket_limit: 50
				}
			})
		});

		await page.goto('/scrape');
		await expect(page.getByText(orchestrationJob.name).first()).toBeVisible();

		await page.goto('/tickets');
		await expect(page.getByText(verificationJob.name).first()).toBeVisible();

		await forceScheduledJobDue(orchestrationJob.id);
		const firstRun = await backendRequest<ScheduledRunResult[]>('/api/v1/jobs/run-due?limit=10', {
			method: 'POST',
			headers: withBearerToken(session.token.access_token)
		});

		const orchestrationResult = firstRun.find((item) => item.job_id === orchestrationJob.id);
		expect(orchestrationResult?.status).toBe('completed');
		expect(orchestrationResult?.detail ?? '').toContain('scrape_job:');
		expect(orchestrationResult?.detail ?? '').toContain('predictions:');
		expect(orchestrationResult?.detail ?? '').toContain('ticket_batch:');

		const ticketsAfterGeneration = await waitFor(
			async () =>
				await backendRequest<TicketResponse[]>('/api/v1/tickets', {
					headers: withBearerToken(session.token.access_token)
				}),
			(tickets) => tickets.length >= 2,
			10_000,
			500
		);
		expect(ticketsAfterGeneration.length).toBeGreaterThanOrEqual(2);
		const generatedTicket = ticketsAfterGeneration.find(
			(ticket) => ticket.id !== fixtures.seededTicketId && ticket.batch_id !== null
		);
		expect(generatedTicket).toBeTruthy();

		await markMatchFinished(fixtures.scheduledMatchId, {
			homeScore: 2,
			awayScore: 0,
			status: 'finished'
		});
		await markMatchFinished(fixtures.liveMatchId, {
			homeScore: 2,
			awayScore: 1,
			status: 'finished'
		});

		await forceScheduledJobDue(verificationJob.id);
		const secondRun = await backendRequest<ScheduledRunResult[]>('/api/v1/jobs/run-due?limit=10', {
			method: 'POST',
			headers: withBearerToken(session.token.access_token)
		});

		const verificationResult = secondRun.find((item) => item.job_id === verificationJob.id);
		expect(verificationResult?.status).toBe('completed');
		expect(verificationResult?.detail ?? '').toContain('tickets=');

		const ticketsAfterSettlement = await backendRequest<TicketResponse[]>('/api/v1/tickets', {
			headers: withBearerToken(session.token.access_token)
		});
		const settledGeneratedTicket = ticketsAfterSettlement.find((ticket) => ticket.id === generatedTicket?.id);
		expect(settledGeneratedTicket?.status).toMatch(/won|lost|void/);

		await page.goto('/tickets');
		await expect(page.getByRole('heading', { name: 'TICKETS', exact: true })).toBeVisible();
		await expect(page.getByText(verificationJob.name).first()).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
