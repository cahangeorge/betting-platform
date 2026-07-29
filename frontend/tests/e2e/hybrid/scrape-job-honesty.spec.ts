import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { backendProbe, withBearerToken } from '../helpers/backend';
import { runDirectSql, skipIfDirectDatabaseFixturesUnavailable } from '../helpers/database';
import { executeScrapeJob } from '../helpers/scrape';

test('scrape API rejects unsupported job types instead of fabricating completion', async ({ context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		const result = await backendProbe('/api/v1/data/scrape', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				...withBearerToken(session.token.access_token)
			},
			body: JSON.stringify({
				job_type: `e2e-noop-${session.namespace}`,
				params: { command: 'noop' }
			})
		});

		expect(result.status).toBe(422);
		expect('error' in result ? result.error.detail : '').toContain('Unsupported generic scrape job type');
	} finally {
		await cleanupSessionArtifacts(session);
	}
});

test('Prepare shows the real terminal state of a supported scraper job', async ({ page, context }) => {
	skipIfDirectDatabaseFixturesUnavailable();
	const session = await createAuthenticatedSession(context);
	let jobId: number | null = null;

	try {
		const insertedId = await runDirectSql(`
			INSERT INTO scrape_jobs (job_type, status, params)
			VALUES (
				'refresh_results',
				'pending',
				'{"command":"upcoming","sport":"football","_created_by_user_id":${session.user.id},"e2e_namespace":"${session.namespace}"}'::jsonb
			)
			RETURNING id;
		`);
		jobId = Number.parseInt(insertedId, 10);
		expect(jobId).toBeGreaterThan(0);

		const terminalJob = await executeScrapeJob(session, jobId);
		expect(terminalJob.status).toBe('failed');
		expect(terminalJob.error).toContain('missing source match links');

		await page.goto('/prepare');
		const jobRow = page.getByRole('row').filter({ hasText: 'refresh_results' }).first();
		await expect(jobRow.getByText('refresh_results', { exact: true })).toBeVisible();
		await expect(jobRow.getByText('eșuat', { exact: true })).toBeVisible();
	} finally {
		if (jobId !== null) {
			await runDirectSql(`DELETE FROM scrape_jobs WHERE id = ${jobId};`);
		}
		await cleanupSessionArtifacts(session);
	}
});
