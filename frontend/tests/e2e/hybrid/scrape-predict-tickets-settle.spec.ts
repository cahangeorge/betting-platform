import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { backendRequest, waitFor, withBearerToken } from '../helpers/backend';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { forceScheduledJobDue, markMatchFinished, seedHybridFixtures } from '../helpers/seed';

type ScheduledJobResponse = {
	id: number;
	name: string;
	task_type: string;
	enabled: boolean;
};

type ScheduledRunResult = {
	id: number | null;
	job_id: number;
	task_type: string;
	status: string;
	detail: string | null;
	error?: string | null;
};

type TicketResponse = {
	id: number;
	status: string;
	batch_id: number | null;
};

test('scheduled ticket drafts and result settlement remain separate until explicit activation', async ({
	page,
	context
}) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);

		const generationJob = await backendRequest<ScheduledJobResponse>('/api/v1/jobs', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				...withBearerToken(session.token.access_token)
			},
			body: JSON.stringify({
				name: `E2E ticket generation ${session.namespace}`,
				task_type: 'generate_tickets',
				cron_expression: '0 */1 * * *',
				config: {
					source_page: 'tickets',
					area: 'generation',
					workflow: 'ticket_draft_generation',
					bankroll_id: session.bankroll.id,
					run_id: fixtures.predictionRunId,
					ticket_count: 1,
					difficulty: 'safe',
					market_types: ['1x2'],
					min_odds: 1.01,
					max_odds: 10
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

		await page.goto('/tickets');
		await expect(page.getByTestId('tickets-panel')).toHaveAttribute('data-interactive', 'true');
		await page.getByRole('tab', { name: 'Active' }).click();
		await page.getByText('Automatizare verificare', { exact: true }).click();
		await expect(page.getByText(verificationJob.name).first()).toBeVisible();

		await forceScheduledJobDue(generationJob.id);
		const firstRun = await backendRequest<ScheduledRunResult[]>('/api/v1/jobs/run-due?limit=10', {
			method: 'POST',
			headers: withBearerToken(session.token.access_token)
		});

		const queuedGenerationRun = firstRun.find((item) => item.job_id === generationJob.id);
		expect(queuedGenerationRun?.id).toBeTruthy();
		const generationResult = await waitFor(
			async () =>
				await backendRequest<ScheduledRunResult>(`/api/v1/job-runs/${queuedGenerationRun?.id}`, {
					headers: withBearerToken(session.token.access_token)
				}),
			(run) => ['completed', 'failed', 'cancelled'].includes(run.status),
			120_000,
			500
		);
		expect(
			generationResult?.status,
			`generation failed: ${generationResult?.detail ?? generationResult?.error ?? 'no detail'}`
		).toBe('completed');
		expect(generationResult?.detail ?? '').toContain('ticket_batch:');

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
		expect(generatedTicket?.status).toBe('generated');

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

		const queuedVerificationRun = secondRun.find((item) => item.job_id === verificationJob.id);
		expect(queuedVerificationRun?.id).toBeTruthy();
		const verificationResult = await waitFor(
			async () =>
				await backendRequest<ScheduledRunResult>(`/api/v1/job-runs/${queuedVerificationRun?.id}`, {
					headers: withBearerToken(session.token.access_token)
				}),
			(run) => ['completed', 'failed', 'cancelled'].includes(run.status),
			120_000,
			500
		);
		expect(
			verificationResult?.status,
			`verification failed: ${verificationResult?.detail ?? verificationResult?.error ?? 'no detail'}`
		).toBe('completed');
		expect(verificationResult?.detail ?? '').toContain('tickets=');

		const ticketsAfterSettlement = await backendRequest<TicketResponse[]>('/api/v1/tickets', {
			headers: withBearerToken(session.token.access_token)
		});
		const settledSeededTicket = ticketsAfterSettlement.find((ticket) => ticket.id === fixtures.seededTicketId);
		expect(settledSeededTicket?.status).toMatch(/won|lost|void/);
		const unchangedDraftTicket = ticketsAfterSettlement.find((ticket) => ticket.id === generatedTicket?.id);
		expect(unchangedDraftTicket?.status).toBe('generated');

		await page.goto('/tickets');
		await expect(page.getByRole('heading', { name: 'Bilete', exact: true })).toBeVisible();
		await expect(page.getByTestId('tickets-panel')).toHaveAttribute('data-interactive', 'true');
		await page.getByRole('tab', { name: 'Active' }).click();
		await page.getByText('Automatizare verificare', { exact: true }).click();
		await expect(page.getByText(verificationJob.name).first()).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
