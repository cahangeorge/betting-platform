import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';

test('authenticated user can open the dashboard with a real backend session', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	await page.goto('/');

	await expect(page).toHaveURL(/\/$/);
	await expect(page.getByRole('heading', { name: 'Rezultate si oportunitati' })).toBeVisible();
	await expect(page.getByRole('heading', { name: 'Bilete castigate / pierdute' })).toBeVisible();
	await expect(page.getByRole('heading', { name: 'Verificare predictii' })).toBeVisible();
	await page.getByRole('tab', { name: /Viitor/ }).click();
	await expect(page.getByRole('heading', { name: 'Meciuri viitoare si predictii' })).toBeVisible();
	await expect(page.getByRole('button', { name: new RegExp(session.user.name ?? session.user.email, 'i') })).toBeVisible();
});
