import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

const draft = {
	legs: [
		{
			id: '9001-1x2-home',
			matchId: 9001,
			matchName: 'PWA Draft Home vs Away',
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

async function waitForActiveServiceWorker(page: import('@playwright/test').Page) {
	await page.evaluate(async () => {
		await navigator.serviceWorker.ready;
	});
	if (!(await page.evaluate(() => navigator.serviceWorker.controller !== null))) {
		await page.reload();
	}
	await expect
		.poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null))
		.toBe(true);
}

test('production HTTPS PWA installs a public-only cache and serves the truthful offline fallback', async ({
	page,
	context
}) => {
	await page.goto('/about');
	await waitForActiveServiceWorker(page);

	const manifestHref = await page.locator('link[rel="manifest"]').getAttribute('href');
	expect(manifestHref).toBe('/manifest.json');
	const manifestResponse = await page.request.get('/manifest.json');
	expect(manifestResponse.ok()).toBe(true);

	const cacheSnapshot = await page.evaluate(async () => {
		const keys = (await caches.keys()).filter((key) => key.startsWith('betfront-'));
		const entries = (
			await Promise.all(
				keys.map(async (key) => {
					const cache = await caches.open(key);
					return Promise.all((await cache.keys()).map((request) => new URL(request.url).pathname));
				})
			)
		).flat();
		return { keys, entries };
	});
	expect(cacheSnapshot.keys).toHaveLength(1);
	expect(cacheSnapshot.entries).toContain('/offline.html');
	expect(cacheSnapshot.entries.some((path) => path.startsWith('/api/'))).toBe(false);

	await context.setOffline(true);
	await page.goto(`/offline-proof-${Date.now()}`);
	await expect(page.getByRole('heading', { name: 'Bet este temporar deconectat' })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Reîncearcă' })).toBeVisible();
	await context.setOffline(false);
});

test('production PWA announces offline state and recovery', async ({
	page,
	context
}) => {
	await page.goto('/about');
	await waitForActiveServiceWorker(page);

	await context.setOffline(true);
	await expect(page.getByRole('status')).toContainText('Mod offline.');

	await context.setOffline(false);
	await expect(page.getByRole('status')).toContainText('Conexiune restabilită.');
	await expect(page.getByRole('status')).toContainText('Bet nu retrimite automat');
});

test('a production service-worker update asks before reload and preserves the active betslip draft', async ({
	page,
	context
}) => {
	const session = await createAuthenticatedSession(context);
	await context.addCookies([
		{
			name: 'access_token',
			value: session.token.access_token,
			url: 'https://127.0.0.1:4173',
			httpOnly: true,
			sameSite: 'Lax',
			secure: true
		}
	]);

	try {
		await page.goto('/about');
		await waitForActiveServiceWorker(page);
		await page.evaluate(
			({ value, userId }) => {
				sessionStorage.setItem(`bet:betslip-draft:v2:user:${userId}`, JSON.stringify(value));
			},
			{ value: draft, userId: session.user.id }
		);
		await page.reload();

		await page.evaluate(async () => {
			const registration = await navigator.serviceWorker.register(
				`/pwa-test-update-sw.js?version=${Date.now()}`,
				{ scope: '/' }
			);
			await new Promise<void>((resolve, reject) => {
				const deadline = window.setTimeout(
					() => reject(new Error('Timed out waiting for the PWA update worker')),
					15_000
				);
				const inspect = () => {
					if (registration.waiting) {
						window.clearTimeout(deadline);
						resolve();
						return;
					}
					window.setTimeout(inspect, 100);
				};
				inspect();
			});
			document.dispatchEvent(new Event('visibilitychange'));
		});

		await expect(page.getByText('Actualizare disponibilă')).toBeVisible();
		await expect(page.getByText(/Biletul curent este păstrat/)).toBeVisible();

		page.once('dialog', async (dialog) => {
			expect(dialog.message()).toContain('bilet nefinalizat');
			await dialog.dismiss();
		});
		await page.getByRole('button', { name: 'Reîncarcă' }).click();
		await expect(page.getByText('Actualizare disponibilă')).toBeVisible();

		const reloaded = page.waitForEvent('load');
		page.once('dialog', async (dialog) => {
			expect(dialog.message()).toContain('bilet nefinalizat');
			await dialog.accept();
		});
		await page.getByRole('button', { name: 'Reîncarcă' }).click();
		await reloaded;

		const restoredDraft = await page.evaluate((userId) =>
			JSON.parse(sessionStorage.getItem(`bet:betslip-draft:v2:user:${userId}`) ?? 'null'),
			session.user.id
		);
		expect(restoredDraft).toEqual(draft);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
