import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('risk API uses the bankroll-scoped policy and pause contracts', async () => {
	const source = await readFile('src/lib/api/risk.ts', 'utf8');

	assert.match(source, /\/api\/v1\/bankroll\/\$\{bankrollId\}\/\$\{suffix\}/);
	assert.match(source, /bankrollPath\(bankrollId, 'risk-policy'\)/);
	assert.match(source, /bankrollPath\(bankrollId, 'pause'\)/);
	assert.match(source, /statusCode === 404/);
	assert.match(source, /normalizeRiskPolicyOverview/);
	assert.match(source, /pending_policy/);
	assert.match(source, /open_exposure_pct/);
	assert.match(source, /max_daily_stake_pct/);
	assert.match(source, /max_weekly_stake_pct/);
});

test('risk policy panel is fail-closed and exposes the hard ceilings', async () => {
	const source = await readFile('src/lib/components/RiskPolicyPanel.svelte', 'utf8');

	assert.match(source, /bankrollId: number/);
	assert.match(source, /onSaved\?: \(overview: RiskPolicyOverview\) => void/);
	assert.match(source, /Niciun câmp nu este completat automat/);
	assert.match(source, /5% \/ ticket/);
	assert.match(source, /20% expunere deschisă/);
	assert.match(source, /Metoda de staking trebuie aleasă explicit/);
	assert.match(source, /Permisiunea pentru acumulatoare/);
	assert.match(source, /Permisiunea pentru automatizare/);
	assert.match(source, /onSaved\?\.\(saved\)/);
});

test('risk policy panel covers pending relaxation, usage and responsible-use pause', async () => {
	const source = await readFile('src/lib/components/RiskPolicyPanel.svelte', 'utf8');

	assert.match(source, /Relaxare în așteptare/);
	assert.match(source, /Utilizare curentă/);
	assert.match(source, /Expunere deschisă/);
	assert.match(source, /Pauză voluntară/);
	assert.match(source, /paused_until: until\.toISOString\(\)/);
	assert.match(source, /Pauza trebuie să se încheie în viitor/);
});
