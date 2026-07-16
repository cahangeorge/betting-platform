import { expect, test, type Page } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { getE2EEnv } from '../helpers/backend';
import { runDirectSql, skipIfDirectDatabaseFixturesUnavailable } from '../helpers/database';

type GeneratedTicket = {
	id: number;
	batch_id: number | null;
	status: string;
	legs: Array<{ model_prediction_id: number | null }>;
};

type TicketGenerationResponse = {
	batch_id: number;
	revision: number;
	source_prediction_run_ids: number[];
	generation_report: {
		prediction_run_ids?: number[];
		generated_prediction_run_ids?: number[];
		generated_ticket_lineage?: Array<{
			ticket_id: number;
			prediction_ids: number[];
			prediction_run_ids: number[];
			match_ids: number[];
		}>;
	};
	tickets: GeneratedTicket[];
};

function sqlLiteral(value: string): string {
	return `'${value.split("'").join("''")}'`;
}

async function seedTicketLineageFixture(userId: number, namespace: string) {
	const datasetName = `E2E Ticket Lifecycle ${namespace}`;
	const competition = `E2E Ticket Lifecycle ${namespace}`;
	const qualityReport = JSON.stringify({
		model: { pick: 'home' },
		market: {
			odds: {
				home: { odds: 2, bookmaker: 'E2E' }
			}
		},
		reliability: {
			label: 'reliable',
			score: 95,
			is_ticket_eligible: true,
			block_reasons: []
		}
	});

	const output = await runDirectSql(`
		WITH dataset AS (
			INSERT INTO scraped_datasets (name, source, data, matches_count, created_at)
			VALUES (
				${sqlLiteral(datasetName)},
				'e2e',
				'{}'::json,
				3,
				NOW()
			)
			RETURNING id
		), matches_insert AS (
			INSERT INTO matches (
				external_id, sport, home_team, away_team, status, match_date, competition, season
			)
			VALUES
				(${sqlLiteral(`ticket-a-${namespace}`)}, 'football', 'Atlas A', 'Comets A', 'scheduled', NOW() + INTERVAL '5 hours', ${sqlLiteral(competition)}, '2026'),
				(${sqlLiteral(`ticket-b-${namespace}`)}, 'football', 'Atlas B', 'Comets B', 'scheduled', NOW() + INTERVAL '6 hours', ${sqlLiteral(competition)}, '2026'),
				(${sqlLiteral(`ticket-c-${namespace}`)}, 'football', 'Atlas C', 'Comets C', 'scheduled', NOW() + INTERVAL '7 hours', ${sqlLiteral(competition)}, '2026')
			RETURNING id, external_id
		), odds_snapshots_insert AS (
			INSERT INTO odds_snapshots (
				match_id, source, source_key, dataset_id, observed_at, quality, metadata_json
			)
			SELECT matches_insert.id, 'e2e', matches_insert.external_id, dataset.id, NOW(), 'complete', '{}'::json
			FROM matches_insert, dataset
			RETURNING id, match_id
		), odds_entries_insert AS (
			INSERT INTO odds_entries (
				match_id, odds_snapshot_id, bookmaker, market, home_odds, draw_odds, away_odds, timestamp
			)
			SELECT odds_snapshots_insert.match_id, odds_snapshots_insert.id, 'E2E', '1x2', 2.0, 3.5, 4.2, NOW()
			FROM odds_snapshots_insert
			RETURNING id
		), run_one AS (
			INSERT INTO prediction_runs (
				user_id, name, model_type, ensemble, status, matches_count, started_at, completed_at,
				source_dataset_id, input_hash, dedupe_enabled, created_at
			)
			SELECT ${userId}, ${sqlLiteral(`E2E selected one ${namespace}`)}, 'poisson', FALSE, 'completed', 1,
				NOW(), NOW(), dataset.id, ${sqlLiteral(`e2e-one-${namespace}`)}, FALSE, NOW()
			FROM dataset
			RETURNING id
		), run_two AS (
			INSERT INTO prediction_runs (
				user_id, name, model_type, ensemble, status, matches_count, started_at, completed_at,
				source_dataset_id, input_hash, dedupe_enabled, created_at
			)
			SELECT ${userId}, ${sqlLiteral(`E2E selected two ${namespace}`)}, 'poisson', FALSE, 'completed', 1,
				NOW(), NOW(), dataset.id, ${sqlLiteral(`e2e-two-${namespace}`)}, FALSE, NOW()
			FROM dataset
			RETURNING id
		), run_three AS (
			INSERT INTO prediction_runs (
				user_id, name, model_type, ensemble, status, matches_count, started_at, completed_at,
				source_dataset_id, input_hash, dedupe_enabled, created_at
			)
			SELECT ${userId}, ${sqlLiteral(`E2E selected three ${namespace}`)}, 'poisson', FALSE, 'completed', 1,
				NOW(), NOW(), dataset.id, ${sqlLiteral(`e2e-three-${namespace}`)}, FALSE, NOW()
			FROM dataset
			RETURNING id
		), prediction_one AS (
			INSERT INTO model_predictions (
				run_id, model_type, match_id, odds_snapshot_id, market, home_prob, draw_prob, away_prob,
				home_odds, draw_odds, away_odds, value_home, value_draw, value_away,
				expected_value, quality_report, created_at
			)
			SELECT run_one.id, 'poisson', matches_insert.id, odds_snapshots_insert.id, '1x2', 0.64, 0.21, 0.15,
				2.0, 3.4, 4.1, 0.28, 0.01, -0.04, 0.30, ${sqlLiteral(qualityReport)}::json, NOW()
			FROM run_one, matches_insert, odds_snapshots_insert
			WHERE matches_insert.external_id = ${sqlLiteral(`ticket-a-${namespace}`)}
				AND odds_snapshots_insert.match_id = matches_insert.id
			RETURNING id
		), prediction_two AS (
			INSERT INTO model_predictions (
				run_id, model_type, match_id, odds_snapshot_id, market, home_prob, draw_prob, away_prob,
				home_odds, draw_odds, away_odds, value_home, value_draw, value_away,
				expected_value, quality_report, created_at
			)
			SELECT run_two.id, 'poisson', matches_insert.id, odds_snapshots_insert.id, '1x2', 0.62, 0.22, 0.16,
				2.0, 3.5, 4.2, 0.24, 0.01, -0.04, 0.20, ${sqlLiteral(qualityReport)}::json, NOW()
			FROM run_two, matches_insert, odds_snapshots_insert
			WHERE matches_insert.external_id = ${sqlLiteral(`ticket-b-${namespace}`)}
				AND odds_snapshots_insert.match_id = matches_insert.id
			RETURNING id
		), prediction_three AS (
			INSERT INTO model_predictions (
				run_id, model_type, match_id, odds_snapshot_id, market, home_prob, draw_prob, away_prob,
				home_odds, draw_odds, away_odds, value_home, value_draw, value_away,
				expected_value, quality_report, created_at
			)
			SELECT run_three.id, 'poisson', matches_insert.id, odds_snapshots_insert.id, '1x2', 0.60, 0.23, 0.17,
				2.0, 3.6, 4.3, 0.20, 0.01, -0.04, 0.10, ${sqlLiteral(qualityReport)}::json, NOW()
			FROM run_three, matches_insert, odds_snapshots_insert
			WHERE matches_insert.external_id = ${sqlLiteral(`ticket-c-${namespace}`)}
				AND odds_snapshots_insert.match_id = matches_insert.id
			RETURNING id
		)
		SELECT dataset.id, run_one.id, run_two.id, run_three.id,
			prediction_one.id, prediction_two.id, prediction_three.id
		FROM dataset, run_one, run_two, run_three, prediction_one, prediction_two, prediction_three;
	`);

	const [datasetId, runOne, runTwo, runThree, predictionOne, predictionTwo, predictionThree] = output
		.split('\n')[0]
		.split('|')
		.map(Number);

	return {
		datasetId,
		runIds: [runOne, runTwo, runThree],
		predictionIds: [predictionOne, predictionTwo, predictionThree],
		datasetName,
		competition
	};
}

