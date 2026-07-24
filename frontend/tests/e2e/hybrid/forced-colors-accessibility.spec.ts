import { expect, test } from '@playwright/test';

test('login submit button retains a visible focus indicator in forced colors', async ({ page }) => {
	await page.emulateMedia({ forcedColors: 'active' });
	await page.goto('/login');
	const submit = page.getByRole('button', { name: 'Autentificare', exact: true });
	await submit.focus();
	await page.keyboard.press('Shift+Tab');
	await page.keyboard.press('Tab');
	await expect(submit).toBeFocused();

	const focusIndicator = await submit.evaluate((element) => {
		const style = getComputedStyle(element);
		return {
			outlineStyle: style.outlineStyle,
			outlineWidth: Number.parseFloat(style.outlineWidth)
		};
	});
	expect(focusIndicator.outlineStyle).not.toBe('none');
	expect(focusIndicator.outlineWidth).toBeGreaterThanOrEqual(2);
});
