import { expect, test, type BrowserContext, type Page } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { getE2EEnv } from '../helpers/backend';
import type { AuthSession } from '../helpers/types';

function draft(matchId: number, matchName: string) {
	return {
		legs: [
			{
				id: `${matchId}-1x2-home`,
				matchId,
				matchName,
				market: '1X2',
				marketKey: '1x2',
				selection: 'Home',
				selectionKey: 'home',
				odds: 2.1,
				source: 'dashboard'
			}
		],
		stake: 12,
		ticketType: 'single'
	};
}

function draftKey(userId: number): string {
	return `bet:betslip-draft:v2:user:${userId}`;
}

function betslipFab(page: Page) {
	return page.locator('button[aria-label="Revizuiește biletul"]');
}

async function switchSession(context: BrowserContext, session: AuthSession): Promise<void> {
	await context.addCookies([
		{
			name: 'access_token',
			value: session.token.access_token,
			url: getE2EEnv().frontendURL,
			httpOnly: true,
			sameSite: 'Lax',
			secure: getE2EEnv().frontendURL.startsWith('https://')
		}
	]);
}

async function storeDraft(page: Page, userId: number, value: ReturnType<typeof draft>): Promise<void> {
	await page.evaluate(
		({ key, value }) => sessionStorage.setItem(key, JSON.stringify(value)),
		{ key: draftKey(userId), value }
	);
}

test('same-tab user changes never expose another user’s betslip draft', async ({ page, context }) => {
	const firstUser = await createAuthenticatedSession(context);
	const secondUser = await createAuthenticatedSession(context);

	try {
		await switchSession(context, firstUser);
		await page.goto('/');
		await storeDraft(page, firstUser.user.id, draft(9101, 'First user selection'));
		await page.reload();
		await expect(betslipFab(page)).toBeVisible();

		await switchSession(context, secondUser);
		await page.goto('/');
		await expect(betslipFab(page)).toHaveCount(0);
		expect(
			await page.evaluate((key) => sessionStorage.getItem(key), draftKey(secondUser.user.id))
		).toBeNull();

		await storeDraft(page, secondUser.user.id, draft(9102, 'Second user selection'));
		await page.reload();
		await betslipFab(page).click();
		await expect(page.getByText('Second user selection')).toBeVisible();
		await expect(page.getByText('First user selection')).toHaveCount(0);

		await switchSession(context, firstUser);
		await page.goto('/');
		await betslipFab(page).click();
		await expect(page.getByText('First user selection')).toBeVisible();
		await expect(page.getByText('Second user selection')).toHaveCount(0);
	} finally {
		await cleanupSessionArtifacts(firstUser);
		await cleanupSessionArtifacts(secondUser);
	}
});
