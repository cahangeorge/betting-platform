// ─── Auth ──────────────────────────────────────────────
export interface User {
	id: number;
	email: string;
	name: string | null;
	is_admin: boolean;
	is_active?: boolean;
	is_superuser?: boolean;
	created_at: string;
	updated_at?: string;
}

export interface LoginRequest {
	email: string;
	password: string;
}

export interface SignupRequest {
	email: string;
	password: string;
	name: string;
}

export interface AuthResponse {
	access_token: string;
	token_type: string;
}

// ─── Matches ───────────────────────────────────────────
export interface Match {
	id: number;
	league: string;
	home_team: string;
	away_team: string;
	start_time: string;
	status: MatchStatus;
	home_score: number | null;
	away_score: number | null;
	odds: Odd[];
	// Live match properties
	minute?: number;
	momentum?: string;
	momentum_intensity?: 'overwhelming' | 'strong' | 'moderate' | 'weak';
	source_ok?: boolean;
	data_age_seconds?: number | null;
	odds_freshness_seconds?: number | null;
	has_live_1x2_odds?: boolean;
	xg_home?: number;
	xg_away?: number;
	possession_home?: number;
	possession_away?: number;
	shots_home?: number;
	shots_away?: number;
	live_value_candidates?: LiveValueCandidate[];
}

export type MatchStatus = 'scheduled' | 'live' | 'finished' | 'postponed' | 'cancelled';

export interface Odd {
	id: number;
	bookmaker: string;
	market: string;
	home_odds: number;
	draw_odds: number | null;
	away_odds: number;
	updated_at: string;
}

export interface LiveValueCandidate {
	market: string;
	selection: string;
	odds: number;
	model_probability: number;
	implied_probability: number;
	edge: number;
	expected_value: number;
	spread: number | null;
	source: string;
	prediction_age_seconds: number | null;
	selection_age_seconds?: number | null;
	odds_freshness_seconds?: number | null;
	data_age_seconds?: number | null;
	source_ok?: boolean;
	model_drift_flag?: boolean;
	is_betslip_eligible?: boolean;
	block_reasons?: string[];
	confidence_band: 'low' | 'medium' | 'high';
}

export interface MatchFilter {
	league?: string;
	status?: MatchStatus;
	date_from?: string;
	date_to?: string;
	page?: number;
	per_page?: number;
}

export interface PaginatedResponse<T> {
	items: T[];
	total: number;
	page: number;
	per_page: number;
}

// ─── Predictions ──────────────────────────────────────
export type ModelType =
	| 'poisson'
	| 'bivariate_poisson'
	| 'skellam'
	| 'elo'
	| 'ensemble'
	| 'xgb'
	| string;

export interface PredictionModel {
	id: string;
	name: string;
	type: ModelType;
	description: string;
	parameters: Record<string, unknown>;
}

export interface PredictionRun {
	id: number;
	user_id?: number | null;
	name?: string | null;
	model_type: string;
	ensemble?: boolean;
	status: RunStatus;
	matches_count: number;
	matches?: number[];
	parameters?: Record<string, unknown>;
	started_at?: string | null;
	created_at: string;
	completed_at: string | null;
	model_predictions?: ModelPrediction[];
	ensemble_predictions?: ModelPrediction[];
	results?: PredictionResult[] | null;
	error: string | null;
	source_dataset_id?: number | null;
	strategy_id?: number | null;
	strategy_name?: string | null;
	input_hash?: string | null;
	input_context?: Record<string, unknown> | null;
}

export type RunStatus = 'pending' | 'running' | 'completed' | 'partial' | 'failed';

export interface PredictionQualityReport {
	schema_version: number;
	training?: {
		total_matches?: number;
		home_team?: { matches?: number; [key: string]: number | undefined };
		away_team?: { matches?: number; [key: string]: number | undefined };
		[key: string]: unknown;
	};
	model?: {
		pick?: string | null;
		probabilities?: Record<string, number>;
	};
	market?: {
		pick?: string | null;
		probabilities?: Record<string, number>;
		odds?: Record<string, { odds: number; bookmaker?: string } | null>;
		implied_source?: string;
	};
	edge?: Record<string, number | null>;
	reliability?: {
		label?: string | null;
		score?: number;
		is_ticket_eligible?: boolean;
		block_reasons?: string[];
	};
}

