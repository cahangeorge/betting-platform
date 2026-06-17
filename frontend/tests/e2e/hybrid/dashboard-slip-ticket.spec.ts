import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { seedHybridFixtures } from '../helpers/seed';

test('dashboard can add a seeded match to the slip and place a ticket', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);

		await page.goto('/tickets');
		const clearSlipButton = page.getByRole('button', { name: 'Clear Slip' });
		if (await clearSlipButton.isVisible().catch(() => false)) {
			await clearSlipButton.click();
		}

		await page.goto('/');
		await expect(page.getByRole('heading', { name: 'Upcoming Matches' })).toBeVisible();
		await expect(page.getByText(fixtures.scheduledMatchLabel).first()).toBeVisible();

		await page.getByRole('button', { name: /1\s+1\.91/ }).first().click();
		await expect(page.getByRole('button', { name: 'Review Ticket' }).first()).toBeVisible();

		await page.getByRole('button', { name: 'Review Ticket' }).first().click();
		await expect(page).toHaveURL(/\/tickets$/);
		await expect(page.getByRole('heading', { name: 'TICKETS' })).toBeVisible();
		await expect(page.getByRole('tab', { name: /Place Bet 1/ })).toBeVisible();

		await page.getByRole('button', { name: 'Place Ticket' }).click();
		await expect(page.getByRole('tab', { name: /Active 2/ })).toBeVisible();
		await expect(page.getByRole('tab', { name: /History 2/ })).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