async function setTheme(page: Page, theme: 'light' | 'dark') {
	await page.evaluate((nextTheme) => {
		localStorage.setItem('theme', nextTheme);
		document.documentElement.classList.toggle('light', nextTheme === 'light');
		document.documentElement.classList.toggle('dark', nextTheme === 'dark');
	}, theme);
	await expect(page.locator('html')).toHaveClass(new RegExp(`\\b${theme}\\b`));
}

async function expectMobileActionsClearBottomNav(page: Page) {
	const geometry = await page.evaluate(() => {
		const bottomNav = document.querySelector<HTMLElement>('.mobile-bottom-nav');
		const actions = Array.from(document.querySelectorAll<HTMLElement>('.mobile-above-nav')).filter((element) => {
			const style = getComputedStyle(element);
			const rect = element.getBoundingClientRect();
			return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
		});
		return {
			clientWidth: document.documentElement.clientWidth,
			scrollWidth: document.documentElement.scrollWidth,
			navTop: bottomNav?.getBoundingClientRect().top ?? null,
			actions: actions.map((element) => {
				const rect = element.getBoundingClientRect();
				return { top: rect.top, bottom: rect.bottom, height: rect.height };
			})
		};
	});

	expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth);
	expect(geometry.navTop).not.toBeNull();
	for (const action of geometry.actions) {
		expect(action.bottom).toBeLessThanOrEqual((geometry.navTop ?? 0) - 4);
		expect(action.height).toBeLessThanOrEqual(96);
	}
}

