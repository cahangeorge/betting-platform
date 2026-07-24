import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

test('workspace shell uses mobile navigation at 768px and the expanded sidebar at 1920px', async ({
	page,
	context
}) => {
	const session = await createAuthenticatedSession(context);

	try {
		await page.setViewportSize({ width: 768, height: 900 });
		await page.goto('/tickets');
		await expect(page.getByRole('heading', { name: 'Bilete', exact: true })).toBeVisible();

		const mobileNav = page.getByRole('navigation', {
			name: 'Navigarea principală a spațiului de lucru'
		});
		const desktopSidebar = page.locator('aside[aria-label="Navigarea spațiului de lucru"]');
		await expect(mobileNav).toBeVisible();
		await expect(desktopSidebar).toBeHidden();

		const mobileGeometry = await page.evaluate(() => {
			const main = document.querySelector('main');
			const nav = document.querySelector('.mobile-bottom-nav')?.getBoundingClientRect();
			return {
				mainPaddingLeft: main ? Number.parseFloat(getComputedStyle(main).paddingLeft) : null,
				navBottom: nav?.bottom ?? null,
				viewportHeight: window.innerHeight
			};
		});
		expect(mobileGeometry.mainPaddingLeft).toBe(0);
		expect(mobileGeometry.navBottom).toBe(mobileGeometry.viewportHeight);

		await page.setViewportSize({ width: 1920, height: 1080 });
		await expect(desktopSidebar).toBeVisible();
		await expect(mobileNav).toBeHidden();

		const desktopGeometry = await page.evaluate(() => {
			const main = document.querySelector('main');
			const sidebar = document.querySelector(
				'aside[aria-label="Navigarea spațiului de lucru"]'
			)?.getBoundingClientRect();
			return {
				mainPaddingLeft: main ? Number.parseFloat(getComputedStyle(main).paddingLeft) : null,
				sidebarRight: sidebar?.right ?? null,
				sidebarWidth: sidebar?.width ?? null
			};
		});
		expect(desktopGeometry.sidebarWidth).toBeGreaterThanOrEqual(240);
		expect(desktopGeometry.mainPaddingLeft).toBe(desktopGeometry.sidebarRight);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
