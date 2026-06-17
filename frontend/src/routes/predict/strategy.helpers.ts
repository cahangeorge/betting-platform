import type { Strategy } from '$lib/types';

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
