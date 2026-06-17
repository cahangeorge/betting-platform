import assert from 'node:assert/strict';
import test from 'node:test';

import { hasStrategyAvgEdge, normalizeStrategies } from '../../src/routes/predict/strategy.helpers.ts';

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
