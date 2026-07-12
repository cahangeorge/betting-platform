import test from 'node:test';
import assert from 'node:assert/strict';

import {
	formatResultsRefreshQueuedMessage,
	shouldAutoLoadTicketsData,
	verificationActionState
} from '../../src/lib/components/tickets-panel.helpers.ts';

test('does not auto-load when the server already provided an empty tickets snapshot', () => {
	assert.equal(
		shouldAutoLoadTicketsData({
			serverTickets: [],
			serverMatches: [],
		serverStats: { total: 0, won: 0, lost: 0, profit_loss: 0 },
		serverBankrolls: [],
		serverBatches: [],
		hasRequestedInitialLoad: false
	}),
		false
	);
});

test('auto-loads when server ticket data was not provided', () => {
	assert.equal(
		shouldAutoLoadTicketsData({
			serverTickets: undefined,
			serverMatches: undefined,
		serverStats: undefined,
		serverBankrolls: undefined,
		serverBatches: [],
		hasRequestedInitialLoad: false
	}),
		true
	);
});

test('auto-loads when server bankroll data was not provided', () => {
	assert.equal(
		shouldAutoLoadTicketsData({
		serverTickets: [],
		serverMatches: [],
		serverStats: { total: 0, won: 0, lost: 0, profit_loss: 0 },
		serverBankrolls: undefined,
		serverBatches: [],
		hasRequestedInitialLoad: false
	}),
		true
	);
});

test('does not auto-load more than once', () => {
	assert.equal(
		shouldAutoLoadTicketsData({
		serverTickets: undefined,
		serverMatches: undefined,
		serverStats: undefined,
		serverBankrolls: undefined,
		serverBatches: undefined,
		hasRequestedInitialLoad: true
	}),
		false
	);
});

test('result refresh messaging reports a queued job without claiming score changes', () => {
	const message = formatResultsRefreshQueuedMessage({
		jobId: 19,
		runId: 42,
		matchCount: 3
	});

	assert.match(message, /job #19 \(run #42\)/);
	assert.match(message, /3 open-ticket matches/);
	assert.match(message, /has not refreshed scores or settled tickets yet/);
});

test('blocks verification while final-results refresh is queued or running', () => {
	assert.deepEqual(
		verificationActionState({
			settlementChecking: false,
			resultsRefreshing: false,
			watchingResultsRefresh: true
		}),
		{ disabled: true, label: 'Waiting for final-results refresh...' }
	);
});

test('keeps the verification action available only when no refresh or settlement is running', () => {
	assert.deepEqual(
		verificationActionState({
			settlementChecking: false,
			resultsRefreshing: false,
			watchingResultsRefresh: false
		}),
		{ disabled: false, label: 'Verify and settle' }
	);
});
