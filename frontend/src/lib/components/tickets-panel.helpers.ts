import type { Ticket, TicketGenerationReport, TicketStatus, TicketType } from '$lib/types';

export function ticketCountLabel(count: number): string {
	return `${count} ${count === 1 ? 'bilet' : 'bilete'}`;
}

export function selectionCountLabel(count: number): string {
	return `${count} ${count === 1 ? 'selecție' : 'selecții'}`;
}

export interface TicketStructuralSignal {
	kind: 'same_match_dependency' | 'repeated_team_concentration' | 'competition_window_concentration';
	matchIds: number[];
	legIds: number[];
	markets: string[];
	severity: 'high' | 'medium' | 'low';
	label: string;
	message: string;
}

export function ticketStructuralSignals(ticket: Ticket): TicketStructuralSignal[] {
	const warnings: TicketStructuralSignal[] = [];
	const legsByMatch = new Map<number, Ticket['legs']>();
	for (const leg of ticket.legs) {
		const grouped = legsByMatch.get(leg.match_id) ?? [];
		grouped.push(leg);
		legsByMatch.set(leg.match_id, grouped);
	}

	warnings.push(...[...legsByMatch.entries()]
		.filter(([, legs]) => legs.length > 1)
		.map(([matchId, legs]) => ({
			kind: 'same_match_dependency' as const,
			matchIds: [matchId],
			legIds: legs.map((leg) => leg.id),
			markets: [...new Set(legs.map((leg) => leg.market))],
			severity: 'high' as const,
			label: 'Dependență structurală · același meci',
			message: `${legs.length} selecții provin din același meci. Probabilitățile nu trebuie înmulțite ca și cum ar fi independente.`
		})));

	const legsByTeam = new Map<string, { label: string; legs: Ticket['legs'] }>();
	for (const leg of ticket.legs) {
		for (const team of [leg.match?.home_team, leg.match?.away_team]) {
			const label = team?.trim();
			if (!label) continue;
			const key = label.toLocaleLowerCase('ro');
			const grouped = legsByTeam.get(key) ?? { label, legs: [] };
			grouped.legs.push(leg);
			legsByTeam.set(key, grouped);
		}
	}
	for (const { label, legs } of legsByTeam.values()) {
		const matchIds = [...new Set(legs.map((leg) => leg.match_id))];
		if (matchIds.length < 2) continue;
		warnings.push({
			kind: 'repeated_team_concentration',
			matchIds,
			legIds: [...new Set(legs.map((leg) => leg.id))],
			markets: [...new Set(legs.map((leg) => leg.market))],
			severity: 'medium',
			label: `Concentrare pe echipă · ${label}`,
			message: `${label} apare în ${matchIds.length} meciuri ale aceluiași bilet. O informație comună despre echipă poate afecta mai multe selecții simultan.`
		});
	}

	const sixHours = 6 * 60 * 60 * 1000;
	for (let left = 0; left < ticket.legs.length; left += 1) {
		for (let right = left + 1; right < ticket.legs.length; right += 1) {
			const first = ticket.legs[left];
			const second = ticket.legs[right];
			if (first.match_id === second.match_id) continue;
			const firstLeague = first.match?.league?.trim();
			const secondLeague = second.match?.league?.trim();
			const firstKickoff = first.match?.start_time ? Date.parse(first.match.start_time) : Number.NaN;
			const secondKickoff = second.match?.start_time ? Date.parse(second.match.start_time) : Number.NaN;
			if (
				!firstLeague ||
				!secondLeague ||
				firstLeague.toLocaleLowerCase('ro') !== secondLeague.toLocaleLowerCase('ro') ||
				!Number.isFinite(firstKickoff) ||
				!Number.isFinite(secondKickoff) ||
				Math.abs(firstKickoff - secondKickoff) > sixHours
			) continue;
			warnings.push({
				kind: 'competition_window_concentration',
				matchIds: [first.match_id, second.match_id],
				legIds: [first.id, second.id],
				markets: [...new Set([first.market, second.market])],
				severity: 'low',
				label: `Concentrare contextuală · ${firstLeague}`,
				message: 'Două selecții sunt din aceeași competiție și încep într-o fereastră de șase ore. Este un semnal conservator de concentrare, nu o corelație statistică măsurată.'
			});
		}
	}

	return warnings;
}

