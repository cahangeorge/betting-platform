import { ApiClient } from './client';
import type {
	PredictionRun,
	RunRequest,
	PredictionModel,
	EnsembleResult,
	BacktestRequest,
	BacktestResult,
	PaginatedResponse,
	PredictionVerification,
	ValueBetFeed,
	ValueBetItem,
	ValueBetTrustMetadata
} from '$lib/types';

type ValueBetReliabilityObject = {
	label?: string | null;
	score?: number | null;
	is_ticket_eligible?: boolean | null;
	block_reasons?: string[] | null;
};

type RawValueBetItem = Omit<ValueBetItem, 'reliability' | 'trust'> & {
	reliability?: string | ValueBetReliabilityObject | null;
	trust?: ValueBetTrustMetadata | null;
};

type RawValueBetFeed = Omit<ValueBetFeed, 'items'> & {
	items: RawValueBetItem[];
};

function isReliabilityObject(value: unknown): value is ValueBetReliabilityObject {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function uniqueStrings(values: unknown[]): string[] {
	return Array.from(
		new Set(
			values.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
		)
	);
}

function normalizeValueBetItem(item: RawValueBetItem): ValueBetItem {
	const reliabilityObject = isReliabilityObject(item.reliability) ? item.reliability : null;
	const trust = item.trust ?? null;
	const qualityReasons = uniqueStrings(item.quality_reasons ?? []);
	const blockReasons = uniqueStrings([
		...(item.block_reasons ?? []),
		...(trust?.block_reasons ?? []),
		...(reliabilityObject?.block_reasons ?? []),
		...qualityReasons
	]);
	const reliability =
		typeof item.reliability === 'string'
			? item.reliability
			: reliabilityObject?.label ?? trust?.reliability_label ?? null;
	const isTicketEligible =
		item.is_ticket_eligible ??
		trust?.is_ticket_eligible ??
		reliabilityObject?.is_ticket_eligible ??
		null;
	const reliabilityScore =
		item.reliability_score ?? trust?.reliability_score ?? reliabilityObject?.score ?? null;

	return {
		...item,
		reliability,
		reliability_score: reliabilityScore,
		quality_reasons: qualityReasons,
		is_ticket_eligible: isTicketEligible,
		block_reasons: blockReasons,
		source_ok: item.source_ok ?? trust?.source_ok ?? null,
		data_age_seconds: item.data_age_seconds ?? trust?.data_age_seconds ?? null,
		odds_freshness_seconds: item.odds_freshness_seconds ?? trust?.odds_freshness_seconds ?? null,
		selection_age_seconds: item.selection_age_seconds ?? trust?.selection_age_seconds ?? null,
		model_drift_flag: item.model_drift_flag ?? trust?.model_drift_flag ?? null,
		trust: trust
			? {
					...trust,
					is_ticket_eligible: isTicketEligible,
					block_reasons: blockReasons,
					reliability_label: trust.reliability_label ?? reliability,
					reliability_score: reliabilityScore
				}
			: null
	};
}

export function normalizeValueBetFeed(response: RawValueBetFeed | RawValueBetItem[]): ValueBetFeed {
	if (Array.isArray(response)) {
		return {
			items: response.map(normalizeValueBetItem),
			source: 'prediction',
			is_demo: false,
			generated_at: new Date().toISOString()
		};
	}

	return {
		...response,
		items: (response.items ?? []).map(normalizeValueBetItem)
	};
}

class PredictionsApi extends ApiClient {
	async getModels(): Promise<PredictionModel[]> {
		return this.get<PredictionModel[]>('/api/v1/predictions/catalog');
	}

	async getRuns(): Promise<PredictionRun[]> {
		return this.get<PredictionRun[]>('/api/v1/predictions/runs');
	}

	async getRunsPage(params?: { page?: number; per_page?: number }): Promise<PaginatedResponse<PredictionRun>> {
		const sp = new URLSearchParams();
		if (params?.page !== undefined) sp.set('page', String(params.page));
		if (params?.per_page !== undefined) sp.set('per_page', String(params.per_page));
		const qs = sp.toString();
		return this.get<PaginatedResponse<PredictionRun>>(`/api/v1/predictions/runs/page${qs ? `?${qs}` : ''}`);
	}

	async getRun(id: number): Promise<PredictionRun> {
		return this.get<PredictionRun>(`/api/v1/predictions/runs/${id}`);
	}

	async createRun(data: RunRequest): Promise<PredictionRun> {
		return this.post<PredictionRun>('/api/v1/predictions/run', data as unknown as Record<string, unknown>);
	}

	async getEnsemble(runId: number): Promise<EnsembleResult> {
		return this.post<EnsembleResult>(`/api/v1/predictions/ensemble`, { run_id: runId } as unknown as Record<string, unknown>);
	}

	async runBacktest(data: BacktestRequest): Promise<BacktestResult> {
		// Backend doesn't have a dedicated backtest endpoint yet — return empty
		return {
			model_type: data.model_type,
			total_matches: 0,
			accuracy: 0,
			profit_loss: 0,
			roi: 0,
			results: []
		};
	}

	async verify(runId?: number): Promise<PredictionVerification> {
		const params = runId ? `?run_id=${runId}` : '';
		return this.get<PredictionVerification>(`/api/v1/predictions/verification${params}`);
	}

	async getValueBets(fetchFn?: typeof fetch): Promise<ValueBetFeed> {
		const response = await this.get<RawValueBetFeed | RawValueBetItem[]>(
			'/api/v1/predictions/value-bets',
			undefined,
			fetchFn
		);
		return normalizeValueBetFeed(response);
	}
}

export const predictionsApi = new PredictionsApi();
