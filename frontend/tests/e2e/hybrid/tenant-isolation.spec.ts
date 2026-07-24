import { expect, test, type BrowserContext } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { backendProbe, backendRequest, withBearerToken } from '../helpers/backend';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { runDirectSql, skipIfDirectDatabaseFixturesUnavailable } from '../helpers/database';
import { seedHybridFixtures } from '../helpers/seed';
import type { AuthSession } from '../helpers/types';

type ScheduledJob = {
	id: number;
	name: string;
};

type PredictionRun = {
	id: number;
};

async function createForeignJob(token: string, namespace: string): Promise<ScheduledJob> {
	return await backendRequest<ScheduledJob>('/api/v1/jobs', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', ...withBearerToken(token) },
		body: JSON.stringify({
			name: `E2E tenant isolation ${namespace}`,
			task_type: 'verify_results',
			cron_expression: '0 */1 * * *',
			config: { source_page: 'tenant-isolation' }
		})
	});
}

test.describe('tenant isolation', () => {
	let owner: AuthSession;
	let other: AuthSession;
	let ownerContext: BrowserContext;
	let otherContext: BrowserContext;

	test.beforeAll(async ({ browser }) => {
		ownerContext = await browser.newContext();
		otherContext = await browser.newContext();
		owner = await createAuthenticatedSession(ownerContext);
		other = await createAuthenticatedSession(otherContext);
	});

	test.afterAll(async () => {
		await ownerContext?.close();
		await otherContext?.close();
		if (owner) await cleanupSessionArtifacts(owner);
		if (other) await cleanupSessionArtifacts(other);
	});

	test('does not let another user read a scheduled job by id', async () => {
		const job = await createForeignJob(owner.token.access_token, owner.namespace);
		const result = await backendProbe(`/api/v1/jobs/${job.id}`, {
			headers: withBearerToken(other.token.access_token)
		});

		expect(result.status).toBe(403);
	});

	test('does not let another user read a prediction run by id', async () => {
		const fixtures = await seedHybridFixtures(owner);
		const result = await backendProbe<PredictionRun>(`/api/v1/predictions/runs/${fixtures.predictionRunId}`, {
			headers: withBearerToken(other.token.access_token)
		});

		expect(result.status).toBe(404);
	});

	test('does not let another user read a bankroll risk policy by id', async () => {
		const result = await backendProbe(`/api/v1/bankroll/${owner.bankroll.id}/risk-policy`, {
			headers: withBearerToken(other.token.access_token)
		});

		expect(result.status).toBe(404);
	});

	test('does not let another user read a trading account health record by id', async () => {
		skipIfDirectDatabaseFixturesUnavailable();
		const accountId = Number(
			await runDirectSql(`
				INSERT INTO trading_accounts (user_id, name, provider, mode, currency, balance, enabled)
				VALUES (${owner.user.id}, 'E2E tenant ${owner.namespace}', 'paper-local', 'paper', 'EUR', 1000, TRUE)
				RETURNING id;
			`)
		);
		const result = await backendProbe(`/api/v1/trading/accounts/${accountId}/health`, {
			headers: withBearerToken(other.token.access_token)
		});

		expect(result.status).toBe(404);
	});

	test('does not let another user settle an owned ticket', async () => {
		skipIfDirectDatabaseFixturesUnavailable();
		const ticketId = Number(
			await runDirectSql(`
				INSERT INTO tickets (
					user_id,
					bankroll_id,
					ticket_type,
					stake,
					total_odds,
					potential_return,
					status
				)
				VALUES (${owner.user.id}, ${owner.bankroll.id}, 'single', 10, 1.91, 19.10, 'open')
				RETURNING id;
			`)
		);
		const result = await backendProbe(`/api/v1/tickets/${ticketId}/settle?outcome=won`, {
			method: 'POST',
			headers: withBearerToken(other.token.access_token)
		});

		expect(result.status).toBe(404);
	});
});
