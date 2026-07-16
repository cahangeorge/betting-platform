import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

test('risk policy, model governance, and CLV surfaces are reachable in the authenticated workspace', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		await page.goto('/account');
		await expect(page.getByTestId('account-panel')).toHaveAttribute('data-interactive', 'true');
		await page.getByRole('tab', { name: /Risk & limits/i }).click();
		await expect(page.getByRole('heading', { name: 'Politica de risc' })).toBeVisible();
		await expect(page.getByText('5% / ticket', { exact: true })).toBeVisible();

		await page.goto('/settings/model-governance');
		await expect(page.getByRole('heading', { name: 'Model governance' })).toBeVisible();
		await expect(page.getByText(/ROI-ul singur nu certifică un model/)).toBeVisible();

		await page.goto('/monitoring');
		await expect(page.getByRole('heading', { name: 'Closing line value' })).toBeVisible();
		await expect(page.getByText(/Cota lipsă rămâne lipsă/)).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
