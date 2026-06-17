import test from 'node:test';
import assert from 'node:assert/strict';

import { shouldAutoLoadTicketsData } from '../../src/lib/components/tickets-panel.helpers.ts';

test('does not auto-load when the server already provided an empty tickets snapshot', () => {
	assert.equal(
		shouldAutoLoadTicketsData({
			serverTickets: [],
			serverMatches: [],
			serverStats: { total: 0, won: 0, lost: 0, profit_loss: 0 },
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
			hasRequestedInitialLoad: true
		}),
		false
	);
});