export interface ModelPrediction {
	id: number;
	run_id: number;
	model_type: string;
	match_id: number;
	market: string;
	home_prob: number;
	draw_prob: number | null;
	away_prob: number;
	home_odds: number | null;
	draw_odds: number | null;
	away_odds: number | null;
	value_home: number | null;
	value_draw: number | null;
	value_away: number | null;
	expected_value: number | null;
	quality_report: PredictionQualityReport | null;
	created_at: string;
}

export interface PredictionResult {
	match_id: number;
	home_team: string;
	away_team: string;
	home_prob: number;
	draw_prob: number;
	away_prob: number;
	home_expected_goals: number;
	away_expected_goals: number;
	predicted_score: string;
	value_bet: string | null;
	confidence: number;
}

export interface PredictionCalibrationBucket {
	lower_bound: number;
	upper_bound: number;
	mean_predicted_probability: number;
	observed_frequency: number;
	calibration_gap: number;
	samples: number;
}

export interface PredictionCalibrationGroup {
	source_run_id?: number;
	model_type: string;
	market: string;
	resolved_predictions: number;
	accuracy: number;
	brier_score: number;
	log_loss: number;
	expected_calibration_error: number;
	buckets: PredictionCalibrationBucket[];
}

export interface PredictionCalibrationReport {
	resolved_predictions: number;
	groups: PredictionCalibrationGroup[];
}

export interface PredictionScoreGridCell {
	home_goals: number;
	away_goals: number;
	probability: number;
}

export interface PredictionScoreGridItem {
	source_run_id?: number;
	match_id: number;
	home_team: string;
	away_team: string;
	kickoff: string | null;
	league: string | null;
	model_type: string;
	prediction_ids: number[];
	source_markets: string[];
	available: boolean;
	unavailable_reason: string | null;
	home_expected_goals: number | null;
	away_expected_goals: number | null;
	max_displayed_goals: number;
	displayed_probability_mass: number | null;
	cells: PredictionScoreGridCell[];
	top_scores: PredictionScoreGridCell[];
	usage: 'analysis_only' | string;
	ticket_generation_eligible: boolean;
}

export interface PredictionScoreGridReport {
	run_id: number;
	source_dataset_id: number | null;
	items: PredictionScoreGridItem[];
	disclaimer: string;
}

export interface RunRequest {
	model_type: ModelType;
	match_ids: number[];
	parameters?: Record<string, unknown>;
}

export interface EnsembleResult {
	models: string[];
	weights: Record<string, number>;
	results: PredictionResult[];
}

export interface ValueBetTrustMetadata {
	is_ticket_eligible?: boolean | null;
	block_reasons?: string[];
	reliability_label?: string | null;
	reliability_score?: number | null;
	source_ok?: boolean | null;
	data_age_seconds?: number | null;
	odds_freshness_seconds?: number | null;
	selection_age_seconds?: number | null;
	model_drift_flag?: boolean | null;
}

export interface ValueBetItem {
	id: number;
	match_id: number;
	league: string | null;
	home_team: string;
	away_team: string;
	kickoff: string | null;
	market: string;
	selection: string;
	model_prob: number;
	odds: number;
	edge: number;
	model_type: string;
	confidence: number;
	reliability?: string | null;
	reliability_score?: number | null;
	quality_reasons?: string[];
	is_ticket_eligible?: boolean | null;
	block_reasons?: string[];
	source_ok?: boolean | null;
	data_age_seconds?: number | null;
	odds_freshness_seconds?: number | null;
	selection_age_seconds?: number | null;
	model_drift_flag?: boolean | null;
	trust?: ValueBetTrustMetadata | null;
	source: string;
}

