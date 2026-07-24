import { createHash } from 'node:crypto';

import { expect, test } from '@playwright/test';

import { createAuthenticatedSession } from '../helpers/auth';
import { backendRequest, withBearerToken } from '../helpers/backend';
import { cleanupSessionArtifacts } from '../helpers/cleanup';
import { runDirectSql, skipIfDirectDatabaseFixturesUnavailable } from '../helpers/database';
import { seedHybridFixtures } from '../helpers/seed';

type TicketGenerationResponse = {
	batch_id: number;
	source_prediction_run_id?: number | null;
	source_prediction_run_ids: number[];
	generation_report: {
		prediction_run_id?: number;
		prediction_run_ids?: number[];
		source_dataset_id?: number | null;
		requested_prediction_ids?: number[];
	};
	tickets: Array<{
		batch_id: number | null;
		legs: Array<{ model_prediction_id?: number | null }>;
	}>;
};

function sqlLiteral(value: string): string {
	return `'${value.replaceAll("'", "''")}'`;
}

function analysisInputHash(strategyId: number, datasetId: number, matchId: number): string {
	const payload = {
		execution_config: {
			fit_kwargs: {},
			max_goals: 10,
			model_key: 'PoissonGoalsModel',
			model_kwargs: {},
			target_limit: 50,
			time_decay_xi: 0.0018,
			training_limit: 380,
			use_time_decay: false
		},
		filters: {},
		markets: ['1x2', 'btts', 'ou_2_5'],
		match_ids: [matchId],
		source_dataset_id: datasetId,
		strategy_id: strategyId,
		strategy_model_type: 'poisson'
	};

	return createHash('sha256').update(JSON.stringify(payload)).digest('hex').slice(0, 24);
}

