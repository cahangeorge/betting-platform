import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

test('core authenticated workspace navigation works across supported browser engines', async ({
	page,
	context
}) => {
	const session = await createAuthenticatedSession(context);

	try {
		await page.goto('/tickets');
		await expect(page.getByRole('heading', { name: 'Bilete', exact: true })).toBeVisible();
		await expect(
			page.getByRole('button', { name: new RegExp(session.user.name ?? session.user.email, 'i') })
		).toBeVisible();

		await page.getByRole('link', { name: 'Pregătire' }).first().click();
		await expect(page).toHaveURL(/\/prepare$/);
		await expect(page.getByRole('heading', { name: 'Pregătește datele meciurilor', exact: true })).toBeVisible();

		await page.getByRole('link', { name: 'Analiză' }).first().click();
		await expect(page).toHaveURL(/\/analyze$/);
		await expect(page.getByRole('heading', { name: 'Analiză', exact: true })).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
