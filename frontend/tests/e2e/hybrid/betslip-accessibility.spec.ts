import { expect, test, type Page } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { seedHybridFixtures } from '../helpers/seed';

async function addSelectionToBetslip(page: Page, matchLabel: string) {
	await page.goto('/');
	await page.getByRole('tab', { name: /^Today\b/ }).click();
	await page.getByRole('button', { name: `Selectează 1 pentru ${matchLabel}`, exact: true }).click();
}

async function openTicketsWithSelection(page: Page, matchLabel: string) {
	await addSelectionToBetslip(page, matchLabel);
	await page
		.locator('nav[aria-label="Navigarea principală a spațiului de lucru"]')
		.getByRole('link', { name: 'Bilete', exact: true })
		.click();
}

async function readMobileActionGeometry(page: Page) {
	return page.evaluate(() => {
		const nav = document.querySelector<HTMLElement>('.mobile-bottom-nav')?.getBoundingClientRect();
		const fab = document
			.querySelector<HTMLElement>('[aria-label="Revizuiește biletul"]')
			?.getBoundingClientRect();
		const sticky = document
			.querySelector<HTMLElement>('[data-testid="tickets-generate-sticky-cta"]')
			?.getBoundingClientRect();
		const main = document.querySelector<HTMLElement>('main');
		return {
			clientWidth: document.documentElement.clientWidth,
			scrollWidth: document.documentElement.scrollWidth,
			viewportHeight: window.innerHeight,
			mainPaddingBottom: main ? Number.parseFloat(getComputedStyle(main).paddingBottom) : null,
			nav: nav ? { top: nav.top, bottom: nav.bottom, height: nav.height } : null,
			fab: fab ? { bottom: fab.bottom } : null,
			sticky: sticky ? { bottom: sticky.bottom } : null
		};
	});
}

test('betslip drawer is a keyboard modal and restores focus to its trigger', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);
		await addSelectionToBetslip(page, fixtures.scheduledMatchLabel);

		const trigger = page.getByLabel('Revizuiește biletul', { exact: true });
		await trigger.click();

		const dialog = page.getByRole('dialog', { name: 'SLIP DE PARIURI' });
		const close = dialog.getByRole('button', { name: 'Închide slipul de pariuri' });
		await expect(dialog).toBeVisible();
		await expect(close).toBeFocused();
		await expect(page.getByTestId('app-background')).toHaveAttribute('aria-hidden', 'true');
		await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('hidden');

		await page.keyboard.press('Shift+Tab');
		expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
		await page.keyboard.press('Tab');
		await expect(close).toBeFocused();
		await page.locator('#main-content').focus();
		expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
		await page.keyboard.press('Escape');

		await expect(dialog).toBeHidden();
		await expect(trigger).toBeFocused();
		await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('');
	} finally {
		await cleanupSessionArtifacts(session);
	}
});

test('mobile landscape keeps floating ticket actions above the bottom navigation', async ({
	page,
	context
}) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);
		await page.setViewportSize({ width: 844, height: 390 });
		await openTicketsWithSelection(page, fixtures.scheduledMatchLabel);

		const fab = page.getByRole('button', { name: 'Revizuiește biletul' });
		const stickyAction = page.getByTestId('tickets-generate-sticky-cta');
		await expect(fab).toBeVisible();
		await expect(stickyAction).toBeVisible();

		const geometry = await readMobileActionGeometry(page);
		expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth);
		expect(geometry.nav).not.toBeNull();
		expect(geometry.fab).not.toBeNull();
		expect(geometry.sticky).not.toBeNull();
		expect(geometry.fab?.bottom).toBeLessThanOrEqual((geometry.nav?.top ?? 0) - 4);
		expect(geometry.sticky?.bottom).toBeLessThanOrEqual((geometry.nav?.top ?? 0) - 4);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});

test('mobile shell reserves a simulated bottom safe-area inset', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);
		await page.setViewportSize({ width: 390, height: 844 });
		await openTicketsWithSelection(page, fixtures.scheduledMatchLabel);
		await page.evaluate(() => {
			document.documentElement.style.setProperty('--safe-area-bottom', '34px');
		});
		await expect(page.getByRole('button', { name: 'Revizuiește biletul' })).toBeVisible();
		await expect(page.getByTestId('tickets-generate-sticky-cta')).toBeVisible();

		const geometry = await readMobileActionGeometry(page);
		expect(geometry.nav).not.toBeNull();
		expect(geometry.nav?.bottom).toBe(geometry.viewportHeight);
		expect(geometry.nav?.height).toBe(98);
		expect(geometry.mainPaddingBottom).toBeGreaterThanOrEqual(98);
		expect(geometry.fab).not.toBeNull();
		expect(geometry.sticky).not.toBeNull();
		expect(geometry.fab?.bottom).toBeLessThanOrEqual((geometry.nav?.top ?? 0) - 4);
		expect(geometry.sticky?.bottom).toBeLessThanOrEqual((geometry.nav?.top ?? 0) - 4);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});

test('mobile betslip FAB clears the sticky ticket-generation action and icon sidebar links keep names', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);
		await page.setViewportSize({ width: 390, height: 844 });
		await openTicketsWithSelection(page, fixtures.scheduledMatchLabel);

		const fab = page.getByRole('button', { name: 'Revizuiește biletul' });
		const stickyAction = page.getByTestId('tickets-generate-sticky-cta');
		await expect(fab).toBeVisible();
		await expect(stickyAction).toBeVisible();
		const boxes = await Promise.all([fab.boundingBox(), stickyAction.boundingBox()]);
		expect(boxes[0]).not.toBeNull();
		expect(boxes[1]).not.toBeNull();
		const [fabBox, stickyBox] = boxes as [NonNullable<typeof boxes[0]>, NonNullable<typeof boxes[1]>];
		expect(fabBox.y + fabBox.height).toBeLessThanOrEqual(stickyBox.y);

		await page.setViewportSize({ width: 1024, height: 900 });
		await page.goto('/analyze');
		const sidebar = page.locator('aside[aria-label="Navigarea spațiului de lucru"]');
		await expect(sidebar.getByRole('link', { name: 'Analiză', exact: true })).toHaveAttribute(
			'aria-label',
			'Analiză'
		);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