export interface ValueBetFeed {
	items: ValueBetItem[];
	source: string;
	is_demo: boolean;
	generated_at: string;
}

export interface PredictionVerificationItem {
	prediction_id: number;
	run_id: number;
	match_id: number;
	model_type: string | null;
	league: string | null;
	kickoff: string | null;
	market: string;
	predicted_selection: string | null;
	actual_selection: string | null;
	model_probability: number | null;
	market_odds: number | null;
	status: 'won' | 'lost' | 'pending' | 'void' | 'unsupported';
	home_team: string;
	away_team: string;
	home_score: number | null;
	away_score: number | null;
}

export interface PredictionVerification {
	checked_predictions: number;
	resolved_predictions: number;
	correct_predictions: number;
	incorrect_predictions: number;
	pending_predictions: number;
	void_predictions: number;
	unsupported_predictions: number;
	accuracy: number | null;
	items: PredictionVerificationItem[];
}

// ─── Tickets ──────────────────────────────────────────
export type TicketStatus = 'generated' | 'open' | 'watchlist' | 'won' | 'lost' | 'cashed_out' | 'void';
export type TicketType = 'single' | 'accumulator' | 'system';

export interface TicketGenerationReport {
	prediction_run_id?: number;
	prediction_run_ids?: number[];
	prediction_run_status?: string;
	prediction_run_statuses?: Record<string, string>;
	source_dataset_id?: number | null;
	scanned_predictions?: number;
	requested_prediction_ids?: number[];
	eligible_candidates?: number;
	excluded_predictions?: number;
	excluded_by_reason?: Record<string, number>;
	generated_ticket_lineage?: Array<{
		ticket_id: number;
		prediction_ids: number[];
		prediction_run_ids: number[];
		match_ids: number[];
	}>;
}

export interface TicketBatch {
	id: number;
	bankroll_id: number | null;
	source_prediction_run_id?: number | null;
	source_prediction_run_ids?: number[];
	name: string | null;
	strategy: string | null;
	tickets_count: number;
	total_stake: number;
	revision: number;
	risk_policy_id?: number | null;
	risk_policy_version?: number | null;
	risk_assessment?: TicketRiskAssessment | null;
	staking_snapshot?: Record<string, unknown> | null;
	activation_report?: Record<string, unknown> | null;
	generation_report?: TicketGenerationReport | null;
	created_at: string;
}

export interface TicketLineageLeg extends TicketLeg {
	prediction?: ModelPrediction | null;
	run?: PredictionRun | null;
}

export interface TicketLineageTicket extends Omit<Ticket, 'legs'> {
	legs: TicketLineageLeg[];
}

export interface TicketBatchLineage extends TicketBatch {
	source_runs: PredictionRun[];
	tickets: TicketLineageTicket[];
}

export interface Ticket {
	id: number;
	reference: string;
	batch_id: number | null;
	type?: TicketType;
	ticket_type?: TicketType;
	status: TicketStatus;
	stake: number;
	total_odds: number;
	potential_return: number;
	actual_return: number | null;
	legs: TicketLeg[];
	created_at: string;
	settled_at: string | null;
	bankroll_id: number;
}

export interface TicketLeg {
	id: number;
	model_prediction_id?: number | null;
	prediction_run_id_snapshot?: number | null;
	model_probability_snapshot?: number | null;
	market_probability_snapshot?: number | null;
	market_probability_basis_snapshot?: 'consensus_de_vig' | 'inverse_selected_odds' | string | null;
	expected_value_snapshot?: number | null;
	edge_pct_snapshot?: number | null;
	reliability_label_snapshot?: string | null;
	reliability_score_snapshot?: number | null;
	match_id: number;
	market: string;
	selection: string;
	odds: number;
	status: 'pending' | 'won' | 'lost' | 'void';
	match?: Partial<Match> | null;
}