async function expectButtonContrast(page: Page, accessibleName: string, minimum = 4.5) {
	const ratio = await page.getByRole('button', { name: accessibleName, exact: true }).evaluate((element) => {
		function rgb(value: string): [number, number, number] {
			const channels = value.match(/[\d.]+/g)?.slice(0, 3).map(Number) ?? [];
			if (channels.length !== 3) throw new Error(`Cannot parse color: ${value}`);
			return channels as [number, number, number];
		}
		function luminance([red, green, blue]: [number, number, number]) {
			const [r, g, b] = [red, green, blue].map((channel) => {
				const normalized = channel / 255;
				return normalized <= 0.03928
					? normalized / 12.92
					: ((normalized + 0.055) / 1.055) ** 2.4;
			});
			return 0.2126 * r + 0.7152 * g + 0.0722 * b;
		}

		const style = getComputedStyle(element);
		const foreground = luminance(rgb(style.color));
		const background = luminance(rgb(style.backgroundColor));
		const lighter = Math.max(foreground, background);
		const darker = Math.min(foreground, background);
		return (lighter + 0.05) / (darker + 0.05);
	});
	expect(ratio).toBeGreaterThanOrEqual(minimum);
}

async function selectBalancedAccumulator(page: Page) {
	await expect(page.getByTestId('tickets-panel')).toHaveAttribute('data-interactive', 'true');
	const difficulty = page.getByLabel('Siguranță / dificultate', { exact: true });
	const acknowledgement = page.getByRole('checkbox', { name: /Confirm riscul acumulatorului/i });
	await expect(async () => {
		await difficulty.selectOption('balanced');
		await expect(difficulty).toHaveValue('balanced');
		await expect(acknowledgement).toBeVisible();
	}).toPass({ timeout: 5_000 });
	await acknowledgement.check();
}

