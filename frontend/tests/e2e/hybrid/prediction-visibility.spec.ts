import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { seedHybridFixtures } from '../helpers/seed';

test('generated predictions are visible on Predict and Data Hub pages', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);

		await page.goto('/predict');
		await expect(page.getByRole('heading', { name: 'PREDICTIONS' })).toBeVisible();
		await expect(page.getByRole('heading', { name: 'Recent Prediction Runs' }).first()).toBeVisible();
		await expect(page.getByText(`Run #${fixtures.predictionRunId}`).first()).toBeVisible();
		await expect(page.getByRole('heading', { name: 'Model Predictions' }).first()).toBeVisible();
		await expect(page.getByText(fixtures.scheduledMatchLabel).first()).toBeVisible();
		await expect(page.getByText('reliable').first()).toBeVisible();
		await expect(page.getByText('ticket eligible').first()).toBeVisible();

		await page.goto('/data');
		await page.getByRole('tab', { name: 'Predictions' }).click();
		await expect(page.getByText(fixtures.scheduledMatchLabel).first()).toBeVisible({ timeout: 20_000 });
		await expect(page.getByText('PoissonGoalsModel').first()).toBeVisible();
		await expect(page.getByText('reliable').first()).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
