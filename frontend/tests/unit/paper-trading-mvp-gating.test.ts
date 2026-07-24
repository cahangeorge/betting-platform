import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('production paper trading is gated in server loads and both user-facing surfaces', () => {
	const accountServer = readFileSync('src/routes/account/+page.server.ts', 'utf8');
	const accountPage = readFileSync('src/routes/account/+page.svelte', 'utf8');
	const ticketsServer = readFileSync('src/routes/tickets/+page.server.ts', 'utf8');
	const ticketsPage = readFileSync('src/routes/tickets/+page.svelte', 'utf8');
	const ticketsPanel = readFileSync('src/lib/components/TicketsPanel.svelte', 'utf8');

	assert.match(accountServer, /BET_TRADING_PAPER_ENABLED === 'true'/);
	assert.match(ticketsServer, /BET_TRADING_PAPER_ENABLED === 'true'/);
	assert.match(accountPage, /\{#if pageData\.paperTradingEnabled\}/);
	assert.match(ticketsPage, /paperTradingEnabled=\{pageData\.paperTradingEnabled \?\? false\}/);
	assert.match(ticketsPanel, /\{#if paperTradingEnabled\}.*Simulează BACK LIMIT/s);
});
