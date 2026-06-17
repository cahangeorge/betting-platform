import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { backendProbe, backendRequest, poll, withBearerToken } from '../helpers/backend';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

test('account page uses the authenticated user bankroll context', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);
	const bookmaker = `Orbit Exchange ${session.namespace}`;
	const accountName = `Primary ${session.namespace}`;

	try {
		await poll(
			async () =>
				await backendProbe(`/api/v1/bankroll/${session.bankroll.id}`, {
					headers: withBearerToken(session.token.access_token)
				}),
			(result) => result.status === 200,
			10_000,
			250
		);

		await backendRequest(`/api/v1/bankroll/${session.bankroll.id}/accounts`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				...withBearerToken(session.token.access_token)
			},
			body: JSON.stringify({
				bookmaker,
				account_name: accountName,
				balance: 245.5
			})
		});

		await page.goto('/account');

		await expect(page.getByRole('heading', { name: 'ACCOUNT' })).toBeVisible();
		await expect(page.getByText(session.bankroll.name).first()).toBeVisible();
		await page.getByRole('tab', { name: /Bookmaker Accounts/i }).click();
		await expect(page.getByRole('tabpanel').getByText(bookmaker).first()).toBeVisible();
		await expect(page.getByRole('tabpanel').getByText(accountName).first()).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
