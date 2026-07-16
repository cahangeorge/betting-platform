import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

test('authenticated user can open the dashboard with a real backend session', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		await page.goto('/');

		await expect(page).toHaveURL(/\/$/);
		await expect(page.getByRole('heading', { name: 'Deciziile de azi' })).toBeVisible();
		const todayTab = page.getByRole('tab', { name: /^Today\b/ });
		await expect(todayTab).toHaveAttribute('aria-selected', 'true');
		await expect(page.getByRole('tabpanel', { name: 'Today' })).toBeVisible();
		await expect(page.getByRole('heading', { name: 'Meciuri și predicții viitoare' })).toBeVisible();
		await expect(page.getByRole('button', { name: new RegExp(session.user.name ?? session.user.email, 'i') })).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
