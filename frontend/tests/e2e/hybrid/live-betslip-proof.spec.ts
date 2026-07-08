import { expect, test, type Page } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { backendRequest, withBearerToken } from '../helpers/backend';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { seedHybridFixtures } from '../helpers/seed';

type LiveHeartbeatResponse = {
	bridge_ready: boolean;
	bridge_issues: string[];
	source: string;
};

type LiveOverviewResponse = {
	is_demo: boolean;
	is_data_stale: boolean;
	data_age_seconds: number | null;
	matches: Array<{
		id: number;
		home_team: string;
		away_team: string;
		live_value_candidates: Array<{
			selection: string;
			odds: number;
			edge: number;
		}>;
	}>;
};

async function expectLockedLiveCandidateState(page: Page, fixtures: {
	liveHome: string;
	liveAway: string;
}) {
	const main = page.getByRole('main');
	const betSlip = page.getByRole('complementary', { name: 'Bet slip' });
	const staleBanner = main.getByText('Live feed may be stale').first();
	const monitorOnlyBanner = main.getByText('Monitor-only mode for live betslip actions').first();
	const lockReason = main
		.getByText('Live add-to-betslip is locked because feed freshness is unavailable.')
		.first();
	const lockedAction = main.getByRole('button', { name: 'Locked' }).first();

	await expect(page.getByRole('heading', { name: 'LIVE MATCHES' })).toBeVisible();
	await expect(main.getByText(fixtures.liveHome).first()).toBeVisible({ timeout: 15_000 });
	await expect(main.getByText(fixtures.liveAway).first()).toBeVisible({ timeout: 15_000 });
	await expect(staleBanner).toBeVisible();
	await expect(monitorOnlyBanner).toBeVisible();
	await expect(lockReason).toBeVisible();
	await expect(lockedAction).toBeVisible();
	await expect(lockedAction).toBeDisabled();
	await expect(betSlip.getByText('Select odds to add bets')).toBeVisible();
	await expect(betSlip.getByText('Use Dashboard, Predict, Live, or Value Bets')).toBeVisible();
}

test('seeded live value candidate stays locked on /live when feed freshness is unavailable', async ({
	page,
	context
}) => {
	const session = await createAuthenticatedSession(context);
	const pageErrors: string[] = [];

	page.on('pageerror', (error) => {
		pageErrors.push(error.message);
	});

	try {
		const fixtures = await seedHybridFixtures(session);
		const [liveHome, liveAway] = fixtures.liveMatchLabel.split(' vs ');

		const heartbeat = await backendRequest<LiveHeartbeatResponse>('/api/v1/live/heartbeat', {
			headers: withBearerToken(session.token.access_token)
		});
		expect(
			heartbeat.bridge_ready,
			`live bridge must be ready for seeded live UI verification; issues: ${heartbeat.bridge_issues.join(', ')}`
		).toBe(true);

		const overview = await backendRequest<LiveOverviewResponse>(
			'/api/v1/live/overview?status=live&include_live_value=true&min_live_value_edge=2',
			{
				headers: withBearerToken(session.token.access_token)
			}
		);
		const seededMatch = overview.matches.find((match) => match.id === fixtures.liveMatchId);
		expect(
			seededMatch,
			`seeded live match ${fixtures.liveMatchLabel} should be returned by the live overview endpoint`
		).toBeTruthy();
		expect(overview.is_demo, 'real live overview must not be in demo mode').toBe(false);
		expect(
			seededMatch?.live_value_candidates.some(
				(candidate) => candidate.selection === 'home' && candidate.odds > 1 && candidate.edge > 0
			),
			`seeded match should expose at least one actionable live value candidate: ${JSON.stringify(seededMatch?.live_value_candidates)}`
		).toBe(true);

		await page.goto('/live');
		await expectLockedLiveCandidateState(page, { liveHome, liveAway });
		expect(pageErrors, `unexpected browser errors on /live: ${pageErrors.join('\n')}`).toEqual([]);
	} finally {
		await cleanupSessionArtifacts(session);
	}
});
