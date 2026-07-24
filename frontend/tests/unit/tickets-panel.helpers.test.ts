import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

import {
	analyzeReturnHref,
	formatResultsRefreshQueuedMessage,
	generatedBatchLoadState,
	parseTicketHandoff,
	selectionCountLabel,
	shouldAutoLoadTicketsData,
	ticketCountLabel,
	ticketGenerationPreflight,
	ticketStructuralSignals,
	ticketLegSnapshotCompleteness,
	ticketRunIdsFromReport,
	verificationActionState
} from '../../src/lib/components/tickets-panel.helpers.ts';
import type { Ticket } from '../../src/lib/types.ts';

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

test('parses the explicit Analyze handoff, deduplicates IDs, and accepts the legacy prediction_ids alias', () => {
	assert.deepEqual(
		parseTicketHandoff(
			new URLSearchParams(
				'dataset_id=29&run_ids=11,12,11,invalid&prediction_ids=101,102&source=analyze'
			)
		),
		{
			source: 'analyze',
			datasetId: 29,
			runIds: [11, 12],
			candidateIds: [101, 102]
		}
	);
});

test('builds a return link that preserves the reviewed analysis lineage', () => {
	assert.equal(
		analyzeReturnHref({ source: 'analyze', datasetId: 29, runIds: [11, 12], candidateIds: [101] }),
		'/analyze?dataset_id=29&run_ids=11%2C12&candidate_ids=101&source=tickets'
	);
});

test('ticket generation preflight requires explicit lineage, bankroll, markets, and a valid odds range', () => {
	const result = ticketGenerationPreflight({
		runId: '',
		bankrollId: '',
		ticketCount: '0',
		markets: [],
		minOdds: '5',
		maxOdds: '2'
	});

	assert.equal(result.valid, false);
	assert.deepEqual(Object.keys(result.errors).sort(), [
		'bankrollId',
		'markets',
		'maxOdds',
		'runId',
		'ticketCount'
	]);
});

test('ticket generation preflight accepts a fully configured batch', () => {
	assert.deepEqual(
		ticketGenerationPreflight({
			runId: '42',
			bankrollId: '7',
			ticketCount: '5',
			markets: ['1x2'],
			minOdds: '1.20',
			maxOdds: '5.00'
		}),
		{ valid: true, errors: {} }
	);
});

test('ticket generation preflight accepts explicit multi-run lineage from Analyze', () => {
	assert.deepEqual(
		ticketGenerationPreflight({
			runId: '',
			runIds: [11, 12],
			bankrollId: '7',
			ticketCount: '5',
			markets: ['1x2'],
			minOdds: '1.20',
			maxOdds: '5.00'
		}),
		{ valid: true, errors: {} }
	);
});

