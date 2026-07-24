import { ApiClient, ApiClientError } from './client';

export type RiskStakingMode = 'flat_percent' | 'fractional_kelly';

export type RiskPolicy = {
	id: number;
	bankroll_id: number;
	version: number;
	staking_mode: RiskStakingMode;
	flat_stake_pct: number | null;
	kelly_fraction: number | null;
	max_ticket_pct: number;
	max_open_exposure_pct: number;
	max_match_pct: number | null;
	max_team_pct: number | null;
	max_league_window_pct: number | null;
	league_window_hours: number;
	max_daily_stake_pct: number | null;
	max_weekly_stake_pct: number | null;
	max_daily_ticket_count: number | null;
	max_weekly_ticket_count: number | null;
	accumulators_enabled: boolean;
	automation_enabled: boolean;
	effective_from: string;
	superseded_at?: string | null;
	created_at?: string;
};

export type RiskPolicyInput = {
	staking_mode: RiskStakingMode;
	flat_stake_pct: number | null;
	kelly_fraction: number | null;
	max_ticket_pct: number;
	max_open_exposure_pct: number;
	max_match_pct: number;
	max_team_pct: number;
	max_league_window_pct: number;
	league_window_hours: number;
	max_daily_stake_pct: number;
	max_weekly_stake_pct: number;
	max_daily_ticket_count: number;
	max_weekly_ticket_count: number;
	accumulators_enabled: boolean;
	automation_enabled: boolean;
};

export type RiskUsage = {
	bankroll_balance?: number | null;
	available_balance?: number | null;
	open_exposure_amount?: number | null;
	open_exposure_pct?: number | null;
	staked_last_24h?: number | null;
	staked_last_7d?: number | null;
	ticket_count_last_24h?: number | null;
	ticket_count_last_7d?: number | null;
};

export type RiskPauseState = {
	paused_until: string | null;
	pause_reason: string | null;
	updated_at?: string | null;
};

export type RiskPolicyOverview = {
	policy: RiskPolicy | null;
	pending_policy: RiskPolicy | null;
	state: RiskPauseState | null;
	usage: RiskUsage | null;
};

export type PauseBankrollInput = {
	paused_until: string;
	pause_reason: string;
};

type RiskPolicyApiResponse =
	| RiskPolicy
	| {
			policy?: RiskPolicy | null;
			active_policy?: RiskPolicy | null;
			pending_policy?: RiskPolicy | null;
			state?: RiskPauseState | null;
			pause?: RiskPauseState | null;
			usage?: RiskUsage | null;
	  };

function hasPolicyShape(value: RiskPolicyApiResponse): value is RiskPolicy {
	return 'staking_mode' in value && 'max_ticket_pct' in value;
}

export function normalizeRiskPolicyOverview(
	response: RiskPolicyApiResponse | null
): RiskPolicyOverview | null {
	if (response === null) return null;
	if (hasPolicyShape(response)) {
		return { policy: response, pending_policy: null, state: null, usage: null };
	}

	return {
		policy: response.policy ?? response.active_policy ?? null,
		pending_policy: response.pending_policy ?? null,
		state: response.state ?? response.pause ?? null,
		usage: response.usage ?? null
	};
}

function bankrollPath(bankrollId: number, suffix: string): string {
	if (!Number.isInteger(bankrollId) || bankrollId <= 0) {
		throw new TypeError('bankrollId must be a positive integer');
	}
	return `/api/v1/bankroll/${bankrollId}/${suffix}`;
}

export class RiskApi extends ApiClient {
	async getRiskPolicy(bankrollId: number): Promise<RiskPolicyOverview | null> {
		try {
			const response = await this.get<RiskPolicyApiResponse>(bankrollPath(bankrollId, 'risk-policy'));
			return normalizeRiskPolicyOverview(response);
		} catch (error) {
			if (error instanceof ApiClientError && error.statusCode === 404) return null;
			throw error;
		}
	}

	async saveRiskPolicy(bankrollId: number, input: RiskPolicyInput): Promise<RiskPolicyOverview> {
		const response = await this.put<RiskPolicyApiResponse>(
			bankrollPath(bankrollId, 'risk-policy'),
			input as unknown as Record<string, unknown>
		);
		return normalizeRiskPolicyOverview(response) ?? {
			policy: null,
			pending_policy: null,
			state: null,
			usage: null
		};
	}

	async pauseBankroll(bankrollId: number, input: PauseBankrollInput): Promise<RiskPolicyOverview> {
		const response = await this.post<RiskPolicyApiResponse>(
			bankrollPath(bankrollId, 'pause'),
			input as unknown as Record<string, unknown>
		);
		return normalizeRiskPolicyOverview(response) ?? {
			policy: null,
			pending_policy: null,
			state: null,
			usage: null
		};
	}
}

export const riskApi = new RiskApi();
