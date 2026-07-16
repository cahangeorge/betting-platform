import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

test('countries and leagues catalog is usable on desktop, mobile, light and dark themes', async ({
	page,
	context
}, testInfo) => {
	const session = await createAuthenticatedSession(context);

	try {
		await page.setViewportSize({ width: 1440, height: 1000 });
		await page.goto('/settings/countries-leagues');

		await expect(page.getByRole('heading', { name: 'Listare țări/ligi', exact: true })).toBeVisible();
		await expect(page.getByRole('link', { name: 'Listare țări/ligi', exact: true }).first()).toBeVisible();
		await expect(page.getByLabel('Selectare multiplă țări')).toBeVisible();

		const argentina = page.locator('label').filter({ hasText: 'Argentina' }).getByRole('checkbox').first();
		await expect(argentina).toBeVisible();
		await argentina.check();
		await expect(page.getByText(/Vor fi procesate: Argentina/)).toBeVisible();
		await expect(page.getByRole('button', { name: 'Caută și validează ligile' })).toBeDisabled();

		const initialThemeIsDark = await page.locator('html').evaluate((element) => element.classList.contains('dark'));
		await page.screenshot({ path: testInfo.outputPath('countries-leagues-desktop-initial.png') });
		await page
			.getByRole('button', {
				name: initialThemeIsDark ? 'Activează tema luminoasă' : 'Activează tema întunecată'
			})
			.first()
			.click();
		await expect(page.locator('html')).toHaveClass(initialThemeIsDark ? /light/ : /dark/);
		await page.screenshot({ path: testInfo.outputPath('countries-leagues-desktop-toggled.png') });

		await page.setViewportSize({ width: 390, height: 844 });
		await expect(page.getByRole('heading', { name: 'Listare țări/ligi', exact: true })).toBeVisible();
		await page.screenshot({ path: testInfo.outputPath('countries-leagues-mobile-page.png') });
		await page.getByRole('button', { name: 'Deschide meniul lateral' }).click();
		await expect(page.getByRole('link', { name: 'Listare țări/ligi', exact: true }).last()).toBeVisible();
		await page.screenshot({ path: testInfo.outputPath('countries-leagues-mobile-menu.png') });

		const overflow = await page.evaluate(() => ({
			clientWidth: document.documentElement.clientWidth,
			scrollWidth: document.documentElement.scrollWidth
		}));
		expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