test('prepared dataset keeps its exact prediction lineage through Analyze into Tickets', async ({
	page,
	context
}) => {
	skipIfDirectDatabaseFixturesUnavailable();
	const session = await createAuthenticatedSession(context);
	const datasetName = `E2E Analysis Dataset ${session.namespace}`;
	let datasetId: number | null = null;
	let strategyId: number | null = null;
	let generatedBatchId: number | null = null;

	try {
		const fixtures = await seedHybridFixtures(session);
		await runDirectSql(`UPDATE users SET is_admin = TRUE WHERE id = ${session.user.id};`);
		const strategyName = `E2E Lineage ${session.namespace}`;
		const strategy = await backendRequest<{ id: number }>('/api/v1/strategies', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				...withBearerToken(session.token.access_token)
			},
			body: JSON.stringify({
				name: strategyName,
				description: 'Deterministic hybrid lineage fixture',
				model_type: 'poisson',
				parameters: {},
				is_active: true
			})
		});
		strategyId = strategy.id;

		const scrapeJobId = Number(
			await runDirectSql(`
				INSERT INTO scrape_jobs (
					job_type, status, league, params, started_at, completed_at, output, created_at
				)
				VALUES (
					${sqlLiteral(`e2e-analysis-${session.namespace}`)},
					'completed',
					${sqlLiteral(fixtures.competition)},
					${sqlLiteral(JSON.stringify({ user_id: session.user.id, namespace: session.namespace }))}::json,
					NOW(), NOW(), '1 match persisted', NOW()
				)
				RETURNING id;
			`)
		);

		datasetId = Number(
			await runDirectSql(`
				INSERT INTO scraped_datasets (name, source, data, matches_count, created_at)
				VALUES (
					${sqlLiteral(datasetName)},
					'OddsHarvester',
					${sqlLiteral(
						JSON.stringify({
							job_id: scrapeJobId,
							match_ids: [fixtures.scheduledMatchId],
							matches: [{ match_id: fixtures.scheduledMatchId }]
						})
					)}::json,
					1,
					NOW()
				)
				RETURNING id;
			`)
		);

		const inputHash = analysisInputHash(strategy.id, datasetId, fixtures.scheduledMatchId);
		await runDirectSql(`
			DELETE FROM model_predictions
			WHERE run_id = ${fixtures.predictionRunId}
				AND match_id <> ${fixtures.scheduledMatchId};

			UPDATE prediction_runs
			SET
				name = ${sqlLiteral(`Strategy: ${strategyName} | input:${inputHash}`)},
				model_type = 'poisson',
				matches_count = 1,
				source_dataset_id = ${datasetId},
				strategy_id = ${strategy.id},
				input_hash = ${sqlLiteral(inputHash)},
				dedupe_enabled = TRUE,
				input_context = ${sqlLiteral(
					JSON.stringify({
						dataset_id: datasetId,
						match_ids: [fixtures.scheduledMatchId],
						markets: ['1x2', 'btts', 'ou_2_5']
					})
				)}::json
			WHERE id = ${fixtures.predictionRunId};
		`);

		const predictionId = Number(
			(
				await runDirectSql(`
					SELECT id
					FROM model_predictions
					WHERE run_id = ${fixtures.predictionRunId}
						AND match_id = ${fixtures.scheduledMatchId}
					ORDER BY id
					LIMIT 1;
				`)
			).split('\n')[0]
		);

		await page.goto(`/analyze?dataset_id=${datasetId}`);
		await expect(page.getByText(`Set #${datasetId}`, { exact: true }).first()).toBeVisible();
		await expect(page.getByText('Set de date pregătit pentru analiză', { exact: true })).toBeVisible();

		await page.getByRole('button', { name: 'Golește', exact: true }).click();
		await page.getByRole('checkbox', { name: new RegExp(strategyName) }).check();
		await page
			.getByRole('button', { name: /^Rulează analiza pentru 1 strategi(?:e|i)$/ })
			.click();

		await expect(page.getByText('Run reutilizat', { exact: true })).toBeVisible();
		await expect(page.getByText(new RegExp(`run #${fixtures.predictionRunId}`)).first()).toBeVisible();
		await expect(page.getByText(fixtures.scheduledMatchLabel.replace(' vs ', ' – '), { exact: true }).first()).toBeVisible();

		await page
			.getByRole('checkbox', {
				name: `Selectează ${fixtures.scheduledMatchLabel.replace(' vs ', ' – ')}`
			})
			.first()
			.check();

		await page.getByRole('link', { name: /Continuă la bilete/ }).click();
		await expect(page).toHaveURL(new RegExp(`dataset_id=${datasetId}`));
		await expect(page).toHaveURL(new RegExp(`run_ids=${fixtures.predictionRunId}`));
		await expect(page).toHaveURL(new RegExp(`prediction_ids=${predictionId}`));
		await expect(page).toHaveURL(/source=analyze/);
		await expect(page.getByRole('heading', { name: 'Lineage pentru lotul următor' })).toBeVisible();
		await expect(page.getByText('Din Analiză', { exact: true })).toBeVisible();
		await expect(page.getByText(`run #${fixtures.predictionRunId}`, { exact: true }).first()).toBeVisible();

		await page.getByLabel('Număr de bilete', { exact: true }).fill('1');
		await page.getByLabel('Siguranță / dificultate', { exact: true }).selectOption('safe');
		const generationResponsePromise = page.waitForResponse(
			(response) =>
				response.request().method() === 'POST' &&
				new URL(response.url()).pathname === '/api/v1/tickets/generate'
		);
		await page
			.getByRole('button', {
				name: `Generează 1 bilet din run #${fixtures.predictionRunId}`,
				exact: true
			})
			.click();
		const generationResponse = await generationResponsePromise;
		expect(generationResponse.ok()).toBe(true);
		const generated = (await generationResponse.json()) as TicketGenerationResponse;
		generatedBatchId = generated.batch_id;
		expect(generated.source_prediction_run_id).toBe(fixtures.predictionRunId);
		expect(generated.source_prediction_run_ids).toEqual([fixtures.predictionRunId]);
		expect(generated.generation_report.prediction_run_id).toBe(fixtures.predictionRunId);
		expect(generated.generation_report.prediction_run_ids).toEqual([fixtures.predictionRunId]);
		expect(generated.generation_report.source_dataset_id).toBe(datasetId);
		expect(generated.generation_report.requested_prediction_ids).toEqual([predictionId]);
		expect(generated.tickets).toHaveLength(1);
		expect(generated.tickets[0]?.batch_id).toBe(generated.batch_id);
		expect(generated.tickets[0]?.legs.map((leg) => leg.model_prediction_id)).toEqual([predictionId]);

		await expect(page.getByRole('tab', { name: /Revizuiește lotul/ })).toHaveAttribute(
			'data-state',
			'active'
		);
		await expect(page.getByRole('heading', { name: `Lot #${generated.batch_id}` })).toBeVisible();
		await expect(
			page.getByText(
				new RegExp(`surse run #${fixtures.predictionRunId} · set de date #${datasetId}`)
			)
		).toBeVisible();
		await page.getByText('Vezi selecțiile și cotele', { exact: true }).first().click();
		await expect(
			page.getByText(`predicție #${predictionId}`, { exact: true }).filter({ visible: true }).first()
		).toBeVisible();
	} finally {
		if (generatedBatchId !== null) {
			await runDirectSql(`DELETE FROM ticket_batches WHERE id = ${generatedBatchId};`).catch(
				() => undefined
			);
		}
		await runDirectSql(`DELETE FROM scraped_datasets WHERE name = ${sqlLiteral(datasetName)};`).catch(
			() => undefined
		);
		if (strategyId !== null) {
			await runDirectSql(`DELETE FROM strategies WHERE id = ${strategyId};`).catch(() => undefined);
		}
		await cleanupSessionArtifacts(session);
	}
});
