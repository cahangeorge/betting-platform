import assert from 'node:assert/strict';
import test from 'node:test';

import {
	buildTicketsHandoffUrl,
	chooseAnalysisDataset,
	datasetCoverage,
	datasetJobId,
	hasStrategyAvgEdge,
	normalizeStrategies,
	progressFromBatchRun
} from '../../src/routes/analyze/strategy.helpers.ts';
import type { Dataset } from '../../src/lib/types.ts';

test('normalizeStrategies backfills missing analytics fields with null', () => {
	const strategies = normalizeStrategies([
		{
			id: 7,
			name: 'Poisson Core',
			description: null,
			model_type: 'poisson',
			parameters: {},
			weights: null,
			is_active: true,
			created_at: '2026-06-17T00:00:00Z',
			updated_at: '2026-06-17T00:00:00Z'
		}
	]);

	assert.deepEqual(strategies[0], {
		id: 7,
		name: 'Poisson Core',
		description: null,
		model_type: 'poisson',
		parameters: {},
		weights: null,
		is_active: true,
		created_at: '2026-06-17T00:00:00Z',
		updated_at: '2026-06-17T00:00:00Z',
		last_run: null,
		avg_edge: null,
		avg_win_rate: null
	});
});

test('hasStrategyAvgEdge only accepts finite numbers', () => {
	assert.equal(hasStrategyAvgEdge({ avg_edge: 4.2 }), true);
	assert.equal(hasStrategyAvgEdge({ avg_edge: null }), false);
	assert.equal(hasStrategyAvgEdge({ avg_edge: Number.NaN }), false);
});

function dataset(
	id: number,
	jobId: number,
	league: string,
	createdAt: string,
	matchesCount = 1
): Dataset {
	return {
		id,
		name: `Dataset ${id}`,
		source: 'oddsportal',
		data: {
			job_id: jobId,
			params: { leagues: [league] },
			matches: [
				{ league, match_date: '2026-07-20T18:00:00Z' },
				{ league: `${league} Reserve`, match_date: '2026-07-22T18:00:00Z' }
			]
		},
		matches_count: matchesCount,
		created_at: createdAt
	};
}

test('analysis dataset prefers the newest completed Argentina dataset over a newer failed dataset', () => {
	const failedLatest = dataset(30, 192, 'argentina-liga-profesional', '2026-07-13T12:00:00Z');
	const completedArgentina = dataset(29, 181, 'argentina-liga-profesional', '2026-07-13T11:00:00Z', 56);

	const selected = chooseAnalysisDataset([
		{ dataset: failedLatest, jobId: 192, jobStatus: 'failed' },
		{ dataset: completedArgentina, jobId: 181, jobStatus: 'completed' }
	]);

	assert.equal(selected?.dataset.id, 29);
	assert.equal(datasetJobId(selected!.dataset), 181);
});

test('explicit dataset context is preserved even when it is not the default-ready dataset', () => {
	const failedLatest = dataset(30, 192, 'argentina-liga-profesional', '2026-07-13T12:00:00Z');
	const completedArgentina = dataset(29, 181, 'argentina-liga-profesional', '2026-07-13T11:00:00Z', 56);
	const selected = chooseAnalysisDataset(
		[
			{ dataset: failedLatest, jobId: 192, jobStatus: 'failed' },
			{ dataset: completedArgentina, jobId: 181, jobStatus: 'completed' }
		],
		30
	);

	assert.equal(selected?.dataset.id, 30);
});

test('dataset coverage extracts unique leagues and temporal bounds', () => {
	const coverage = datasetCoverage(dataset(29, 181, 'Argentina Primera', '2026-07-13T11:00:00Z'));
	assert.deepEqual(coverage.leagues, ['Argentina Primera', 'Argentina Primera Reserve']);
	assert.equal(coverage.dateFrom, '2026-07-20T18:00:00Z');
	assert.equal(coverage.dateTo, '2026-07-22T18:00:00Z');
});

test('dataset helpers understand the current scraper league_name and countries payload', () => {
	const currentShape: Dataset = {
		id: 29,
		name: 'scrape_odds:2026-07-13',
		source: 'oddsportal',
		data: {
			job_id: 181,
			params: { countries: ['Argentina'] },
			matches: [
				{ league_name: 'Liga Profesional', match_date: '2026-07-20T18:00:00Z' },
				{ league_name: 'Primera Nacional', match_date: '2026-07-21T18:00:00Z' }
			]
		},
		matches_count: 56,
		created_at: '2026-07-13T11:00:00Z'
	};

	assert.equal(chooseAnalysisDataset([{ dataset: currentShape, jobId: 181, jobStatus: 'completed' }])?.dataset.id, 29);
	assert.deepEqual(datasetCoverage(currentShape).leagues, ['Liga Profesional', 'Primera Nacional']);
});

test('batch statuses normalize deduplicated runs as reused', () => {
	assert.deepEqual(
		progressFromBatchRun({
			strategy_id: 4,
			run_id: 99,
			status: 'deduped',
			matches_count: 56,
			deduped: true
		}),
		{
			strategyId: 4,
			status: 'reused',
			runId: 99,
			matchesCount: 56,
			error: null
		}
	);
});

test('tickets handoff keeps dataset, unique runs, and selected predictions', () => {
	assert.equal(
		buildTicketsHandoffUrl(29, [11, 12, 11], [101, 102]),
		'/tickets?dataset_id=29&run_ids=11%2C12&prediction_ids=101%2C102&source=analyze'
	);
});
