import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { addOddsEntryForMatch, seedHybridFixtures } from '../helpers/seed';

test('public board keeps match content visible after odds comparison hydration', async ({
	page,
	context
}) => {
	const runtimeErrors: string[] = [];
	page.on('pageerror', (error) => runtimeErrors.push(error.message));
	page.on('console', (message) => {
		if (message.type() === 'warning' && message.text().includes('Failed to hydrate')) {
			runtimeErrors.push(message.text());
		}
	});

	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);
		await addOddsEntryForMatch(fixtures.scheduledMatchId, {
			bookmaker: 'Betano',
			homeOdds: 1.94,
			drawOdds: 3.35,
			awayOdds: 4.2
		});
		await addOddsEntryForMatch(fixtures.scheduledMatchId, {
			bookmaker: 'Fortuna',
			homeOdds: 1.89,
			drawOdds: 3.5,
			awayOdds: 4.05
		});

		await context.clearCookies();
		await page.goto('/board');
		await expect(page.getByRole('heading', { name: 'ODDS BOARD' })).toBeVisible();
		await expect(page.getByText(fixtures.scheduledMatchLabel.split(' vs ')[0]).first()).toBeVisible();
		await expect(page.getByLabel('Odds comparison by bookmaker').first()).toBeVisible();

		await page.waitForTimeout(1_000);
		expect(runtimeErrors).toEqual([]);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
