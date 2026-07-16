import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { normalizeValueBetFeed } from '../../src/lib/api/value-bet-normalization.ts';

const rawValueBet = {
	id: 7,
	match_id: 42,
	league: 'Argentina',
	home_team: 'Home',
	away_team: 'Away',
	kickoff: '2026-07-14T12:00:00Z',
	market: '1x2',
	selection: 'home',
	model_prob: 0.6,
	odds: 2.1,
	edge: 12.4,
	model_type: 'PoissonGoalsModel',
	confidence: 60,
	source: 'odds:Book',
	is_betslip_eligible: false,
	block_reasons: ['data_stale']
};

test('value bets frontend maps backend betslip eligibility to the canonical ticket field', () => {
	const response = normalizeValueBetFeed({
		items: [{ ...rawValueBet, is_ticket_eligible: true }],
		source: 'prediction',
		is_demo: false,
		generated_at: '2026-07-13T12:00:00Z'
	});

	assert.equal(response.items[0].is_ticket_eligible, false);
	assert.equal('is_betslip_eligible' in response.items[0], false);
});

test('value bets frontend client normalizes trust metadata from the backend feed', async () => {
	const source = await readFile('src/lib/api/value-bet-normalization.ts', 'utf8');

	assert.match(source, /export function normalizeValueBetFeed/);
	assert.match(source, /is_betslip_eligible/);
	assert.match(source, /typeof item\.reliability === 'string'/);
	assert.match(source, /trust\?\.is_ticket_eligible/);
	assert.match(source, /reliabilityObject\?\.is_ticket_eligible/);
	assert.match(source, /block_reasons: blockReasons/);
	assert.match(source, /quality_reasons: qualityReasons/);
	assert.match(source, /items: \(response\.items \?\? \[\]\)\.map\(normalizeValueBetItem\)/);
});

test('value bets route uses trust metadata to make add-to-betslip locking honest', async () => {
	const source = await readFile('src/lib/features/opportunities/ValueOpportunities.svelte', 'utf8');

	assert.match(source, /bet\.is_ticket_eligible === false \|\| bet\.trust\?\.is_ticket_eligible === false/);
	assert.match(source, /bet\.source_ok === false \|\| bet\.trust\?\.source_ok === false/);
	assert.match(source, /bet\.model_drift_flag \|\| bet\.trust\?\.model_drift_flag/);
	assert.match(source, /function getBetTrustReasons/);
	assert.match(source, /Betslip ready: \{trustReadyCount\}\/\{filteredBets\.length\}/);
	assert.match(source, /BetslipReviewCallout label=\{betslipReviewLabel\}/);
	assert.match(source, /bet\.quality_reasons\.map\(formatTrustReason\)\.join\(' · '\)/);
});
