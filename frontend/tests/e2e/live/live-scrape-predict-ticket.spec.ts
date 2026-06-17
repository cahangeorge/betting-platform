import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { createScrapeJob, executeScrapeJob, waitForScrapeTerminalState } from '../helpers/scrape';

test('@live full scrape flow surfaces a real job terminal state', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);
	const job = await createScrapeJob(session, 'scrape_odds', {
		params: {
			scope: 'live',
			namespace: session.namespace
		}
	});

	try {
		await executeScrapeJob(session, job.id);
		const finalJob = await waitForScrapeTerminalState(session, job.id, 240_000);

		await page.goto('/scrape');
		await expect(page.getByText(`scrape_odds`)).toBeVisible();
		await expect(page.getByText(new RegExp(finalJob.status, 'i')).first()).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