export function ticketLegSnapshotCompleteness(ticket: Ticket): { complete: number; total: number } {
	return {
		complete: ticket.legs.filter(
			(leg) =>
				typeof leg.model_probability_snapshot === 'number' &&
				typeof leg.expected_value_snapshot === 'number' &&
				typeof leg.prediction_run_id_snapshot === 'number'
		).length,
		total: ticket.legs.length
	};
}

export function ticketStatusLabel(status: TicketStatus | string): string {
	return (
		{
			generated: 'Generat · necesită revizuire',
			open: 'Activ',
			watchlist: 'În monitorizare',
			pending: 'În așteptare',
			won: 'Câștigat',
			lost: 'Pierdut',
			cashed_out: 'Închis anticipat',
			void: 'Anulat'
		} as Record<string, string>
	)[status] ?? status;
}

export function ticketTypeLabel(type: TicketType | string): string {
	return ({ single: 'Simplu', accumulator: 'Multiplu', system: 'Sistem' } as Record<string, string>)[type] ?? type;
}

export function ticketRunIdsFromReport(
	ticketId: number,
	report: TicketGenerationReport | null | undefined,
	batchRunIds: number[] = []
): number[] {
	const lineage = report?.generated_ticket_lineage?.find((item) => item.ticket_id === ticketId);
	const exactRunIds = [...new Set(lineage?.prediction_run_ids ?? [])].filter(
		(value) => Number.isSafeInteger(value) && value > 0
	);
	if (exactRunIds.length > 0) return exactRunIds;
	const uniqueBatchRunIds = [...new Set(batchRunIds)].filter(
		(value) => Number.isSafeInteger(value) && value > 0
	);
	return uniqueBatchRunIds.length === 1 ? uniqueBatchRunIds : [];
}

export function shouldAutoLoadTicketsData(input: {
	serverTickets?: unknown[];
	serverMatches?: unknown[];
	serverStats?: { total: number; won: number; lost: number; profit_loss: number };
	serverBankrolls?: unknown[];
	serverBatches?: unknown[];
	hasRequestedInitialLoad: boolean;
}): boolean {
	if (input.hasRequestedInitialLoad) {
		return false;
	}

	return (
		input.serverTickets === undefined ||
		input.serverMatches === undefined ||
		input.serverStats === undefined ||
		input.serverBankrolls === undefined ||
		input.serverBatches === undefined
	);
}

export function formatResultsRefreshQueuedMessage(input: {
	jobId: number;
	runId: number | null | undefined;
	matchCount: number;
}): string {
	const scope = input.matchCount === 1 ? '1 open-ticket match' : `${input.matchCount} open-ticket matches`;
	const run = input.runId ? ` (run #${input.runId})` : '';
	return `Queued final-results refresh job #${input.jobId}${run} for ${scope}. It has not refreshed scores or settled tickets yet.`;
}

export function verificationActionState(input: {
	settlementChecking: boolean;
	resultsRefreshing: boolean;
	watchingResultsRefresh: boolean;
}): { disabled: boolean; label: string } {
	if (input.settlementChecking) {
		return { disabled: true, label: 'Verifying and settling...' };
	}

	if (input.resultsRefreshing) {
		return { disabled: true, label: 'Refreshing final results...' };
	}

	if (input.watchingResultsRefresh) {
		return { disabled: true, label: 'Waiting for final-results refresh...' };
	}

	return { disabled: false, label: 'Verify and settle' };
}

export interface TicketHandoff {
	source: 'analyze' | 'direct';
	datasetId: number | null;
	runIds: number[];
	candidateIds: number[];
}

