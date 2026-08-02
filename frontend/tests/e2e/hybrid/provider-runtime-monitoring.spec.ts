import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { runDirectSql, skipIfDirectDatabaseFixturesUnavailable } from '../helpers/database';

test('monitoring renders provider-safe source, lane and alert snapshots from the runtime API', async ({ browser }) => {
	skipIfDirectDatabaseFixturesUnavailable();
	const context = await browser.newContext({ serviceWorkers: 'block' });
	const page = await context.newPage();
	const session = await createAuthenticatedSession(context);
	await runDirectSql(`UPDATE users SET is_admin = TRUE WHERE id = ${session.user.id};`);

	await page.route('**/api/v1/provider/runtime', async (route) => {
		await route.fulfill({
			contentType: 'application/json',
			body: JSON.stringify({
				observed_at: '2026-08-01T12:00:00Z',
				sources: [{
					adapter_key: 'licensed-odds', source_key: 'primary-feed', circuit_state: 'closed', quota_limit: 100,
					quota_reserved: 2, quota_consumed: 12, provider_remaining: 88, consecutive_failures: 0,
					last_reconciled_at: '2026-08-01T11:59:00Z', observation_count: 10,
					complete_snapshot_count: 8, partial_snapshot_count: 1, unmapped_observation_count: 1,
					coverage_percent: 80, latest_observed_at: '2026-08-01T11:59:30Z', freshness_state: 'fresh', cache_state: 'mixed'
				}],
				lanes: [{
					lane: 'provider-http', queued: 3, running: 1, oldest_queue_age_ms: 1_500,
					sampled_terminal_runs: 8, retries: 1, fallbacks: 0, freshness_failures: 0,
					peak_rss_bytes: null, peak_pid_count: null
				}],
				phases: [
					{ phase: 'backfill', status: 'running', queued: 2, running: 1, failed: 0, partial: 0, attention_count: 0 },
					{ phase: 'normalize', status: 'attention', queued: 0, running: 0, failed: 0, partial: 0, attention_count: 2 },
					{ phase: 'features', status: 'queued', queued: 1, running: 0, failed: 0, partial: 0, attention_count: 0 },
					{ phase: 'model', status: 'attention', queued: 0, running: 0, failed: 1, partial: 0, attention_count: 1 }
				],
				alerts: [{ scope: 'lane', scope_key: 'provider-http', code: 'queue_age_high', severity: 'warning' }]
			})
		});
	});

	try {
		await page.goto('/monitoring');
		const runtime = page.getByTestId('provider-runtime-panel');
		await expect(runtime.getByRole('heading', { name: 'Provider runtime' })).toBeVisible();
		await expect(runtime.getByTestId('provider-source-card')).toContainText('licensed-odds · primary-feed');
		await expect(runtime.getByTestId('provider-source-card')).toContainText('Quota used');
		await expect(runtime.getByTestId('provider-source-card')).toContainText('Coverage');
		await expect(runtime.getByTestId('provider-source-card')).toContainText('80.0%');
		await expect(runtime.getByTestId('provider-source-card')).toContainText('fresh');
		await expect(runtime.getByTestId('provider-source-card')).toContainText('cache mixed');
		await expect(runtime.getByTestId('provider-lane-card')).toContainText('provider-http');
		const phases = runtime.getByTestId('provider-pipeline-phases');
		await expect(phases).toContainText('Pipeline progress');
		await expect(phases.getByTestId('provider-phase-card')).toHaveCount(4);
		await expect(phases).toContainText('backfill');
		await expect(phases).toContainText('running');
		await expect(phases).toContainText('normalize');
		await expect(phases).toContainText('Attention');
		await expect(phases.getByTestId('provider-phase-card').nth(3)).toContainText('1 / 0');
		await expect(runtime.getByTestId('provider-runtime-alerts')).toContainText('queue age high');
		await expect(runtime).not.toContainText('provider_remaining');
	} finally {
		await cleanupSessionArtifacts(session);
		await context.close();
	}
});

test('monitoring does not request or render provider runtime for a regular user', async ({ browser }) => {
	const context = await browser.newContext({ serviceWorkers: 'block' });
	const page = await context.newPage();
	const session = await createAuthenticatedSession(context);
	let providerRequests = 0;

	await page.route('**/api/v1/provider/runtime', async (route) => {
		providerRequests += 1;
		await route.abort();
	});

	try {
		await page.goto('/monitoring');
		await expect(page.getByTestId('provider-runtime-panel')).toHaveCount(0);
		await page.waitForTimeout(250);
		expect(providerRequests).toBe(0);
	} finally {
		await cleanupSessionArtifacts(session);
		await context.close();
	}
});
