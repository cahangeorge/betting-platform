import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';

test('skip link moves keyboard focus to the main content', async ({ page }) => {
	await page.goto('/about');

	await page.keyboard.press('Tab');
	const skipLink = page.getByRole('link', { name: 'Sari la conținutul principal' });
	await expect(skipLink).toBeFocused();
	await page.keyboard.press('Enter');

	await expect(page.locator('#main-content')).toBeFocused();
});

test('command palette traps focus and keyboard selection navigates', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		await page.goto('/');
		await expect(page.getByText('Conectat', { exact: true })).toBeVisible();
		const trigger = page.getByRole('button', { name: 'Deschide paleta de navigare' });
		await trigger.click();

		const dialog = page.getByRole('dialog', { name: 'Navigare rapidă' });
		const search = page.getByRole('textbox', { name: 'Caută pagini, meciuri și acțiuni' });
		await expect(dialog).toBeVisible();
		await expect(search).toBeFocused();

		await page.keyboard.press('Shift+Tab');
		expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);

		await search.fill('Tickets');
		await search.press('Enter');
		await expect(page).toHaveURL(/\/tickets$/);

		await page.goto('/');
		await expect(page.getByText('Conectat', { exact: true })).toBeVisible();
		await page.keyboard.press('Alt+K');
		const reopenedDialog = page.getByRole('dialog', { name: 'Navigare rapidă' });
		const reopenedSearch = page.getByRole('textbox', { name: 'Caută pagini, meciuri și acțiuni' });
		await expect(reopenedDialog).toBeVisible();

		for (let index = 0; index < 5; index += 1) await reopenedSearch.press('ArrowDown');
		await expect(reopenedDialog.getByRole('button', { name: /Run analysis/ })).toHaveClass(/text-football-green/);

		await reopenedSearch.press('Escape');
		await trigger.click();
		const focusedSearch = page.getByRole('textbox', { name: 'Caută pagini, meciuri și acțiuni' });
		await expect(focusedSearch).toBeFocused();
		await focusedSearch.press('Tab');
		await page.keyboard.press('Tab');
		const prepareCommand = page.getByRole('dialog', { name: 'Navigare rapidă' }).getByRole('button', {
			name: /Prepare data/
		});
		await expect(prepareCommand).toBeFocused();
		await prepareCommand.press('Enter');
		await expect(page).toHaveURL(/\/prepare$/);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
