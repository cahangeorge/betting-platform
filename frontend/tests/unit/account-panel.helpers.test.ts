import test from 'node:test';
import assert from 'node:assert/strict';

import { shouldAutoLoadAccountData } from '../../src/lib/components/account-panel.helpers.ts';

test('does not auto-load when the server already provided an empty account snapshot', () => {
	assert.equal(
		shouldAutoLoadAccountData({
			serverBankrolls: [],
			serverAccounts: [],
			serverLedger: [],
			hasRequestedInitialLoad: false
		}),
		false
	);
});

test('auto-loads when server account data was not provided', () => {
	assert.equal(
		shouldAutoLoadAccountData({
			serverBankrolls: undefined,
			serverAccounts: undefined,
			serverLedger: undefined,
			hasRequestedInitialLoad: false
		}),
		true
	);
});

test('does not auto-load more than once', () => {
	assert.equal(
		shouldAutoLoadAccountData({
			serverBankrolls: undefined,
			serverAccounts: undefined,
			serverLedger: undefined,
			hasRequestedInitialLoad: true
		}),
		false
	);
});
