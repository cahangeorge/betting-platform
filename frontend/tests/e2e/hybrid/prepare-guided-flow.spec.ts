import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

test('Prepare offers a compact preset-first data collection flow', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		await page.goto('/prepare');
		await expect(page.getByRole('heading', { name: 'Pregătește datele meciurilor' })).toBeVisible();
		await expect(page.getByRole('button', { name: 'Top 5 Europa' })).toBeVisible();
		await expect(page.getByRole('button', { name: /Arată toate țările/ })).toBeVisible();

		await page.getByRole('button', { name: 'Top 5 Europa' }).click();

		await expect(page.getByText(/5 ligi · 10 ani de istoric \+ mâine/)).toBeVisible();
		await expect(page.locator('#selection').getByText('Premier League', { exact: true }).first()).toBeVisible();
		await expect(page.locator('#selection details').first()).not.toHaveAttribute('open', '');
		await expect(page.getByRole('button', { name: 'Pornește colectarea' })).toBeEnabled();

		await page.setViewportSize({ width: 390, height: 844 });
		expect(
			await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
		).toBe(true);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
