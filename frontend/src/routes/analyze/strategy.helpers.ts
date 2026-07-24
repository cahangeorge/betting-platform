import type { Dataset, ModelPrediction, Strategy, StrategyBatchRunItem } from '$lib/types';

type StrategyAnalyticsFields = Pick<Strategy, 'last_run' | 'avg_edge' | 'avg_win_rate'>;
type StrategyApiResponse = Omit<Strategy, keyof StrategyAnalyticsFields> & Partial<StrategyAnalyticsFields>;

export function normalizeStrategies(strategies: StrategyApiResponse[]): Strategy[] {
	return strategies.map((strategy) => ({
		...strategy,
		last_run: strategy.last_run ?? null,
		avg_edge: strategy.avg_edge ?? null,
		avg_win_rate: strategy.avg_win_rate ?? null
	}));
}

export function hasStrategyAvgEdge(
	strategy: Pick<Strategy, 'avg_edge'>
): strategy is Pick<Strategy, 'avg_edge'> & { avg_edge: number } {
	return typeof strategy.avg_edge === 'number' && Number.isFinite(strategy.avg_edge);
}

function firstBoolean(...values: unknown[]): boolean | null {
	const explicit = values.find((value) => typeof value === 'boolean');
	return typeof explicit === 'boolean' ? explicit : null;
}

export function isStrategyRunnable(strategy: Strategy): boolean {
	const explicit = firstBoolean(
		strategy.runnable,
		strategy.is_runnable,
		strategy.compatible,
		strategy.is_compatible
	);
	return explicit ?? strategy.is_active;
}

export function strategyUnavailableReason(strategy: Strategy): string {
	const explicit = [
		strategy.runnable_reason,
		strategy.disabled_reason,
		strategy.incompatibility_reason
	].find((value): value is string => typeof value === 'string' && value.trim().length > 0);
	if (explicit?.trim().toLocaleLowerCase('en') === 'strategy is inactive') {
		return 'Strategia este inactivă și trebuie activată din configurare.';
	}
	if (explicit) return explicit;
	if (!strategy.is_active) return 'Strategia este inactivă și trebuie activată din configurare.';
	return 'Strategia nu este compatibilă cu această configurație.';
}

export function strategyCountLabel(count: number): string {
	return `${count} ${count === 1 ? 'strategie' : 'strategii'}`;
}

export function runCountLabel(count: number): string {
	return `${count} ${count === 1 ? 'run' : 'run-uri'}`;
}

export function candidateCountLabel(count: number): string {
	return `${count} ${count === 1 ? 'candidat' : 'candidați'}`;
}

export type DatasetReadiness = {
	dataset: Dataset;
	jobId: number | null;
	jobStatus: string | null;
};

export type AnalysisProgressStatus =
	| 'idle'
	| 'queued'
	| 'running'
	| 'completed'
	| 'partial'
	| 'failed'
	| 'reused'
	| 'no_matches';

export type StrategyProgress = {
	strategyId: number;
	status: AnalysisProgressStatus;
	runId: number | null;
	matchesCount: number;
	error: string | null;
};

function record(value: unknown): Record<string, unknown> | null {
	return typeof value === 'object' && value !== null && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: null;
}

