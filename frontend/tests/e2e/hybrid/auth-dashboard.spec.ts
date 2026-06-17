import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';

test('authenticated user can open the dashboard with a real backend session', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	await page.goto('/');

	await expect(page).toHaveURL(/\/$/);
	await expect(page.getByRole('heading', { name: 'Recent Tickets' })).toBeVisible();
	await expect(page.getByRole('heading', { name: 'Upcoming Matches' })).toBeVisible();
	await expect(page.getByRole('button', { name: new RegExp(session.user.name ?? session.user.email, 'i') })).toBeVisible();
});
