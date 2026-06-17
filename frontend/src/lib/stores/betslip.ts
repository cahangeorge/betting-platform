import { derived, writable } from 'svelte/store';
import type { TicketType } from '$lib/types';

export interface BetslipLeg {
	id: string;
	matchId: number;
	modelPredictionId?: number;
	matchName: string;
	market: string;
	marketKey: string;
	selection: string;
	selectionKey: string;
	odds: number;
	league?: string;
	kickoff?: string;
	source?: 'dashboard' | 'prediction' | 'value-bet' | 'live';
}

interface BetslipState {
	legs: BetslipLeg[];
	stake: number;
	ticketType: TicketType;
}

interface CreateBetslipLegInput {
	matchId: number;
	modelPredictionId?: number;
	matchName: string;
	market: string;
	selection: string;
	odds: number;
	league?: string;
	kickoff?: string;
	source?: BetslipLeg['source'];
}

const initialState: BetslipState = {
	legs: [],
	stake: 10,
	ticketType: 'single'
};

function normalizeTicketType(legs: BetslipLeg[], requested: TicketType): TicketType {
	if (legs.length <= 1) {
		return 'single';
	}
	return requested === 'system' ? 'accumulator' : requested;
}

function normalizeMarketKey(market: string): string {
	const value = market.trim().toLowerCase();
	if (value === '1x2') return '1x2';
	if (value === 'ou' || value === 'o/u' || value === 'over_under_2.5') return 'over_under';
	if (value === 'btts' || value === 'both_score') return 'both_score';
	return value.replaceAll(/\s+/g, '_');
}

function normalizeSelectionKey(selection: string): string {
	const value = selection.trim().toLowerCase();
	if (value === 'home' || value === '1') return 'home';
	if (value === 'draw' || value === 'x') return 'draw';
	if (value === 'away' || value === '2') return 'away';
	if (value === 'yes') return 'yes';
	if (value === 'no') return 'no';
	return value.replaceAll(/\s+/g, '_');
}

export function createBetslipLeg(input: CreateBetslipLegInput): BetslipLeg {
	const marketKey = normalizeMarketKey(input.market);
	const selectionKey = normalizeSelectionKey(input.selection);

	return {
		id: `${input.matchId}-${marketKey}-${selectionKey}`,
		matchId: input.matchId,
		modelPredictionId: input.modelPredictionId,
		matchName: input.matchName,
		market: input.market,
		marketKey,
		selection: input.selection,
		selectionKey,
		odds: input.odds,
		league: input.league,
		kickoff: input.kickoff,
		source: input.source
	};
}

function createBetslipStore() {
	const { subscribe, update, set } = writable<BetslipState>(initialState);

	return {
		subscribe,
		reset: () => set(initialState),
		addLeg: (leg: BetslipLeg) =>
			update((state) => {
				const exists = state.legs.some(
					(item) =>
						item.matchId === leg.matchId &&
						item.marketKey === leg.marketKey &&
						item.selectionKey === leg.selectionKey
				);
				if (exists) {
					return state;
				}

				const nextLegs = [...state.legs, leg];
				return {
					...state,
					legs: nextLegs,
					ticketType: normalizeTicketType(nextLegs, state.ticketType)
				};
			}),
		removeLeg: (id: string) =>
			update((state) => {
				const nextLegs = state.legs.filter((leg) => leg.id !== id);
				return {
					...state,
					legs: nextLegs,
					ticketType: normalizeTicketType(nextLegs, state.ticketType)
				};
			}),
		clearLegs: () =>
			update((state) => ({
				...state,
				legs: [],
				ticketType: 'single'
			})),
		setStake: (stake: number) =>
			update((state) => ({
				...state,
				stake: Number.isFinite(stake) && stake > 0 ? stake : 0
			})),
		setTicketType: (ticketType: TicketType) =>
			update((state) => ({
				...state,
				ticketType: normalizeTicketType(state.legs, ticketType)
			}))
	};
}

export const betslip = createBetslipStore();

export const betslipCount = derived(betslip, ($betslip) => $betslip.legs.length);
export const betslipHasLegs = derived(betslip, ($betslip) => $betslip.legs.length > 0);
export const betslipCombinedOdds = derived(betslip, ($betslip) =>
	$betslip.legs.reduce((acc, leg) => acc * leg.odds, 1)
);
export const betslipPotentialReturn = derived(
	[betslip, betslipCombinedOdds],
	([$betslip, $betslipCombinedOdds]) => $betslip.stake * $betslipCombinedOdds
);