export interface PlaceBetRequest {
	legs: {
		match_id: number;
		model_prediction_id?: number;
		market: string;
		selection: string;
		odds: number;
	}[];
	stake: number;
	type?: TicketType;
	ticket_type?: TicketType;
	bankroll_id: number;
}

export interface TicketGenerateRequest {
	bankroll_id: number;
	run_id?: number;
	run_ids?: number[];
	prediction_ids?: number[];
	ticket_count: number;
	ticket_format?: 'single' | 'double' | 'treble';
	difficulty?: 'safe' | 'low' | 'balanced' | 'medium' | 'aggressive' | 'high';
	accumulator_risk_acknowledged?: boolean;
	market_types: Array<'1x2' | 'btts' | 'ou_2_5'>;
	min_odds: number;
	max_odds: number;
}

export interface TicketGenerateResponse {
	batch_id: number;
	revision: number;
	source_prediction_run_id?: number | null;
	source_prediction_run_ids: number[];
	risk_policy_version: number | null;
	risk_assessment: TicketRiskAssessment | null;
	staking_snapshot: Record<string, unknown> | null;
	generation_report: TicketGenerationReport;
	tickets: Ticket[];
}

export interface TicketPreflightRequest {
	bankroll_id?: number | null;
	run_id?: number;
	run_ids?: number[];
	prediction_ids?: number[];
	market_types: Array<'1x2' | 'btts' | 'ou_2_5'>;
	min_odds: number;
	max_odds: number;
	ticket_format?: 'single' | 'double' | 'treble';
	accumulator_risk_acknowledged?: boolean;
}

export interface TicketRiskFinding {
	code: string;
	message?: string;
	[key: string]: unknown;
}

export interface TicketRiskAssessment {
	allowed?: boolean;
	blockers?: TicketRiskFinding[];
	warnings?: TicketRiskFinding[];
	[key: string]: unknown;
}

export interface TicketPreflightRisk {
	difficulty: 'safe' | 'low' | 'balanced' | 'medium' | 'aggressive' | 'high';
	tier: 'safe' | 'balanced' | 'aggressive';
	aliases: string[];
	required_legs: number;
	eligible_candidates: number;
	eligible_unique_matches: number;
	can_generate: boolean;
	excluded_by_reason: Record<string, number>;
}

export interface TicketPreflightResponse {
	source_prediction_run_id: number | null;
	source_prediction_run_ids: number[];
	source_dataset_id: number | null;
	scanned_predictions: number;
	eligible_candidates: number;
	eligible_unique_matches: number;
	eligible_prediction_ids: number[];
	excluded_predictions: number;
	excluded_by_reason: Record<string, number>;
	risk_assessment: TicketRiskAssessment | null;
	staking_snapshot: Record<string, unknown> | null;
	risks: TicketPreflightRisk[];
}

export interface TicketBatchActivateResponse {
	batch_id: number;
	status: 'activated' | string;
	debited_amount: number;
	tickets: Ticket[];
}

export interface TicketBatchActivateRequest {
	expected_revision: number;
	review_acknowledged: boolean;
	accepted_warning_codes: string[];
}

export interface TicketBatchRefreshResponse {
	batch_id: number;
	revision: number;
	status: 'refreshed';
	generation_report: TicketGenerationReport;
	risk_assessment: TicketRiskAssessment | null;
	staking_snapshot: Record<string, unknown> | null;
	tickets: Ticket[];
}

export interface TicketSwapLegsRequest {
	source_ticket_id: number;
	source_leg_id: number;
	target_ticket_id: number;
	target_leg_id: number;
}

export interface TicketSwapLegsResponse {
	source_ticket: Ticket;
	target_ticket: Ticket;
}

export interface SettleRequest {
	ticket_id: number;
	outcome: 'won' | 'lost' | 'void';
	return_amount?: number;
}

export interface TicketSettlementRun {
	checked_tickets: number;
	settled_tickets: number;
	won_tickets: number;
	lost_tickets: number;
	void_tickets: number;
	pending_tickets: number;
	updated_legs: number;
}

