import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupScrapeJobs, cleanupSessionArtifacts } from '../helpers/cleanup';
import { createScrapeJob, executeScrapeJob, waitForScrapeTerminalState } from '../helpers/scrape';

test('scrape page shows the real backend job status', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);
	const jobType = `e2e-noop-${session.namespace}`;

	try {
		const job = await createScrapeJob(session, jobType, {
			params: {
				command: 'noop'
			}
		});

		await executeScrapeJob(session, job.id);
		await waitForScrapeTerminalState(session, job.id, 30_000);

		await page.goto('/scrape');
		await expect(page.getByRole('cell', { name: new RegExp(jobType) }).first()).toBeVisible();
		await expect(page.getByText(/completed|failed/i).first()).toBeVisible();
	} finally {
		await cleanupScrapeJobs(jobType);
		await cleanupSessionArtifacts(session);
	}
});
