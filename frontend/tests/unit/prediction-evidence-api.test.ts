import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('prediction evidence client uses the run-scoped score-grid contract', async () => {
	const source = await readFile('src/lib/api/predictions.ts', 'utf8');

	assert.match(source, /async getScoreGrids\(runId: number\)/);
	assert.match(source, /\/api\/v1\/predictions\/runs\/\$\{runId\}\/score-grids/);
	assert.match(source, /async getCalibration\(runId\?: number\)/);
});

test('score-grid UI keeps the analysis-only boundary and legacy fallback visible', async () => {
	const source = await readFile('src/lib/components/AnalysisModelEvidence.svelte', 'utf8');

	assert.match(source, /selectedScore\.ticket_generation_eligible|nu le trimite în generatorul de bilete/i);
	assert.match(source, /score_grid_not_persisted_for_prediction/);
	assert.match(source, /displayed_probability_mass/);
	assert.doesNotMatch(source, /presupune scoruri Poisson independente/);
	assert.match(source, /Snapshot explicativ produs de modelul/);
});
