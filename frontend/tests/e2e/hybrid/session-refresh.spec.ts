import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { getE2EEnv } from '../helpers/backend';

test('protected SSR navigation rotates a valid refresh-only session', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);
	const { backendURL, frontendURL } = getE2EEnv();

	try {
		const login = await context.request.post(`${backendURL}/api/v1/auth/login`, {
			data: {
				email: session.credentials.email,
				password: session.credentials.password
			}
		});
		expect(login.ok()).toBe(true);
		const refreshCookie = (await context.cookies(frontendURL)).find(
			(cookie) => cookie.name === 'refresh_token'
		);
		const originalRefresh = refreshCookie?.value;
		expect(originalRefresh).toBeTruthy();

		await context.clearCookies();
		await context.addCookies([
			{
				name: 'refresh_token',
				value: originalRefresh!,
				url: frontendURL,
				httpOnly: true,
				sameSite: 'Lax',
				secure: frontendURL.startsWith('https://')
			}
		]);
		expect((await context.cookies(frontendURL)).map((cookie) => cookie.name)).toEqual([
			'refresh_token'
		]);
		await page.goto('/tickets');

		await expect(page).toHaveURL(/\/tickets$/);
		await expect(page.getByRole('heading', { name: 'Bilete', exact: true })).toBeVisible();
		const rotatedCookies = await context.cookies(frontendURL);
		expect(rotatedCookies.some((cookie) => cookie.name === 'access_token')).toBe(true);
		expect(rotatedCookies.find((cookie) => cookie.name === 'refresh_token')?.value).not.toBe(
			originalRefresh
		);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
