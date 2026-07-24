import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { backendProbe, backendRequest, poll, withBearerToken } from '../helpers/backend';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

test('account page uses the authenticated user bankroll context', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);
	const bookmaker = `Orbit Exchange ${session.namespace}`;
	const accountName = `Primary ${session.namespace}`;
	const secondaryBookmaker = `Second Exchange ${session.namespace}`;

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
		const secondaryBankroll = await backendRequest<typeof session.bankroll>('/api/v1/bankroll', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				...withBearerToken(session.token.access_token)
			},
			body: JSON.stringify({
				name: `Secondary ${session.namespace}`,
				type: 'paper',
				currency: 'EUR',
				initial_balance: 500
			})
		});
		await poll(
			async () =>
				await backendProbe(`/api/v1/bankroll/${secondaryBankroll.id}`, {
					headers: withBearerToken(session.token.access_token)
				}),
			(result) => result.status === 200,
			10_000,
			250
		);
		await backendRequest(`/api/v1/bankroll/${secondaryBankroll.id}/accounts`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				...withBearerToken(session.token.access_token)
			},
			body: JSON.stringify({
				bookmaker: secondaryBookmaker,
				account_name: `Secondary account ${session.namespace}`,
				balance: 125
			})
		});

		await page.goto('/account');

		await expect(page.getByRole('heading', { name: 'ACCOUNT', exact: true })).toBeVisible();
		await expect(page.getByText(secondaryBankroll.name).first()).toBeVisible();
		await page.getByRole('tab', { name: /Bookmaker Accounts/i }).click();
		await expect(page.getByRole('tabpanel').getByText(secondaryBookmaker).first()).toBeVisible();
		await expect(page.getByRole('tabpanel').getByText(bookmaker)).toHaveCount(0);

		await page.getByRole('tab', { name: /Risk & limits/i }).click();
		await page
			.getByRole('tabpanel')
			.getByLabel('Bankroll', { exact: true })
			.selectOption(String(session.bankroll.id));
		await page.getByRole('tab', { name: /Bookmaker Accounts/i }).click();
		await expect(page.getByRole('tabpanel').getByText(bookmaker).first()).toBeVisible();
		await expect(page.getByRole('tabpanel').getByText(accountName).first()).toBeVisible();
		await expect(page.getByRole('tabpanel').getByText(secondaryBookmaker)).toHaveCount(0);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
