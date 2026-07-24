import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { seedHybridFixtures, setBankrollBalance } from '../helpers/seed';

test('manual ticket with a stale client stake shows the server policy validation error', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);
		await setBankrollBalance(session.bankroll.id, 5);

		await page.goto('/tickets');
		const clearSlipButton = page.getByRole('button', { name: 'Golește selecțiile' });
		if (await clearSlipButton.isVisible().catch(() => false)) {
			await clearSlipButton.click();
		}

		await page.goto('/');
		await page.waitForLoadState('networkidle');
		const futureTab = page.getByRole('tab', { name: /^Today\b/ });
		await futureTab.click();
		await expect(page.getByRole('heading', { name: 'Meciuri și predicții viitoare' })).toBeVisible();
		await expect(page.getByText(fixtures.scheduledMatchLabel).first()).toBeVisible();
		await page
			.getByRole('button', { name: `Selectează 1 pentru ${fixtures.scheduledMatchLabel}`, exact: true })
			.click();
		await page.getByRole('button', { name: 'Revizuiește biletul' }).first().click();

		await expect(page).toHaveURL(/\/tickets$/);
		await expect(page.getByTestId('tickets-panel')).toHaveAttribute('data-interactive', 'true');
		const placeBetTab = page.getByRole('tab', { name: 'Generează bilete' });
		await expect(placeBetTab).toBeVisible();
		await expect(placeBetTab).toHaveAttribute('data-state', 'active');
		await expect(placeBetTab).toContainText('1');

		await page.getByRole('button', { name: 'Înregistrează biletul în platformă' }).click();

		await expect(page.getByText('Manual ticket is blocked by the risk policy')).toBeVisible();
		await expect(placeBetTab).toHaveAttribute('data-state', 'active');
		const activeTab = page.getByRole('tab', { name: 'Active' });
		await expect(activeTab).toBeVisible();
		await expect(activeTab).toContainText('1');
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