test('selected runs keep exact contributing lineage through review, activation, Active, and History', async ({
	page,
	context
}) => {
	skipIfDirectDatabaseFixturesUnavailable();
	const session = await createAuthenticatedSession(context);
	let fixture: Awaited<ReturnType<typeof seedTicketLineageFixture>> | null = null;
	let generatedBatchId: number | null = null;
	let generatedTicketId: number | null = null;

	try {
		fixture = await seedTicketLineageFixture(session.user.id, session.namespace);
		await page.setViewportSize({ width: 390, height: 844 });
		await page.goto(
			`/tickets?dataset_id=${fixture.datasetId}&run_ids=${fixture.runIds.join(',')}&candidate_ids=${fixture.predictionIds.join(',')}&source=analyze`
		);
		await expect(page.getByRole('heading', { name: 'Lineage pentru lotul următor' })).toBeVisible();
		await page.getByLabel('Număr de bilete', { exact: true }).fill('1');
		await selectBalancedAccumulator(page);
		const preflightResponsePromise = page.waitForResponse(
			(response) =>
				response.request().method() === 'POST' &&
				new URL(response.url()).pathname === '/api/v1/tickets/preflight'
		);
		await page.getByRole('button', { name: 'Verifică disponibilitatea', exact: true }).click();
		const preflightResponse = await preflightResponsePromise;
		expect(preflightResponse.status()).toBe(200);
		const riskAvailability = page.getByLabel('Disponibilitate pe niveluri de risc');
		await expect(riskAvailability.getByRole('heading', { name: 'Prudent', exact: true })).toBeVisible();
		await expect(riskAvailability.getByRole('heading', { name: 'Echilibrat', exact: true })).toBeVisible();
		await expect(riskAvailability.getByRole('heading', { name: 'Agresiv', exact: true })).toBeVisible();

		for (const theme of ['light', 'dark'] as const) {
			await setTheme(page, theme);
			await expectMobileActionsClearBottomNav(page);
		}

		const generationResponsePromise = page.waitForResponse(
			(response) =>
				response.request().method() === 'POST' &&
				new URL(response.url()).pathname === '/api/v1/tickets/generate'
		);
		await page.getByRole('button', { name: 'Generează 1 bilet din 3 run-uri', exact: true }).click();
		const generationResponse = await generationResponsePromise;
		expect(generationResponse.status()).toBe(201);
		const generated = (await generationResponse.json()) as TicketGenerationResponse;
		generatedBatchId = generated.batch_id;
		generatedTicketId = generated.tickets[0]?.id ?? null;

		expect(generated.source_prediction_run_ids).toEqual(fixture.runIds);
		expect(generated.generation_report.prediction_run_ids).toEqual(fixture.runIds);
		expect(generated.generation_report.generated_prediction_run_ids).toEqual(fixture.runIds.slice(0, 2));
		expect(generated.generation_report.generated_ticket_lineage).toEqual([
			{
				ticket_id: generated.tickets[0].id,
				prediction_ids: fixture.predictionIds.slice(0, 2),
				prediction_run_ids: fixture.runIds.slice(0, 2),
				match_ids: expect.any(Array)
			}
		]);
		expect(generated.tickets).toHaveLength(1);
		expect(generated.tickets[0].status).toBe('generated');

		await expect(page.getByRole('tab', { name: /Revizuiește lotul/ })).toHaveAttribute(
			'data-state',
			'active'
		);
		await expect(page.getByRole('heading', { name: `Lot #${generated.batch_id}` })).toBeVisible();
		await expect(page.getByTestId(`ticket-contributing-runs-${generated.tickets[0].id}`)).toContainText(
			fixture.runIds.slice(0, 2).map((runId) => `run #${runId}`).join(', ')
		);
		await expect(page.getByTestId(`ticket-contributing-runs-${generated.tickets[0].id}`)).not.toContainText(
			`run #${fixture.runIds[2]}`
		);

		const discardTrigger = page.getByRole('button', { name: 'Renunță la lotul draft', exact: true });
		for (const theme of ['light', 'dark'] as const) {
			await setTheme(page, theme);
			await discardTrigger.focus();
			await page.keyboard.press('Enter');
			const discardDialog = page.getByRole('alertdialog');
			await expect(discardDialog).toBeVisible();
			await expect(page.getByRole('button', { name: 'Păstrează lotul', exact: true })).toBeFocused();
			await expectButtonContrast(page, 'Confirmă renunțarea');
			const dialogGeometry = await discardDialog.evaluate((element) => {
				const dialog = element.getBoundingClientRect();
				const bottomNav = document.querySelector<HTMLElement>('.mobile-bottom-nav')?.getBoundingClientRect();
				return { dialogBottom: dialog.bottom, navTop: bottomNav?.top ?? null };
			});
			expect(dialogGeometry.navTop).not.toBeNull();
			expect(dialogGeometry.dialogBottom).toBeLessThan(dialogGeometry.navTop ?? 0);
			await page.keyboard.press('Escape');
			await expect(discardDialog).toBeHidden();
			await expect(discardTrigger).toBeFocused();
		}

		await page.getByRole('tab', { name: 'Active', exact: true }).click();
		await expect(page.getByText(`#${generated.tickets[0].id}`, { exact: false })).toHaveCount(0);
		await page.getByRole('tab', { name: /Revizuiește lotul/ }).click();

		for (const theme of ['light', 'dark'] as const) {
			await setTheme(page, theme);
			await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
			await expectMobileActionsClearBottomNav(page);
		}

		// A persisted draft must remain reviewable even after a dev/HMR or user reload.
		await page.getByRole('tab', { name: /Revizuiește lotul/ }).click();
		await expect(page.getByRole('heading', { name: `Lot #${generated.batch_id}` })).toBeVisible();
		const balanceBefore = Number(
			(await runDirectSql(`SELECT balance FROM bankrolls WHERE id = ${session.bankroll.id};`)).split('\n')[0]
		);
		await page.getByRole('checkbox', { name: /^Am verificat/ }).check();
		const activationResponsePromise = page.waitForResponse(
			(response) =>
				response.request().method() === 'POST' &&
				new URL(response.url()).pathname === `/api/v1/tickets/batches/${generated.batch_id}/activate`
		);
		await page.getByRole('button', { name: 'Activează lotul', exact: true }).click();
		const activationResponse = await activationResponsePromise;
		expect(activationResponse.ok()).toBe(true);
		const activation = (await activationResponse.json()) as {
			status: string;
			debited_amount: number;
			tickets: GeneratedTicket[];
		};
		expect(activation.status).toBe('activated');
		expect(activation.debited_amount).toBe(10);
		expect(activation.tickets.map((ticket) => ticket.status)).toEqual(['open']);

		const { backendURL } = getE2EEnv();
		const repeatedActivation = await fetch(
			new URL(`/api/v1/tickets/batches/${generated.batch_id}/activate`, backendURL),
			{
				method: 'POST',
				headers: {
					Authorization: `Bearer ${session.token.access_token}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					expected_revision: generated.revision,
					review_acknowledged: true,
					accepted_warning_codes: []
				})
			}
		);
		expect(repeatedActivation.status).toBe(409);

		const [balanceAfter, stakeLedgerCount, stakeLedgerAmount] = (
			await runDirectSql(`
				SELECT b.balance,
					COUNT(le.id) FILTER (WHERE le.entry_type = 'stake'),
					COALESCE(SUM(le.amount) FILTER (WHERE le.entry_type = 'stake'), 0)
				FROM bankrolls b
				LEFT JOIN ledger_entries le
					ON le.bankroll_id = b.id AND le.ticket_id = ${generated.tickets[0].id}
				WHERE b.id = ${session.bankroll.id}
				GROUP BY b.id;
			`)
		)
			.split('\n')[0]
			.split('|')
			.map(Number);
		expect(balanceAfter).toBe(balanceBefore - 10);
		expect(stakeLedgerCount).toBe(1);
		expect(stakeLedgerAmount).toBe(-10);

		await expect(page.getByRole('tab', { name: 'Active', exact: true })).toHaveAttribute(
			'data-state',
			'active'
		);
		await expect(page.getByText(`#TKT-${generated.tickets[0].id}`, { exact: true })).toBeVisible();

		await page.getByRole('tab', { name: 'Istoric', exact: true }).click();
		await page.getByLabel('Lot de bilete').selectOption(String(generated.batch_id));
		const historySourceRuns = page.getByTestId('tickets-history-source-runs');
		for (const runId of fixture.runIds) await expect(historySourceRuns).toContainText(`run #${runId}`);
		const historyContributingRuns = page.getByTestId(
			`ticket-history-contributing-runs-${generated.tickets[0].id}`
		);
		for (const runId of fixture.runIds.slice(0, 2)) {
			await expect(historyContributingRuns).toContainText(`run #${runId}`);
		}
		await expect(historyContributingRuns).not.toContainText(`run #${fixture.runIds[2]}`);
	} finally {
		if (fixture !== null) {
			await runDirectSql(`
				DELETE FROM ledger_entries
				WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id = ${session.user.id});
				DELETE FROM settlements
				WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id = ${session.user.id});
				DELETE FROM bet_placements
				WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id = ${session.user.id});
				DELETE FROM tickets WHERE user_id = ${session.user.id};
				${generatedBatchId !== null ? `DELETE FROM ticket_batches WHERE id = ${generatedBatchId};` : ''}
				DELETE FROM model_predictions WHERE run_id IN (${fixture.runIds.join(',')});
				DELETE FROM prediction_runs WHERE id IN (${fixture.runIds.join(',')});
				DELETE FROM odds_entries
				WHERE match_id IN (SELECT id FROM matches WHERE competition = ${sqlLiteral(fixture.competition)});
				DELETE FROM matches WHERE competition = ${sqlLiteral(fixture.competition)};
				DELETE FROM scraped_datasets WHERE id = ${fixture.datasetId};
			`);

			const remaining = await runDirectSql(`
				SELECT
					(SELECT COUNT(*) FROM tickets WHERE user_id = ${session.user.id}),
					(SELECT COUNT(*) FROM prediction_runs WHERE id IN (${fixture.runIds.join(',')})),
					(SELECT COUNT(*) FROM scraped_datasets WHERE id = ${fixture.datasetId}),
					(SELECT COUNT(*) FROM matches WHERE competition = ${sqlLiteral(fixture.competition)}),
					(SELECT COUNT(*) FROM ledger_entries WHERE ticket_id = ${generatedTicketId ?? -1});
			`);
			expect(remaining.split('\n')[0]).toBe('0|0|0|0|0');
		}
		await cleanupSessionArtifacts(session);
		const remainingSessionArtifacts = await runDirectSql(`
			SELECT
				(SELECT COUNT(*) FROM ticket_batches WHERE bankroll_id = ${session.bankroll.id}),
				(SELECT COUNT(*) FROM ledger_entries WHERE bankroll_id = ${session.bankroll.id}),
				(SELECT COUNT(*) FROM bankrolls WHERE id = ${session.bankroll.id}),
				(SELECT COUNT(*) FROM users WHERE id = ${session.user.id});
		`);
		expect(remainingSessionArtifacts.split('\n')[0]).toBe('0|0|0|0');
	}
});

test('generated draft discard is owner-scoped, non-financial, and blocked after activation', async ({
	page,
	context,
	browser
}) => {
	skipIfDirectDatabaseFixturesUnavailable();
	const session = await createAuthenticatedSession(context);
	const foreignContext = await browser.newContext();
	const foreignSession = await createAuthenticatedSession(foreignContext);
	let fixture: Awaited<ReturnType<typeof seedTicketLineageFixture>> | null = null;

	try {
		fixture = await seedTicketLineageFixture(session.user.id, session.namespace);
		const ticketURL = `/tickets?dataset_id=${fixture.datasetId}&run_ids=${fixture.runIds.join(',')}&candidate_ids=${fixture.predictionIds.join(',')}&source=analyze`;
		await page.goto(ticketURL);
		await page.getByLabel('Număr de bilete', { exact: true }).fill('1');
		await selectBalancedAccumulator(page);

		const firstGenerationResponse = page.waitForResponse(
			(response) =>
				response.request().method() === 'POST' &&
				new URL(response.url()).pathname === '/api/v1/tickets/generate'
		);
		await page.getByRole('button', { name: 'Generează 1 bilet din 3 run-uri', exact: true }).click();
		const firstGeneration = (await (await firstGenerationResponse).json()) as TicketGenerationResponse;
		const draftBatchId = firstGeneration.batch_id;
		const discardTrigger = page.getByRole('button', { name: 'Renunță la lotul draft' });
		await discardTrigger.click();
		await expect(page.getByRole('alertdialog')).toBeVisible();
		await expect(page.getByRole('button', { name: 'Păstrează lotul' })).toBeFocused();
		await page.keyboard.press('Escape');
		await expect(page.getByRole('alertdialog')).toBeHidden();
		await expect(discardTrigger).toBeFocused();
		const balanceBeforeDiscard = Number(
			(await runDirectSql(`SELECT balance FROM bankrolls WHERE id = ${session.bankroll.id};`)).split('\n')[0]
		);
		const { backendURL } = getE2EEnv();
		const discardURL = new URL(`/api/v1/tickets/batches/${draftBatchId}`, backendURL);

		const foreignDiscard = await fetch(discardURL, {
			method: 'DELETE',
			headers: { Authorization: `Bearer ${foreignSession.token.access_token}` }
		});
		expect(foreignDiscard.status).toBe(404);

		const ownerDiscard = await fetch(discardURL, {
			method: 'DELETE',
			headers: { Authorization: `Bearer ${session.token.access_token}` }
		});
		expect(ownerDiscard.status).toBe(200);
		expect(await ownerDiscard.json()).toEqual({
			batch_id: draftBatchId,
			status: 'discarded',
			discarded_tickets: 1
		});

		const repeatedDiscard = await fetch(discardURL, {
			method: 'DELETE',
			headers: { Authorization: `Bearer ${session.token.access_token}` }
		});
		expect(repeatedDiscard.status).toBe(404);

		const discardState = (
			await runDirectSql(`
				SELECT
					(SELECT COUNT(*) FROM ticket_batches WHERE id = ${draftBatchId}),
					(SELECT COUNT(*) FROM tickets WHERE batch_id = ${draftBatchId}),
					(SELECT COUNT(*) FROM ledger_entries WHERE bankroll_id = ${session.bankroll.id}),
					(SELECT balance FROM bankrolls WHERE id = ${session.bankroll.id});
			`)
		)
			.split('\n')[0]
			.split('|');
		expect(discardState.slice(0, 3)).toEqual(['0', '0', '0']);
		expect(Number(discardState[3])).toBe(balanceBeforeDiscard);

		await page.reload();
		await page.waitForLoadState('networkidle');
		const reviewTab = page.getByRole('tab', { name: /Revizuiește lotul/ });
		await reviewTab.click();
		await expect(reviewTab).toHaveAttribute('data-state', 'active');
		await expect(page.getByRole('heading', { name: 'Nu există un lot nou de revizuit' })).toBeVisible();
		await expect(page.getByRole('heading', { name: `Lot #${draftBatchId}` })).toHaveCount(0);
		await page.getByRole('tab', { name: 'Istoric', exact: true }).click();
		await expect(page.getByRole('heading', { name: 'Nu există loturi istorice' })).toBeVisible();

		await page.getByRole('tab', { name: /Generează/ }).click();
		await page.getByLabel('Număr de bilete', { exact: true }).fill('1');
		const activatedGenerationResponse = page.waitForResponse(
			(response) =>
				response.request().method() === 'POST' &&
				new URL(response.url()).pathname === '/api/v1/tickets/generate'
		);
		await page.getByRole('button', { name: 'Generează 1 bilet din 3 run-uri', exact: true }).click();
		const activatedGeneration = (await (await activatedGenerationResponse).json()) as TicketGenerationResponse;
		await expect(page.getByRole('tab', { name: /Revizuiește lotul/ })).toHaveAttribute(
			'data-state',
			'active'
		);
		await page.getByRole('checkbox', { name: /^Am verificat/ }).check();
		await page.getByRole('button', { name: 'Activează lotul', exact: true }).click();
		await expect(page.getByRole('tab', { name: 'Active', exact: true })).toHaveAttribute(
			'data-state',
			'active'
		);

		const activatedDiscard = await fetch(
			new URL(`/api/v1/tickets/batches/${activatedGeneration.batch_id}`, backendURL),
			{
				method: 'DELETE',
				headers: { Authorization: `Bearer ${session.token.access_token}` }
			}
		);
		expect(activatedDiscard.status).toBe(409);
	} finally {
		if (fixture !== null) {
			await runDirectSql(`
				DELETE FROM ledger_entries
				WHERE bankroll_id = ${session.bankroll.id};
				DELETE FROM settlements
				WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id = ${session.user.id});
				DELETE FROM bet_placements
				WHERE ticket_id IN (SELECT id FROM tickets WHERE user_id = ${session.user.id});
				DELETE FROM tickets WHERE user_id = ${session.user.id};
				DELETE FROM ticket_batches WHERE bankroll_id = ${session.bankroll.id};
				DELETE FROM model_predictions WHERE run_id IN (${fixture.runIds.join(',')});
				DELETE FROM prediction_runs WHERE id IN (${fixture.runIds.join(',')});
				DELETE FROM odds_entries
				WHERE match_id IN (SELECT id FROM matches WHERE competition = ${sqlLiteral(fixture.competition)});
				DELETE FROM matches WHERE competition = ${sqlLiteral(fixture.competition)};
				DELETE FROM scraped_datasets WHERE id = ${fixture.datasetId};
			`);
		}
		await cleanupSessionArtifacts(session);
		await cleanupSessionArtifacts(foreignSession);
		await foreignContext.close();
	}
});
