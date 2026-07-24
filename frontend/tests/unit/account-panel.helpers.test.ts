import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

import {
	parseBankrollId,
	shouldAutoLoadAccountData
} from '../../src/lib/components/account-panel.helpers.ts';

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

test('normalizes select values to a positive numeric bankroll id', () => {
	assert.equal(parseBankrollId('7'), 7);
	assert.equal(parseBankrollId(9), 9);
	assert.equal(parseBankrollId(''), null);
	assert.equal(parseBankrollId('invalid'), null);
	assert.equal(parseBankrollId('0'), null);
});

test('AccountPanel normalizes every bankroll select before rendering risk policy', async () => {
	const source = await readFile('src/lib/components/AccountPanel.svelte', 'utf8');

	assert.match(source, /const bankrollId = parseBankrollId\(/);
	assert.match(source, /selectedBankrollId = bankrollId/);
	assert.match(source, /onchange=\{changeBankroll\}/);
	assert.doesNotMatch(source, /bind:value=\{selectedBankrollId as unknown as string\}/);
	assert.match(source, /<RiskPolicyPanel bankrollId=\{selectedBankrollId\}/);
});
