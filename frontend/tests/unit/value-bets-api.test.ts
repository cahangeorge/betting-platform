import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('value bets frontend client normalizes trust metadata from the backend feed', async () => {
	const source = await readFile('src/lib/api/predictions.ts', 'utf8');

	assert.match(source, /export function normalizeValueBetFeed/);
	assert.match(source, /type RawValueBetItem = Omit<ValueBetItem, 'reliability' \| 'trust'>/);
	assert.match(source, /typeof item\.reliability === 'string'/);
	assert.match(source, /trust\?\.is_ticket_eligible/);
	assert.match(source, /reliabilityObject\?\.is_ticket_eligible/);
	assert.match(source, /block_reasons: blockReasons/);
	assert.match(source, /quality_reasons: qualityReasons/);
	assert.match(source, /items: \(response\.items \?\? \[\]\)\.map\(normalizeValueBetItem\)/);
});

test('value bets route uses trust metadata to make add-to-betslip locking honest', async () => {
	const source = await readFile('src/routes/value-bets/+page.svelte', 'utf8');

	assert.match(source, /bet\.is_ticket_eligible === false \|\| bet\.trust\?\.is_ticket_eligible === false/);
	assert.match(source, /bet\.source_ok === false \|\| bet\.trust\?\.source_ok === false/);
	assert.match(source, /bet\.model_drift_flag \|\| bet\.trust\?\.model_drift_flag/);
	assert.match(source, /function getBetTrustReasons/);
	assert.match(source, /Betslip ready: \{trustReadyCount\}\/\{filteredBets\.length\}/);
	assert.match(source, /BetslipReviewCallout label=\{betslipReviewLabel\}/);
	assert.match(source, /bet\.quality_reasons\.map\(formatTrustReason\)\.join\(' · '\)/);
});
