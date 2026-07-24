import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { seedHybridFixtures } from '../helpers/seed';

test('Analyze exposes the current workflow and generated predictions remain visible in Data Hub', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);

		await page.goto('/analyze');
		await expect(page.getByRole('heading', { name: 'Analiză', exact: true })).toBeVisible();
		await expect(page.getByRole('heading', { name: '1. Date pregătite' })).toBeVisible();
		await expect(page.getByRole('heading', { name: '2. Strategii' })).toBeVisible();
		await expect(page.getByRole('heading', { name: '3. Piețe și opțiuni' })).toBeVisible();

		await page.goto('/data');
		await expect(page.getByRole('heading', { name: 'Data Hub' })).toBeVisible();
		await page.waitForLoadState('networkidle');

		const predictionsTab = page.getByRole('tab', { name: 'Predictions' });
		await expect(predictionsTab).toBeVisible();
		await predictionsTab.click();
		await expect(predictionsTab).toHaveAttribute('data-state', 'active');

		await expect(page.getByText(fixtures.scheduledMatchLabel).first()).toBeVisible({ timeout: 20_000 });
		await expect(page.getByText('PoissonGoalsModel').first()).toBeVisible();
		await expect(page.getByText('reliable').first()).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
