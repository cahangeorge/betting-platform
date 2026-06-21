import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { seedHybridFixtures } from '../helpers/seed';

test('Data Hub tickets tab shows seeded tickets with ticket type and leg match details', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);

		await page.goto('/data');
		await expect(page.getByRole('heading', { name: 'Data Hub' })).toBeVisible();
		await page.waitForLoadState('networkidle');

		const ticketsTab = page.getByRole('tab', { name: 'Tickets' });
		await expect(ticketsTab).toBeVisible();
		await ticketsTab.click();
		await expect(ticketsTab).toHaveAttribute('data-state', 'active');

		await expect(page.getByText(`TKT-${fixtures.seededTicketId}`).first()).toBeVisible({
			timeout: 20_000
		});
		await expect(page.getByRole('cell', { name: 'single' }).first()).toBeVisible();

		await page.getByText(`TKT-${fixtures.seededTicketId}`).first().click();

		await expect(page.getByRole('heading', { name: 'Tickets Detail' })).toBeVisible();
		await expect(page.getByText(fixtures.scheduledMatchLabel)).toBeVisible();
		await expect(page.getByText('1x2 · home · Betfair')).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
