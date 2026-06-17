import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { seedHybridFixtures } from '../helpers/seed';

test('live and value bet pages surface seeded backend data', async ({ page, context }) => {
	const session = await createAuthenticatedSession(context);

	try {
		const fixtures = await seedHybridFixtures(session);
		const [liveHome, liveAway] = fixtures.liveMatchLabel.split(' vs ');
		console.log('live-value-data: seeded');

		await page.goto('/live');
		console.log('live-value-data: goto live');
		await expect(page.getByRole('heading', { name: 'LIVE MATCHES' })).toBeVisible();
		await expect(page.getByText(liveHome).first()).toBeVisible();
		await expect(page.getByText(liveAway).first()).toBeVisible();
		await expect(page.getByRole('button', { name: 'Add to betslip' })).toBeVisible();
		console.log('live-value-data: live ok');

		await page.goto('/value-bets');
		console.log('live-value-data: goto value-bets');
		await expect(page.getByRole('heading', { name: 'VALUE BET FEED' })).toBeVisible();
		await expect(page.getByText(fixtures.scheduledMatchLabel).first()).toBeVisible();
		await expect(page.getByRole('button', { name: 'ADD TO SLIP' }).first()).toBeVisible();
		console.log('live-value-data: value-bets ok');

		await page.goto('/data');
		console.log('live-value-data: goto data');
		await expect(page.getByRole('heading', { name: 'Data Hub' })).toBeVisible();
		await expect(page.getByRole('tab', { name: 'Matches' })).toBeVisible();
		console.log('live-value-data: data ok');
	} finally {
		console.log('live-value-data: cleanup start');
		await page.close().catch(() => undefined);
		await cleanupSessionArtifacts(session);
		console.log('live-value-data: cleanup done');
	}
});