test('tickets sends the exact handoff subset and keeps draft activation or discard explicit', async () => {
	const [panelSource, apiSource] = await Promise.all([
		readFile('src/lib/components/TicketsPanel.svelte', 'utf8'),
		readFile('src/lib/api/tickets.ts', 'utf8')
	]);

	assert.match(panelSource, /prediction_ids: handoff\.candidateIds\.length > 0 \? handoff\.candidateIds : undefined/);
	assert.match(panelSource, /run_ids: generationRunIds/);
	assert.match(panelSource, /await ticketsApi\.activateBatch\(generatedBatchId, \{/);
	assert.match(panelSource, /expected_revision: generatedBatchRevision/);
	assert.match(panelSource, /await ticketsApi\.refreshBatch\(generatedBatchId, generatedBatchRevision\)/);
	assert.doesNotMatch(panelSource, /ticket-generation-stake/);
	assert.match(panelSource, /await ticketsApi\.discardDraftBatch\(discardedBatchId\)/);
	assert.match(panelSource, /Renunță la lotul draft/);
	assert.match(panelSource, /Confirmă renunțarea/);
	assert.match(panelSource, /await ticketsApi\.getBatchTickets\(batchId\)/);
	assert.match(panelSource, /await loadTickets\(\{ preserveReview: true \}\)/);
	assert.match(panelSource, /async function pollVisibleTicketContext\(\)/);
	assert.match(panelSource, /if \(document\.hidden\) return/);
	assert.match(panelSource, /activeTab === 'history'/);
	assert.match(panelSource, /activeTab === 'review'/);
	assert.match(panelSource, /setInterval\(\(\) => void pollVisibleTicketContext\(\), 30000\)/);
	assert.match(panelSource, /await loadFullGeneratedBatch\(batchId\)/);
	assert.match(panelSource, /!generatedBatchState\.complete/);
	assert.match(apiSource, /sp\.set\('per_page', '100'\)/);
	assert.match(apiSource, /\/batches\/\$\{batchId\}\/activate/);
	assert.match(apiSource, /this\.del\(`\/api\/v1\/tickets\/batches\/\$\{batchId\}`\)/);
});

test('uses correct Romanian ticket and selection pluralization', () => {
	assert.equal(ticketCountLabel(1), '1 bilet');
	assert.equal(ticketCountLabel(2), '2 bilete');
	assert.equal(selectionCountLabel(1), '1 selecție');
	assert.equal(selectionCountLabel(3), '3 selecții');
});

test('uses exact per-ticket run lineage and never attributes every run from a multi-run batch', () => {
	const report = {
		generated_ticket_lineage: [
			{ ticket_id: 7, prediction_ids: [101], prediction_run_ids: [12], match_ids: [41] }
		]
	};

	assert.deepEqual(ticketRunIdsFromReport(7, report, [11, 12]), [12]);
	assert.deepEqual(ticketRunIdsFromReport(8, report, [11, 12]), []);
	assert.deepEqual(ticketRunIdsFromReport(8, report, [11]), [11]);
});

test('generated batch review is incomplete until every persisted draft is loaded', () => {
	const draft = (id: number, status: Ticket['status'] = 'generated') =>
		({ id, status }) as Ticket;

	assert.deepEqual(
		generatedBatchLoadState({
			expectedCount: 50,
			tickets: Array.from({ length: 20 }, (_, index) => draft(index + 1)),
			loading: false
		}),
		{ loadedCount: 20, expectedCount: 50, complete: false }
	);
	assert.equal(
		generatedBatchLoadState({
			expectedCount: 50,
			tickets: Array.from({ length: 50 }, (_, index) => draft(index + 1)),
			loading: false
		}).complete,
		true
	);
	assert.equal(
		generatedBatchLoadState({
			expectedCount: 2,
			tickets: [draft(1), draft(2, 'open')],
			loading: false
		}).complete,
		false
	);
});

test('flags same-match accumulator legs as a structural dependency', () => {
	const ticket = {
		id: 1,
		legs: [
			{ id: 11, match_id: 7, market: '1x2' },
			{ id: 12, match_id: 7, market: 'btts' },
			{ id: 13, match_id: 8, market: 'ou_2_5' }
		]
	} as Ticket;

	assert.deepEqual(ticketStructuralSignals(ticket), [
		{
			kind: 'same_match_dependency',
			matchIds: [7],
			legIds: [11, 12],
			markets: ['1x2', 'btts'],
			severity: 'high',
			label: 'Dependență structurală · același meci',
			message: '2 selecții provin din același meci. Probabilitățile nu trebuie înmulțite ca și cum ar fi independente.'
		}
	]);
});

test('detects concentration across valid unique-match tickets without claiming statistical correlation', () => {
	const ticket = {
		legs: [
			{ id: 21, match_id: 17, market: '1x2', match: { home_team: 'River', away_team: 'A', league: 'Liga', start_time: '2026-07-17T12:00:00Z' } },
			{ id: 22, match_id: 18, market: 'btts', match: { home_team: 'B', away_team: 'River', league: 'Liga', start_time: '2026-07-17T16:00:00Z' } }
		]
	} as Ticket;

	const warnings = ticketStructuralSignals(ticket);
	assert.equal(warnings.some((warning) => warning.kind === 'repeated_team_concentration'), true);
	assert.equal(warnings.some((warning) => warning.kind === 'competition_window_concentration'), true);
	assert.equal(warnings.some((warning) => /corelație statistică măsurată/.test(warning.message)), true);
});

test('reports immutable ticket-leg snapshot completeness', () => {
	const ticket = {
		legs: [
			{ id: 1, prediction_run_id_snapshot: 4, model_probability_snapshot: 0.62, expected_value_snapshot: 0.08 },
			{ id: 2, prediction_run_id_snapshot: null, model_probability_snapshot: null, expected_value_snapshot: null }
		]
	} as Ticket;

	assert.deepEqual(ticketLegSnapshotCompleteness(ticket), { complete: 1, total: 2 });
});
