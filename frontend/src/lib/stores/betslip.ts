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

export const BETSLIP_DRAFT_STORAGE_KEY = 'bet:betslip-draft:v2';
const LEGACY_BETSLIP_DRAFT_STORAGE_KEY = 'bet:betslip-draft:v1';

function storageKeyForUser(userId: number): string {
	return `${BETSLIP_DRAFT_STORAGE_KEY}:user:${userId}`;
}

function loadDraftForUser(userId: number): BetslipState {
	if (typeof window === 'undefined') return initialState;
	try {
		// The old unscoped draft cannot safely be attributed to the active user.
		sessionStorage.removeItem(LEGACY_BETSLIP_DRAFT_STORAGE_KEY);
		const stored = sessionStorage.getItem(storageKeyForUser(userId));
		if (!stored) return initialState;
		const parsed = JSON.parse(stored) as Partial<BetslipState>;
		if (!Array.isArray(parsed.legs)) return initialState;
		return {
			legs: parsed.legs,
			stake: typeof parsed.stake === 'number' ? parsed.stake : initialState.stake,
			ticketType: normalizeTicketType(
				parsed.legs,
				parsed.ticketType === 'accumulator' || parsed.ticketType === 'system' ? parsed.ticketType : 'single'
			)
		};
	} catch {
		return initialState;
	}
}

function persistDraft(userId: number | null, state: BetslipState): void {
	if (typeof window === 'undefined' || userId === null) return;
	const storageKey = storageKeyForUser(userId);
	if (state.legs.length === 0) {
		sessionStorage.removeItem(storageKey);
		return;
	}
	sessionStorage.setItem(storageKey, JSON.stringify(state));
}

function normalizeTicketType(legs: BetslipLeg[], requested: TicketType): TicketType {
	if (legs.length <= 1) {
		return 'single';
	}
	return requested === 'system' ? 'accumulator' : requested;
}

function normalizeMarketKey(market: string): string {
	const value = market.trim().toLowerCase().replaceAll(/[\s/.-]+/g, '_');
	if (value === '1x2') return '1x2';
	if (
		value === 'ou' ||
		value === 'o_u' ||
		value === 'ou25' ||
		value === 'ou2_5' ||
		value === 'ou_2_5' ||
		value === 'over_under' ||
		value === 'over_under_2_5' ||
		value === 'overunder' ||
		value === 'totals'
	) {
		return 'ou_2_5';
	}
	if (value === 'btts' || value === 'both_score') return 'both_score';
	return value.replaceAll(/\s+/g, '_');
}

function normalizeSelectionKey(selection: string, marketKey: string): string {
	const value = selection.trim().toLowerCase().replaceAll(/[\s/.-]+/g, '_');
	if (value === 'home' || value === '1') return 'home';
	if (value === 'draw' || value === 'x') return 'draw';
	if (value === 'away' || value === '2') return 'away';
	if (value === 'yes') return 'yes';
	if (value === 'no') return 'no';
	if (marketKey === 'ou_2_5') {
		if (value === 'over' || value === 'over_2_5' || value === 'o' || value === 'o_2_5') {
			return 'over';
		}
		if (value === 'under' || value === 'under_2_5' || value === 'u' || value === 'u_2_5') {
			return 'under';
		}
	}
	return value.replaceAll(/\s+/g, '_');
}

export function createBetslipLeg(input: CreateBetslipLegInput): BetslipLeg {
	const marketKey = normalizeMarketKey(input.market);
	const selectionKey = normalizeSelectionKey(input.selection, marketKey);

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
	let ownerUserId: number | null = null;
	const updateAndPersist = (updater: (state: BetslipState) => BetslipState) =>
		update((state) => {
			const nextState = updater(state);
			persistDraft(ownerUserId, nextState);
			return nextState;
		});

	return {
		subscribe,
		setOwner: (userId: number | null) => {
			const nextOwnerUserId = typeof userId === 'number' && Number.isInteger(userId) && userId > 0
				? userId
				: null;
			if (ownerUserId === nextOwnerUserId) return;

			ownerUserId = nextOwnerUserId;
			set(nextOwnerUserId === null ? initialState : loadDraftForUser(nextOwnerUserId));
		},
		reset: () => {
			persistDraft(ownerUserId, initialState);
			set(initialState);
		},
		addLeg: (leg: BetslipLeg) =>
			updateAndPersist((state) => {
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
			updateAndPersist((state) => {
				const nextLegs = state.legs.filter((leg) => leg.id !== id);
				return {
					...state,
					legs: nextLegs,
					ticketType: normalizeTicketType(nextLegs, state.ticketType)
				};
			}),
		clearLegs: () =>
			updateAndPersist((state) => ({
				...state,
				legs: [],
				ticketType: 'single'
			})),
		setStake: (stake: number) =>
			updateAndPersist((state) => ({
				...state,
				stake: Number.isFinite(stake) && stake > 0 ? stake : 0
			})),
		setTicketType: (ticketType: TicketType) =>
			updateAndPersist((state) => ({
				...state,
				ticketType: normalizeTicketType(state.legs, ticketType)
			}))
	};
}

export const betslip = createBetslipStore();

export const betslipCount = derived(betslip, ($betslip) => $betslip.legs.length);
export const betslipHasLegs = derived(betslip, ($betslip) => $betslip.legs.length > 0);
export const betslipHasUnsavedDraft = betslipHasLegs;
export const betslipCombinedOdds = derived(betslip, ($betslip) =>
	$betslip.legs.reduce((acc, leg) => acc * leg.odds, 1)
);
export const betslipPotentialReturn = derived(
	[betslip, betslipCombinedOdds],
	([$betslip, $betslipCombinedOdds]) => $betslip.stake * $betslipCombinedOdds
);
