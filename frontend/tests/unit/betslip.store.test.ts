import test from 'node:test';
import assert from 'node:assert/strict';
import { get } from 'svelte/store';

import {
	BETSLIP_DRAFT_STORAGE_KEY,
	betslip,
	betslipCombinedOdds,
	betslipHasLegs,
	betslipPotentialReturn,
	createBetslipLeg
} from '../../src/lib/stores/betslip.ts';

class SessionStorageMock {
	private values = new Map<string, string>();

	getItem(key: string): string | null {
		return this.values.get(key) ?? null;
	}

	setItem(key: string, value: string): void {
		this.values.set(key, value);
	}

	removeItem(key: string): void {
		this.values.delete(key);
	}
}

const sessionStorage = new SessionStorageMock();
Object.assign(globalThis, { window: globalThis, sessionStorage });

function draftKey(userId: number): string {
	return `${BETSLIP_DRAFT_STORAGE_KEY}:user:${userId}`;
}

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

test('betslip canonicalizes over/under 2.5 market and selection aliases', () => {
	betslip.reset();

	const first = createBetslipLeg({
		matchId: 21,
		matchName: 'A vs B',
		market: 'ou_2_5',
		selection: 'Over',
		odds: 1.9
	});
	const duplicate = createBetslipLeg({
		matchId: 21,
		matchName: 'A vs B',
		market: 'Over/Under 2.5',
		selection: 'Over 2.5',
		odds: 2
	});

	assert.equal(first.marketKey, 'ou_2_5');
	assert.equal(first.selectionKey, 'over');
	assert.equal(duplicate.marketKey, 'ou_2_5');
	assert.equal(duplicate.selectionKey, 'over');
	betslip.addLeg(first);
	betslip.addLeg(duplicate);
	assert.equal(get(betslip).legs.length, 1);

	const under = createBetslipLeg({
		matchId: 22,
		matchName: 'C vs D',
		market: 'over_under_2.5',
		selection: 'U 2.5',
		odds: 1.8
	});
	assert.equal(under.marketKey, 'ou_2_5');
	assert.equal(under.selectionKey, 'under');

	betslip.reset();
});

test('betslip isolates session drafts by authenticated user and clears the in-memory draft on logout', () => {
	const firstUserId = 101;
	const secondUserId = 202;
	betslip.setOwner(firstUserId);
	betslip.addLeg(
		createBetslipLeg({
			matchId: 31,
			matchName: 'First user match',
			market: '1x2',
			selection: 'Home',
			odds: 1.8
		})
	);

	assert.equal(get(betslip).legs[0]?.matchName, 'First user match');
	assert.ok(sessionStorage.getItem(draftKey(firstUserId)));

	betslip.setOwner(secondUserId);
	assert.equal(get(betslip).legs.length, 0);
	assert.equal(sessionStorage.getItem(draftKey(secondUserId)), null);

	betslip.addLeg(
		createBetslipLeg({
			matchId: 32,
			matchName: 'Second user match',
			market: 'BTTS',
			selection: 'Yes',
			odds: 1.9
		})
	);
	betslip.setOwner(null);
	assert.equal(get(betslip).legs.length, 0);

	betslip.setOwner(firstUserId);
	assert.equal(get(betslip).legs[0]?.matchName, 'First user match');
	betslip.reset();
	betslip.setOwner(null);
});