// ─── Bankroll ─────────────────────────────────────────
export type BankrollType = 'paper' | 'real';
export type LedgerEntryType = 'deposit' | 'withdrawal' | 'bet_placed' | 'bet_won' | 'bet_lost' | 'adjustment';

export interface Bankroll {
	id: number;
	name: string;
	type: BankrollType;
	currency: string;
	balance: number;
	initial_balance: number;
	is_active: boolean;
	created_at: string;
}

export interface BankrollCreateRequest {
	name: string;
	type: BankrollType;
	currency?: string;
	initial_balance: number;
}

export interface BookmakerAccount {
	id: number;
	bookmaker: string;
	account_name: string;
	balance: number;
	bankroll_id: number;
	created_at?: string;
}

export interface BookmakerAccountCreateRequest {
	bookmaker: string;
	account_name: string;
	balance?: number;
	bankroll_id: number;
}

export interface LedgerEntry {
	id: number;
	entry_type: LedgerEntryType;
	description: string;
	amount: number;
	balance_after: number;
	reference_type: string | null;
	reference_id: number | null;
	created_at: string;
	bankroll_id: number;
}

// Isolated paper-local trading domain. These accounts are intentionally
// separate from bookmaker bookkeeping accounts and never carry credentials.
export interface TradingAccount {
	id: number;
	name: string;
	provider: 'paper-local';
	mode: 'paper';
	currency: string;
	balance: number;
	enabled: boolean;
	created_at: string;
	updated_at: string;
}

export interface TradingAccountHealth {
	account_id: number;
	status: 'healthy' | 'disabled';
	mode: 'paper';
	provider: 'paper-local';
	enabled: boolean;
	paper_execution_enabled: boolean;
	live_execution_enabled: false;
	betfair_read_only_status: 'not_configured';
	message: string;
}

export interface TradingExecution {
	id: number;
	trading_account_id: number;
	ticket_id: number;
	odds_entry_id: number;
	idempotency_key: string;
	mode: 'paper';
	market: '1x2';
	selection: 'home' | 'draw' | 'away';
	side: 'BACK';
	order_type: 'LIMIT';
	stake: number;
	limit_price: number;
	status: 'queued' | 'accepted' | 'filled' | 'failed' | 'cancelled';
	error: string | null;
	created_at: string;
	updated_at: string;
	completed_at: string | null;
	orders: Array<{
		id: number;
		provider: 'paper-local';
		external_order_id: null;
		status: string;
		requested_price: number;
		average_price: number | null;
		requested_size: number;
		matched_size: number;
		created_at: string;
	}>;
	events: Array<{
		id: number;
		event_type: string;
		from_status: string | null;
		to_status: string;
		message: string | null;
		payload: Record<string, unknown> | null;
		created_at: string;
	}>;
}

// ─── Data / Scraping ──────────────────────────────────
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type JobType = 'scrape_odds' | 'scrape_results' | 'scrape_league' | 'sync_data';

export interface ScrapeJob {
	id: number;
	job_type: string;
	status: JobStatus;
	league?: string | null;
	params: Record<string, unknown> | null;
	created_at: string;
	started_at?: string | null;
	completed_at: string | null;
	error: string | null;
	output?: string | null;
	queued_run_id?: number | null;
	queued_run?: ScheduledJobRun | null;
}

export interface ScrapeJobCreateRequest {
	job_type: JobType;
	params?: Record<string, unknown>;
}

export interface Dataset {
	id: number;
	name: string | null;
	source: string;
	data: Record<string, unknown>;
	matches_count: number | null;
	created_at: string;
}

export interface League {
	id: string;
	name: string;
	matches_count: number;
	scrape_slug?: string | null;
}

// ─── Scheduled Jobs ───────────────────────────────────
export interface ScheduledJob {
	id: number;
	name: string;
	cron_expression: string;
	task_type: string;
	config: Record<string, unknown> | null;
	enabled: boolean;
	last_run: string | null;
	next_run: string | null;
	created_at: string;
}