function positiveInteger(value: string | null): number | null {
	if (!value) return null;
	const parsed = Number(value);
	return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function positiveIntegerList(value: string | null): number[] {
	if (!value) return [];
	return [...new Set(value.split(',').map((entry) => positiveInteger(entry.trim())).filter((entry): entry is number => entry !== null))];
}

export function parseTicketHandoff(searchParams: URLSearchParams): TicketHandoff {
	const datasetId = positiveInteger(searchParams.get('dataset_id'));
	const runIds = positiveIntegerList(searchParams.get('run_ids'));
	const candidateIds = positiveIntegerList(
		searchParams.get('candidate_ids') ?? searchParams.get('prediction_ids')
	);
	const fromAnalyze =
		searchParams.get('source') === 'analyze' ||
		datasetId !== null ||
		runIds.length > 0 ||
		candidateIds.length > 0;

	return {
		source: fromAnalyze ? 'analyze' : 'direct',
		datasetId,
		runIds,
		candidateIds
	};
}

export function analyzeReturnHref(handoff: TicketHandoff): string {
	const searchParams = new URLSearchParams();
	if (handoff.datasetId !== null) searchParams.set('dataset_id', String(handoff.datasetId));
	if (handoff.runIds.length > 0) searchParams.set('run_ids', handoff.runIds.join(','));
	if (handoff.candidateIds.length > 0) searchParams.set('candidate_ids', handoff.candidateIds.join(','));
	searchParams.set('source', 'tickets');
	return `/analyze?${searchParams.toString()}`;
}

export interface TicketGenerationPreflight {
	valid: boolean;
	errors: {
		runId?: string;
		bankrollId?: string;
		ticketCount?: string;
		markets?: string;
		minOdds?: string;
		maxOdds?: string;
	};
}

export function ticketGenerationPreflight(input: {
	runId: string;
	runIds?: number[];
	bankrollId: string;
	ticketCount: string;
	markets: string[];
	minOdds: string;
	maxOdds: string;
}): TicketGenerationPreflight {
	const errors: TicketGenerationPreflight['errors'] = {};
	const runId = positiveInteger(input.runId.trim());
	const runIds = (input.runIds ?? []).filter(
		(value) => Number.isSafeInteger(value) && value > 0
	);
	const bankrollId = positiveInteger(input.bankrollId.trim());
	const ticketCount = Number(input.ticketCount);
	const minOdds = Number(input.minOdds);
	const maxOdds = Number(input.maxOdds);

	if (runId === null && runIds.length === 0) errors.runId = 'Selectează cel puțin un run de predicție valid.';
	if (bankrollId === null) errors.bankrollId = 'Selectează un bankroll activ.';
	if (!Number.isSafeInteger(ticketCount) || ticketCount < 1 || ticketCount > 50) {
		errors.ticketCount = 'Numărul de bilete trebuie să fie între 1 și 50.';
	}
	if (input.markets.length === 0) errors.markets = 'Selectează cel puțin o piață.';
	if (!Number.isFinite(minOdds) || minOdds < 1.01) errors.minOdds = 'Cota minimă trebuie să fie cel puțin 1.01.';
	if (!Number.isFinite(maxOdds) || maxOdds < 1.01) errors.maxOdds = 'Cota maximă trebuie să fie cel puțin 1.01.';
	if (Number.isFinite(minOdds) && Number.isFinite(maxOdds) && minOdds > maxOdds) {
		errors.maxOdds = 'Cota maximă trebuie să fie mai mare sau egală cu cea minimă.';
	}
	return { valid: Object.keys(errors).length === 0, errors };
}

export function generatedBatchLoadState(input: {
	expectedCount: number;
	tickets: Ticket[];
	loading: boolean;
}): { loadedCount: number; expectedCount: number; complete: boolean } {
	const expectedCount = Math.max(0, input.expectedCount);
	const loadedCount = input.tickets.length;
	return {
		loadedCount,
		expectedCount,
		complete:
			!input.loading &&
			expectedCount > 0 &&
			loadedCount === expectedCount &&
			input.tickets.every((ticket) => ticket.status === 'generated')
	};
}
