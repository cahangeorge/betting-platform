import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { seedHybridFixtures } from '../helpers/seed';

test('dashboard can add a seeded match to the slip and place a ticket', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);

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
		await expect(
			page.getByRole('button', { name: 'Revizuiește biletul' }).first()
		).toBeVisible();

		await page.getByRole('button', { name: 'Revizuiește biletul' }).first().click();
		await expect(page).toHaveURL(/\/tickets$/);
		await expect(page.getByRole('heading', { name: 'Bilete', exact: true })).toBeVisible();
		await expect(page.getByTestId('tickets-panel')).toHaveAttribute('data-interactive', 'true');
		const placeBetTab = page.getByRole('tab', { name: 'Generează bilete' });
		await expect(placeBetTab).toBeVisible();
		await expect(placeBetTab).toContainText('1');
		await page.getByLabel('Miză', { exact: true }).fill('9.90');

		await page.getByRole('button', { name: 'Înregistrează biletul în platformă' }).click();
		const activeTab = page.getByRole('tab', { name: 'Active' });
		await expect(activeTab).toBeVisible();
		await expect(activeTab).toHaveAttribute('data-state', 'active');
		await expect(activeTab).toContainText('2');
		await expect(page.getByRole('tabpanel', { name: 'Active' }).getByText(fixtures.scheduledMatchLabel)).toHaveCount(2);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
