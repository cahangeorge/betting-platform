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

test('live websocket connects only after the browser has an authenticated layout', async ({ page, context }) => {
	const websocketUrls: string[] = [];
	page.on('websocket', (socket) => websocketUrls.push(socket.url()));

	await page.goto('/about');
	await expect(
		page.getByRole('heading', { name: 'Un flux mai clar pentru analiza pariurilor sportive' })
	).toBeVisible();
	await page.waitForTimeout(250);
	expect(websocketUrls.filter((url) => url.includes('/api/v1/live/ws'))).toEqual([]);

	const session = await createAuthenticatedSession(context);
	try {
		await page.goto('/');
		await expect
			.poll(() => websocketUrls.some((url) => url.includes('/api/v1/live/ws')))
			.toBe(true);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
