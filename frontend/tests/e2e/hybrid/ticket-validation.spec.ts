import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { seedHybridFixtures, setBankrollBalance } from '../helpers/seed';

test('placing a ticket with insufficient bankroll shows the backend validation error', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);
		await setBankrollBalance(session.bankroll.id, 5);

		await page.goto('/tickets');
		const clearSlipButton = page.getByRole('button', { name: 'Clear Slip' });
		if (await clearSlipButton.isVisible().catch(() => false)) {
			await clearSlipButton.click();
		}

		await page.goto('/');
		await expect(page.getByText(fixtures.scheduledMatchLabel).first()).toBeVisible();
		await page.getByRole('button', { name: /1\s+1\.91/ }).first().click();
		await page.getByRole('button', { name: 'Review Ticket' }).first().click();

		await expect(page).toHaveURL(/\/tickets$/);
		await expect(page.getByRole('tab', { name: /Place Bet 1/ })).toBeVisible();

		await page.getByRole('button', { name: 'Place Ticket' }).click();

		await expect(page.getByText('Insufficient bankroll balance')).toBeVisible();
		await expect(page.getByRole('tab', { name: /Place Bet 1/ })).toBeVisible();
		await expect(page.getByRole('tab', { name: /Active 1/ })).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