export interface ScheduledJobCreateRequest {
	name: string;
	cron_expression: string;
	task_type: string;
	config?: Record<string, unknown>;
}

export type ScheduledJobRunStatus =
	| 'queued'
	| 'pending'
	| 'running'
	| 'completed'
	| 'partial'
	| 'failed'
	| 'enqueue_failed'
	| 'skipped'
	| 'cancelled'
	| string;

export interface ScheduledJobRun {
	id: number;
	job_id: number | null;
	scheduled_job_id: number | null;
	scrape_job_id: number | null;
	task_type: string;
	status: ScheduledJobRunStatus;
	detail: string | null;
	artifacts: Record<string, unknown> | null;
	taskiq_task_id: string | null;
	attempt: number | null;
	queued_at: string | null;
	started_at: string | null;
	finished_at: string | null;
	duration_ms: number | null;
	error: string | null;
	triggered_by: string | null;
	due_at: string | null;
	created_at: string | null;
}

export interface ScheduledJobRunPage {
	runs: ScheduledJobRun[];
	total: number;
	page: number;
	per_page: number;
}

// ─── Strategy Run Results ─────────────────────────────
export interface StrategyCreateRequest {
	name: string;
	model_type: string;
	description?: string;
	parameters?: Record<string, unknown>;
	weights?: Record<string, unknown> | null;
	is_active?: boolean;
}

export interface StrategyRunRequest {
	match_ids: number[];
	markets: string[];
	parameters?: Record<string, unknown>;
}

export interface StrategyRunFilters {
	countries: string[];
	leagues: string[];
	date_from?: string;
	date_to?: string;
}

export interface StrategyBatchRunRequest {
	dataset_id: number;
	strategy_ids?: number[];
	markets: string[];
	filters?: StrategyRunFilters;
	avoid_reprediction: boolean;
	autopredict?: boolean;
	allow_partial_resolution?: boolean;
}

export type StrategyBatchRunStatus =
	| 'completed'
	| 'partial'
	| 'failed'
	| 'no_matches';

export type StrategyBatchItemStatus =
	| 'completed'
	| 'partial'
	| 'failed'
	| 'deduped'
	| 'no_matches';

export interface StrategyBatchRunItem {
	strategy_id: number | null;
	run_id: number;
	status: StrategyBatchItemStatus | string;
	matches_count: number;
	error?: string | null;
	deduped: boolean;
	dataset_id?: number | null;
	input_hash?: string | null;
}

export interface StrategyBatchRunResponse {
	status: StrategyBatchRunStatus | string;
	dataset_id: number;
	scrape_job_id?: number | null;
	scrape_job_status?: string | null;
	match_ids: number[];
	dataset_records_count?: number;
	resolved_records_count?: number;
	unresolved_records_count?: number;
	resolution_counts?: Record<string, number>;
	unresolved_samples?: Record<string, unknown>[];
	strategy_count: number;
	runs: StrategyBatchRunItem[];
}

export interface StrategyRunResult {
	strategy_id: number;
	match_id: number;
	match_home: string;
	match_away: string;
	league: string;
	market: string;
	predicted: string;
	probability: number;
	confidence: number;
	edge: number;
	odds: number;
}

// ─── API Error ─────────────────────────────────────────
export interface ApiError {
	detail:
		| string
		| {
				message?: string;
				resolved_records_count?: number;
				unresolved_records_count?: number;
				[key: string]: unknown;
		  };
	status_code: number;
}

// ─── Polling ──────────────────────────────────────────
export interface PollingState<T> {
	data: T | null;
	loading: boolean;
	error: string | null;
}

// ─── Dashboard ────────────────────────────────────────
export interface DashboardSummary {
	total_matches: number;
	total_tickets: number;
	win_rate: number;
	total_pnl: number;
	active_bankroll: number;
	pending_bets: number;
}

