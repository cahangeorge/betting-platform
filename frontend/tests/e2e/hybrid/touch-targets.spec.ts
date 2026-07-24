import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

test.use({
	hasTouch: true,
	isMobile: true,
	viewport: { width: 390, height: 844 }
});

test('workspace navigation targets are at least 44 CSS pixels on coarse pointers', async ({
	page,
	context
}) => {
	const session = await createAuthenticatedSession(context);

	try {
		await page.goto('/tickets');
		await expect.poll(() => page.evaluate(() => matchMedia('(pointer: coarse)').matches)).toBe(true);
		const navigation = page.getByRole('navigation', {
			name: 'Navigarea principală a spațiului de lucru'
		});
		await expect(navigation).toBeVisible();

		const targets = navigation.locator('a, button');
		expect(await targets.count()).toBeGreaterThan(0);
		for (let index = 0; index < (await targets.count()); index += 1) {
			const target = targets.nth(index);
			await expect(target).toBeVisible();
			const box = await target.boundingBox();
			expect(box, `navigation target ${index + 1} has geometry`).not.toBeNull();
			expect(box?.width, `navigation target ${index + 1} width`).toBeGreaterThanOrEqual(44);
			expect(box?.height, `navigation target ${index + 1} height`).toBeGreaterThanOrEqual(44);
		}

		const menuTrigger = page.getByRole('button', { name: 'Deschide navigarea completă' });
		await expect(menuTrigger).toBeVisible();
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
