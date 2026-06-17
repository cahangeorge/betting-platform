export type E2EEnv = {
	frontendURL: string;
	backendURL: string;
	mode: 'hybrid' | 'live';
	liveScrapeTimeoutMs: number;
};

export type TestCredentials = {
	email: string;
	name: string;
	password: string;
};

export type AuthTokenResponse = {
	access_token: string;
	token_type?: string;
};

export type AuthUser = {
	id: number;
	email: string;
	name: string | null;
	is_admin: boolean;
};

export type Bankroll = {
	id: number;
	user_id: number;
	name: string;
	type: string;
	balance: number;
	initial_balance: number;
	currency: string;
};

export type SeededMatch = {
	id: number;
	label: string;
	competition: string;
};

export type AuthSession = {
	namespace: string;
	credentials: TestCredentials;
	user: AuthUser;
	token: AuthTokenResponse;
	bankroll: Bankroll;
	seeded?: {
		competition: string;
		scheduledMatchLabel: string;
		scheduledMatchId: number;
		liveMatchLabel?: string;
		liveMatchId?: number;
	};
};

export type ScrapeJob = {
	id: number;
	job_type: string;
	status: 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
	league: string | null;
	params: Record<string, unknown> | null;
	started_at: string | null;
	completed_at: string | null;
	error: string | null;
	created_at: string;
};

export type SeededHybridFixtures = {
	competition: string;
	scheduledMatchId: number;
	scheduledMatchLabel: string;
	liveMatchId: number;
	liveMatchLabel: string;
	predictionRunId: number;
	seededTicketId: number;
};
