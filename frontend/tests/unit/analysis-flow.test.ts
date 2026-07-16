import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import {
	nextCandidateWindowSize,
	parseAnalysisReturnContext,
	selectModelOutcome,
	visibleCandidateWindow
} from '../../src/routes/analyze/strategy.helpers.ts';
import type { ModelPrediction } from '../../src/lib/types.ts';

test('analysis client posts the lineage-preserving batch contract', async () => {
	const source = await readFile('src/lib/api/predictions.ts', 'utf8');

	assert.match(source, /runStrategyBatch\(data: StrategyBatchRunRequest\)/);
	assert.match(source, /'\/api\/v1\/strategies\/run-batch'/);
});

test('analyze resolves the dataset once for all selected strategies and retries only failed rows', async () => {
	const source = await readFile('src/routes/analyze/+page.svelte', 'utf8');

	assert.match(source, /strategy_ids: strategyIds/);
	assert.doesNotMatch(source, /strategy_ids: \[strategyId\]/);
	assert.match(source, /await executeQueue\(failedIds, false\)/);
	assert.match(source, /allow_partial_resolution: false/);
});

test('analysis only sends ticket-eligible candidates to the bet slip and preserves prediction lineage', async () => {
	const source = await readFile('src/routes/analyze/+page.svelte', 'utf8');

	assert.match(source, /candidate\.ticketEligible === false/);
	assert.match(source, /modelPredictionId: candidate\.id/);
});

test('analyze hands exact dataset, run and prediction context to tickets', async () => {
	const source = await readFile('src/routes/analyze/+page.svelte', 'utf8');

	assert.match(source, /buildTicketsHandoffUrl\(selectedDataset\.id, successfulRunIds, selectedPredictionIds\)/);
	assert.match(source, /href=\{ticketsUrl\}/);
});

test('analysis candidate follows the model pick even when the market pick differs', () => {
	const prediction = {
		id: 1,
		run_id: 2,
		model_type: 'poisson',
		match_id: 3,
		market: '1x2',
		home_prob: 0.25,
		draw_prob: 0.3,
		away_prob: 0.45,
		home_odds: 4,
		draw_odds: 3.2,
		away_odds: 2.2,
		value_home: null,
		value_draw: null,
		value_away: null,
		expected_value: null,
		quality_report: {
			schema_version: 1,
			model: { pick: 'away', probabilities: { home: 0.25, draw: 0.3, away: 0.45 } },
			market: {
				pick: 'home',
				probabilities: { home: 0.5, draw: 0.3, away: 0.2 },
				odds: {
					home: { odds: 4 },
					draw: { odds: 3.2 },
					away: { odds: 2.25 }
				}
			}
		},
		created_at: '2026-07-13T00:00:00Z'
	} satisfies ModelPrediction;

	assert.deepEqual(selectModelOutcome(prediction), {
		selection: 'away',
		probability: 0.45,
		odds: 2.25
	});
});

test('analysis return context restores run and selected prediction ids', () => {
	assert.deepEqual(
		parseAnalysisReturnContext(
			new URLSearchParams('run_ids=11,12,11&candidate_ids=101,102,invalid&source=tickets')
		),
		{ runIds: [11, 12], predictionIds: [101, 102] }
	);
});

test('analysis results use a bounded 25-item window and grow incrementally', () => {
	const candidates = Array.from({ length: 123 }, (_, index) => index + 1);
	assert.deepEqual(visibleCandidateWindow(candidates, 25), candidates.slice(0, 25));
	assert.equal(nextCandidateWindowSize(25, candidates.length), 50);
	assert.equal(nextCandidateWindowSize(100, candidates.length), 123);
});

test('analysis blocks re-entry through hydration and ignores stale result requests', async () => {
	const source = await readFile('src/routes/analyze/+page.svelte', 'utf8');

	assert.match(source, /!batchRunning\s*&&\s*!resultsLoading/);
	assert.match(source, /batchRunning \|\|\s*resultsLoading/);
	assert.match(source, /resultRequests\.invalidate\(\)/);
	assert.match(source, /if \(!resultRequests\.isCurrent\(requestId\)\) return/);
	assert.match(source, /await loadRunResults\(\);[\s\S]*finally \{\s*batchRunning = false;/);
	assert.match(source, /function changeDataset\(\) \{\s*if \(batchRunning\) return;/);
	assert.match(source, /name="analysis-dataset"[\s\S]*disabled=\{batchRunning\}/);
});