export function datasetJobId(dataset: Dataset): number | null {
	const value = dataset.data.job_id;
	const parsed = typeof value === 'number' ? value : Number.parseInt(String(value ?? ''), 10);
	return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function datasetLooksArgentinian(dataset: Dataset): boolean {
	const data = dataset.data;
	const params = record(data.params);
	const matches = Array.isArray(data.matches) ? data.matches : [];
	const searchable = [
		dataset.name,
		data.league,
		params?.country,
		...(Array.isArray(params?.countries) ? params.countries : []),
		...(Array.isArray(params?.leagues) ? params.leagues : []),
		...matches.flatMap((match) => {
			const item = record(match);
			return item ? [item.country, item.league, item.league_name, item.competition, item.tournament] : [];
		})
	]
		.filter((value): value is string => typeof value === 'string')
		.join(' ')
		.toLocaleLowerCase('ro');

	return searchable.includes('argentina') || searchable.includes('argentin');
}

function newestFirst(a: DatasetReadiness, b: DatasetReadiness): number {
	const byDate = new Date(b.dataset.created_at).getTime() - new Date(a.dataset.created_at).getTime();
	return Number.isFinite(byDate) && byDate !== 0 ? byDate : b.dataset.id - a.dataset.id;
}

export function chooseAnalysisDataset(
	items: DatasetReadiness[],
	requestedDatasetId?: number | null
): DatasetReadiness | null {
	if (requestedDatasetId) {
		const explicit = items.find((item) => item.dataset.id === requestedDatasetId);
		if (explicit) return explicit;
	}

	const ready = items
		.filter(
			(item) =>
				(item.jobStatus === 'completed' || item.jobStatus === 'partial') &&
				(item.dataset.matches_count ?? 0) > 0
		)
		.sort((a, b) => {
			if (a.jobStatus === 'completed' && b.jobStatus !== 'completed') return -1;
			if (b.jobStatus === 'completed' && a.jobStatus !== 'completed') return 1;
			return newestFirst(a, b);
		});
	return ready[0] ?? null;
}

export function datasetCountryLabel(dataset: Dataset): string {
	const data = dataset.data;
	const params = record(data.params);
	const matches = Array.isArray(data.matches) ? data.matches : [];
	const values = [
		data.country,
		params?.country,
		...(Array.isArray(params?.countries) ? params.countries : []),
		...matches.flatMap((match) => {
			const item = record(match);
			return item ? [item.country, item.country_name] : [];
		})
	].filter((value): value is string => typeof value === 'string' && value.trim().length > 0);
	return values[0] ?? 'Țară nespecificată';
}

export function datasetCoverage(dataset: Dataset): {
	leagues: string[];
	dateFrom: string | null;
	dateTo: string | null;
} {
	const matches = Array.isArray(dataset.data.matches) ? dataset.data.matches : [];
	const leagues = new Set<string>();
	const dates: string[] = [];

	for (const rawMatch of matches) {
		const match = record(rawMatch);
		if (!match) continue;
		const league = [match.league, match.league_name, match.competition, match.tournament].find(
			(value): value is string => typeof value === 'string' && value.trim().length > 0
		);
		if (league) leagues.add(league);
		const date = [match.match_date, match.kickoff, match.date, match.start_time].find(
			(value): value is string => typeof value === 'string' && !Number.isNaN(Date.parse(value))
		);
		if (date) dates.push(date);
	}

	const sortedDates = dates.sort((a, b) => Date.parse(a) - Date.parse(b));
	return {
		leagues: Array.from(leagues).sort((a, b) => a.localeCompare(b)),
		dateFrom: sortedDates[0] ?? null,
		dateTo: sortedDates.at(-1) ?? null
	};
}

export function progressFromBatchRun(run: StrategyBatchRunItem): StrategyProgress | null {
	if (!run.strategy_id) return null;
	const status: AnalysisProgressStatus =
		run.deduped || run.status === 'deduped'
			? 'reused'
			: run.status === 'completed' ||
				  run.status === 'partial' ||
				  run.status === 'failed' ||
				  run.status === 'no_matches'
				? run.status
				: 'failed';
	return {
		strategyId: run.strategy_id,
		status,
		runId: run.run_id > 0 ? run.run_id : null,
		matchesCount: run.matches_count ?? 0,
		error: run.error ?? (status === 'failed' ? `Unexpected status: ${run.status}` : null)
	};
}

export function buildTicketsHandoffUrl(
	datasetId: number,
	runIds: number[],
	predictionIds: number[] = []
): string {
	const params = new URLSearchParams({
		dataset_id: String(datasetId),
		run_ids: Array.from(new Set(runIds)).join(',')
	});
	if (predictionIds.length > 0) {
		params.set('prediction_ids', Array.from(new Set(predictionIds)).join(','));
	}
	params.set('source', 'analyze');
	return `/tickets?${params.toString()}`;
}

function predictionFieldOutcome(
	prediction: ModelPrediction,
	selection: string
): { probability: number | null; odds: number | null } {
	const normalized = selection.trim().toLocaleLowerCase('en');
	if (normalized === 'home' || normalized === '1' || normalized === 'yes' || normalized === 'over') {
		return { probability: prediction.home_prob, odds: prediction.home_odds };
	}
	if (normalized === 'draw' || normalized === 'x') {
		return { probability: prediction.draw_prob, odds: prediction.draw_odds };
	}
	if (normalized === 'away' || normalized === '2' || normalized === 'no' || normalized === 'under') {
		return { probability: prediction.away_prob, odds: prediction.away_odds };
	}
	return { probability: null, odds: null };
}

/**
 * Select the model verdict. Market data is only used to attach the persisted odds
 * for that same model selection; it must never replace the model pick/probability.
 */
export function selectModelOutcome(prediction: ModelPrediction): {
	selection: string;
	probability: number;
	odds: number | null;
} {
	const modelReport = prediction.quality_report?.model;
	const modelPick = modelReport?.pick?.trim();
	if (modelPick) {
		const stored = predictionFieldOutcome(prediction, modelPick);
		const reportedProbability = modelReport?.probabilities?.[modelPick];
		const marketOdds = prediction.quality_report?.market?.odds?.[modelPick]?.odds;
		if (typeof reportedProbability === 'number' || typeof stored.probability === 'number') {
			return {
				selection: modelPick,
				probability:
					typeof reportedProbability === 'number' ? reportedProbability : (stored.probability ?? 0),
				odds: typeof marketOdds === 'number' ? marketOdds : stored.odds
			};
		}
	}

	const options = [
		{ selection: 'home', probability: prediction.home_prob, odds: prediction.home_odds },
		{ selection: 'draw', probability: prediction.draw_prob ?? 0, odds: prediction.draw_odds },
		{ selection: 'away', probability: prediction.away_prob, odds: prediction.away_odds }
	];
	return options.reduce((best, candidate) =>
		candidate.probability > best.probability ? candidate : best
	);
}

function positiveIntegerList(value: string | null): number[] {
	if (!value) return [];
	return Array.from(
		new Set(
			value
				.split(',')
				.map((entry) => Number(entry.trim()))
				.filter((entry) => Number.isSafeInteger(entry) && entry > 0)
		)
	);
}

export function parseAnalysisReturnContext(searchParams: URLSearchParams): {
	runIds: number[];
	predictionIds: number[];
} {
	return {
		runIds: positiveIntegerList(searchParams.get('run_ids')),
		predictionIds: positiveIntegerList(
			searchParams.get('prediction_ids') ?? searchParams.get('candidate_ids')
		)
	};
}

export function visibleCandidateWindow<T>(items: T[], limit: number): T[] {
	const safeLimit = Number.isSafeInteger(limit) && limit > 0 ? limit : 25;
	return items.slice(0, safeLimit);
}

export function nextCandidateWindowSize(current: number, total: number, pageSize = 25): number {
	const safeCurrent = Number.isSafeInteger(current) && current > 0 ? current : pageSize;
	const safeTotal = Math.max(0, total);
	return Math.min(safeTotal, safeCurrent + pageSize);
}
