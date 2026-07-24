import { ApiClient } from './client';
import type {
	PredictionRun,
	RunRequest,
	PredictionModel,
	EnsembleResult,
	PaginatedResponse,
	PredictionVerification,
	ValueBetFeed,
	StrategyBatchRunRequest,
	StrategyBatchRunResponse,
	PredictionCalibrationReport,
	PredictionScoreGridReport
} from '$lib/types';
import {
	normalizeValueBetFeed,
	type RawValueBetFeed,
	type RawValueBetItem
} from './value-bet-normalization';

export { normalizeValueBetFeed } from './value-bet-normalization';

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

	async runStrategyBatch(data: StrategyBatchRunRequest): Promise<StrategyBatchRunResponse> {
		return this.post<StrategyBatchRunResponse>(
			'/api/v1/strategies/run-batch',
			data as unknown as Record<string, unknown>
		);
	}

	async getEnsemble(runId: number): Promise<EnsembleResult> {
		return this.post<EnsembleResult>(`/api/v1/predictions/ensemble`, { run_id: runId } as unknown as Record<string, unknown>);
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

	async getCalibration(runId?: number): Promise<PredictionCalibrationReport> {
		const params = new URLSearchParams();
		if (runId !== undefined) params.set('run_id', String(runId));
		const query = params.toString();
		return this.get<PredictionCalibrationReport>(
			`/api/v1/predictions/calibration${query ? `?${query}` : ''}`
		);
	}

	async getScoreGrids(runId: number): Promise<PredictionScoreGridReport> {
		return this.get<PredictionScoreGridReport>(
			`/api/v1/predictions/runs/${runId}/score-grids`
		);
	}
}

export const predictionsApi = new PredictionsApi();