export interface JobLog {
	id: number;
	job_type: string;
	status: string;
	league: string | null;
	started_at: string | null;
	completed_at: string | null;
	error: string | null;
	created_at: string;
}

export interface ScrapeJobLogEntry {
	id: number;
	job_id: number;
	level: string;
	action: string;
	message: string;
	metadata_json: Record<string, unknown> | null;
	created_at: string;
}

export interface ScrapeJobLogPage {
	items: ScrapeJobLogEntry[];
	total: number;
	page: number;
	per_page: number;
}

// ─── Analytics ────────────────────────────────────────
export interface PnlPoint {
	date: string;
	pnl: number;
	cumulative_pnl: number;
	bets_count: number;
	wins: number;
}

// ─── Catalog ──────────────────────────────────────────
export interface Country {
	country: string;
	leagues: LeagueInfo[];
	/** Optional metadata returned by the dynamic OddsPortal catalog. */
	source?: string | null;
	status?: string | null;
	last_refreshed_at?: string | null;
}

export interface LeagueInfo {
	id: string;
	name: string;
	matches_count: number;
	scrape_slug?: string | null;
	/** `validated`, `validation_pending`, `validation_passed`, or `unavailable` when the catalog provides it. */
	status?: string | null;
	source?: string | null;
	source_url?: string | null;
	last_refreshed_at?: string | null;
	last_seen_at?: string | null;
	scrape_capability?: 'full' | 'upcoming';
}

/**
 * The catalog endpoint remains backwards compatible with its original array
 * response. Dynamic catalog deployments may instead return this envelope.
 */
export interface CatalogResponse {
	countries: Country[];
	source?: string | null;
	status?: string | null;
	last_refreshed_at?: string | null;
}

export interface FootballCatalogWorkflowAttempt {
	attempt: number;
	discovered: number;
	created: number;
	updated: number;
	checked: number;
	available: number;
	unavailable: number;
	pending: number;
}

export interface FootballCatalogDiscoveryValidationResponse {
	countries: string[];
	attempts_used: number;
	discovered: number;
	available: number;
	unavailable: number;
	pending: number;
	stop_reason: 'all_validated' | 'attempt_limit' | 'no_candidates';
	attempts: FootballCatalogWorkflowAttempt[];
}

// ─── Strategies ───────────────────────────────────────
export interface Strategy {
	id: number;
	name: string;
	model_type: string;
	description: string | null;
	parameters: Record<string, unknown>;
	weights: Record<string, unknown> | null;
	is_active: boolean;
	created_at: string;
	updated_at: string;
	last_run: string | null;
	avg_edge: number | null;
	avg_win_rate: number | null;
	/** Optional catalog metadata. Older backends omit these fields; active strategies remain the safe fallback. */
	runnable?: boolean | null;
	is_runnable?: boolean | null;
	compatible?: boolean | null;
	is_compatible?: boolean | null;
	runnable_reason?: string | null;
	disabled_reason?: string | null;
	incompatibility_reason?: string | null;
}

// ─── Extended Dashboard Types ─────────────────────────
export interface DashboardTicket {
	id: number;
	reference: string | null;
	ticket_type: string;
	status: TicketStatus;
	stake: number;
	total_odds: number;
	potential_return: number;
	actual_return: number | null;
	legs: {
		match_id: number;
		home_team: string;
		away_team: string;
		market: string;
		selection: string;
		odds: number;
		status: string;
		home_score: number | null;
		away_score: number | null;
	}[];
	created_at: string;
}

export interface DashboardTicketOutcomeBucket {
	bucket_start: string;
	bucket_end: string;
	won: number;
	lost: number;
	void: number;
	pending: number;
	ticket_ids: number[];
}

export interface DashboardTicketOutcomeResponse {
	range: string;
	bucket: string;
	items: DashboardTicketOutcomeBucket[];
}

export interface UpcomingMatch {
	id: number;
	league: string;
	home_team: string;
	away_team: string;
	start_time: string;
	home_odds: number | null;
	draw_odds: number | null;
	away_odds: number | null;
}
