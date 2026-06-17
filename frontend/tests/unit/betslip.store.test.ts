import test from 'node:test';
import assert from 'node:assert/strict';
import { get } from 'svelte/store';

import {
	betslip,
	betslipCombinedOdds,
	betslipHasLegs,
	betslipPotentialReturn,
	createBetslipLeg
} from '../../src/lib/stores/betslip.ts';

test('betslip deduplicates equivalent legs and preserves model prediction link', () => {
	betslip.reset();

	const first = createBetslipLeg({
		matchId: 11,
		modelPredictionId: 42,
		matchName: 'A vs B',
		market: '1x2',
		selection: 'Home',
		odds: 1.95,
		source: 'prediction'
	});

	const duplicate = createBetslipLeg({
		matchId: 11,
		modelPredictionId: 77,
		matchName: 'A vs B',
		market: '1x2',
		selection: '1',
		odds: 2.05,
		source: 'prediction'
	});

	betslip.addLeg(first);
	betslip.addLeg(duplicate);

	const state = get(betslip);
	assert.equal(state.legs.length, 1);
	assert.equal(state.legs[0]?.modelPredictionId, 42);
	assert.equal(get(betslipHasLegs), true);
});

test('betslip computes accumulator odds and potential return from retained legs', () => {
	betslip.reset();
	betslip.setStake(25);
	betslip.addLeg(
		createBetslipLeg({
			matchId: 1,
			matchName: 'A vs B',
			market: '1x2',
			selection: 'Home',
			odds: 2,
			source: 'dashboard'
		})
	);
	betslip.addLeg(
		createBetslipLeg({
			matchId: 2,
			matchName: 'C vs D',
			market: 'BTTS',
			selection: 'Yes',
			odds: 1.5,
			source: 'value-bet'
		})
	);

	assert.equal(get(betslipCombinedOdds), 3);
	assert.equal(get(betslipPotentialReturn), 75);

	betslip.reset();
});
