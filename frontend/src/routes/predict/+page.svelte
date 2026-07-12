<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { fade, slide } from 'svelte/transition';
	import { betslip, createBetslipLeg } from '$lib/stores/betslip';
	import BetslipReviewCallout from '$lib/components/BetslipReviewCallout.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import Skeleton from '$lib/components/ui/skeleton/skeleton.svelte';
	import Separator from '$lib/components/ui/separator/separator.svelte';
	import DialogRoot from '$lib/components/ui/dialog/dialog-root.svelte';
	import DialogContent from '$lib/components/ui/dialog/dialog-content.svelte';
	import DialogHeader from '$lib/components/ui/dialog/dialog-header.svelte';
	import DialogTitle from '$lib/components/ui/dialog/dialog-title.svelte';
	import DialogFooter from '$lib/components/ui/dialog/dialog-footer.svelte';
	import ScheduledJobRunTable from '$lib/components/jobs/ScheduledJobRunTable.svelte';
	import { jobsApi } from '$lib/api/jobs';
	import { predictionsApi } from '$lib/api/predictions';
	import { ApiClientError } from '$lib/api/client';
	import { apiBaseUrl } from '$lib/api/base';
	import { cronFromInterval, describeScheduledJob, scheduledJobsForArea } from '$lib/scheduled-jobs.helpers';
	import { hasStrategyAvgEdge, normalizeStrategies } from './strategy.helpers';
	import { cn } from '$lib/utils';
	import type {
		Country,
		Match,
		ModelPrediction,
		PredictionVerification,
		PredictionRun,
		ScheduledJob,
		Strategy,
		StrategyCreateRequest,
		StrategyRunResult
	} from '$lib/types';

	// Use same-origin /api requests so the frontend auth cookie is sent through the proxy.
	const BASE_URL = apiBaseUrl();

	// --- Catalog State ---
	let countries = $state<Country[]>([]);
	let allLeagues = $state<{ id: string; name: string; matches_count: number; country: string }[]>([]);
	let selectedCountries = $state<string[]>([]);
	let selectedLeagues = $state<string[]>([]);
	let dateFrom = $state('');
	let dateTo = $state('');
	let loadingCatalog = $state(true);

	// --- Strategy State ---
	let strategies = $state<Strategy[]>([]);
	let selectedStrategyIds = $state<number[]>([]);
	let loadingStrategies = $state(true);
	let strategyLoadError = $state('');

	// --- Strategy Dialog ---
	let dialogOpen = $state(false);
	let newStrategyName = $state('');
	let newStrategyModelType = $state('poisson');
	let newStrategyDescription = $state('');
	let newStrategyParams = $state('');
	let creatingStrategy = $state(false);
	let createError = $state('');

		// --- Market State ---
	type MarketOption = { id: string; label: string };
	let marketOptions = $state<MarketOption[]>([
		{ id: '1x2', label: '1X2' },
		{ id: 'over_under_2.5', label: 'Over/Under 2.5' },
		{ id: 'btts', label: 'BTTS' }
	]);
	let selectedMarkets = $state<string[]>(['1x2']);
	let loadingPredictionCatalog = $state(true);
	let predictionCatalogError = $state('');

	// --- Run State ---
	let running = $state(false);
	let runProgress = $state(0);
	let runError = $state('');
	let runSuccess = $state('');
	let runWarning = $state('');
	let autoPredict = $state(false);
	let autoInterval = $state('24');
	let autoIntervalUnit = $state('Hours');
	let avoidReprediction = $state(true);
	let predictionFutureDays = $state('7');
	let predictionFutureWeeks = $state('0');
	let predictionFutureMonths = $state('0');
	let predictionFutureYears = $state('0');
	let pollTimer: ReturnType<typeof setInterval> | null = null;
	let scheduledJobs = $state<ScheduledJob[]>([]);
	let loadingScheduledJobs = $state(true);
	let scheduledJobsError = $state('');
	let savingScheduledJob = $state(false);

	// --- Results State ---
	let results = $state<StrategyRunResult[]>([]);
	let recentRuns = $state<PredictionRun[]>([]);
	let verification = $state<PredictionVerification | null>(null);
	let verificationError = $state('');
	let modelPredictionRows = $state<
		{
			runId: number;
			predictionId: number;
			model: string;
			matchId: number;
			match: string;
			league: string;
			market: string;
			selection: string;
			probability: number;
			homeProb: number;
			drawProb: number | null;
			awayProb: number;
			bestOdds: number | null;
			bookmaker: string | null;
			edge: number | null;
			reliability: string;
			ticketEligible: boolean | null;
			qualityReasons: string[];
			marketPick: string | null;
			marketProbability: number | null;
		}[]
	>([]);
	let activeResultTab = $state('all');
	let resultPollTimer: ReturnType<typeof setInterval> | null = null;

	// --- Derived ---
	const scopedMatchId = $derived.by(() => {
		const raw = $page.url.searchParams.get('match');
		if (!raw) return null;
		const parsed = Number.parseInt(raw, 10);
		return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
	});

	const filteredLeagues = $derived(
		selectedCountries.length === 0
			? allLeagues
			: allLeagues.filter((l) => selectedCountries.includes(l.country))
	);

	const selectedCountryBadges = $derived(
		selectedCountries.map((c) => ({ value: c, label: c }))
	);

	const selectedLeagueBadges = $derived(
		selectedLeagues.map((id) => {
			const league = allLeagues.find((l) => l.id === id);
			return { value: id, label: league?.name ?? id };
		})
	);

	const selectedStrategies = $derived(
		strategies.filter((s) => selectedStrategyIds.includes(s.id))
	);

	const resultTabs = $derived([
		{ id: 'all', label: 'All Strategies', count: results.length },
		...selectedStrategies.map((s) => ({
			id: String(s.id),
			label: s.name,
			count: results.filter((r) => r.strategy_id === s.id).length
		}))
	]);

	const filteredResults = $derived.by(() => {
		if (activeResultTab === 'all') return results;
		const id = parseInt(activeResultTab, 10);
		return results.filter((r) => r.strategy_id === id);
	});

	const sortedResults = $derived.by(() => {
		return [...filteredResults].sort((a, b) => b.edge - a.edge);
	});

	const sortedModelPredictionRows = $derived.by(() => {
		return [...modelPredictionRows].sort((a, b) => {
			const aScore = a.edge ?? a.probability;
			const bScore = b.edge ?? b.probability;
			return bScore - aScore;
		});
	});

	const predictionFutureTotalDays = $derived(
		intervalToDays(predictionFutureDays, predictionFutureWeeks, predictionFutureMonths, predictionFutureYears)
	);

	const completedRunCount = $derived(recentRuns.filter((run) => run.status === 'completed').length);
	const activeRunCount = $derived(recentRuns.filter((run) => run.status === 'running' || run.status === 'pending').length);
	const selectedFilterCount = $derived(
		selectedCountries.length + selectedLeagues.length + selectedMarkets.length + selectedStrategyIds.length
	);
	const automaticPredictionJobs = $derived(scheduledJobsForArea(scheduledJobs, 'prediction'));
	const predictionWinRate = $derived(
		verification?.resolved_predictions
			? (verification.correct_predictions / verification.resolved_predictions) * 100
			: null
	);

	const predictionControlNotes = $derived.by(() => {
		const notes: string[] = [];
		if (avoidReprediction) {
			notes.push('Avoid reprediction is active: identical successful strategy inputs reuse the existing run.');
		}
		if (autoPredict) {
			notes.push('Autopredict can be saved as a persistent /api/v1/jobs action with the Save autopredict button.');
		}
		return notes;
	});

	const unitOptions = [
		{ value: 'Hours', label: 'Hours' },
		{ value: 'Days', label: 'Days' },
		{ value: 'Weeks', label: 'Weeks' }
	];

	const modelTypeOptions = [
		{ value: 'poisson', label: 'Poisson' },
		{ value: 'bivariate_poisson', label: 'Bivariate Poisson' },
		{ value: 'dixon_coles', label: 'Dixon-Coles' },
		{ value: 'negbin', label: 'Negative Binomial' },
		{ value: 'zip', label: 'Zero-Inflated Poisson' },
		{ value: 'weibull', label: 'Weibull Copula' }
	];

	const modelTypeBadgeVariant: Record<string, 'success' | 'info' | 'warning' | 'premium'> = {
		poisson: 'success',
		bivariate_poisson: 'success',
		dixon_coles: 'info',
		negbin: 'success',
		zip: 'success',
		weibull: 'success'
	};

	function positiveInteger(value: string): number {
		const parsed = Number.parseInt(value, 10);
		return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
	}

	function intervalToDays(days: string, weeks: string, months: string, years: string): number {
		return (
			positiveInteger(days) +
			positiveInteger(weeks) * 7 +
			positiveInteger(months) * 30 +
			positiveInteger(years) * 365
		);
	}

	function localDateString(date: Date): string {
		const year = date.getFullYear();
		const month = String(date.getMonth() + 1).padStart(2, '0');
		const day = String(date.getDate()).padStart(2, '0');
		return `${year}-${month}-${day}`;
	}

	function marketLabel(market: string): string {
		const labels: Record<string, string> = {
			'1x2': '1X2',
			btts: 'BTTS',
			ou_2_5: 'Over/Under 2.5',
			'over_under_2.5': 'Over/Under 2.5'
		};
		return labels[market] ?? market;
	}

	function applyFuturePredictionInterval() {
		if (predictionFutureTotalDays <= 0) return;
		const start = new Date();
		const end = new Date();
		end.setDate(end.getDate() + predictionFutureTotalDays);
		dateFrom = localDateString(start);
		dateTo = localDateString(end);
	}

	// --- Data Fetching ---
	async function fetchCatalog() {
		try {
			const res = await fetch(`${BASE_URL}/api/v1/catalog/countries`, { credentials: 'include' });
			if (res.ok) {
				countries = await res.json();
				allLeagues = countries.flatMap((c) =>
					c.leagues.map((l) => ({ ...l, country: c.country }))
				);
			}
		} catch {
			// silently handle
		} finally {
			loadingCatalog = false;
		}
	}

	async function fetchPredictionCatalog() {
		predictionCatalogError = '';
		try {
			const res = await fetch(`${BASE_URL}/api/v1/predictions/catalog`, { credentials: 'include' });
			if (!res.ok) {
				const err = await res.json().catch(() => ({ detail: 'Failed to load prediction catalog' }));
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			const data = (await res.json()) as { markets?: string[] };
			if (Array.isArray(data.markets) && data.markets.length > 0) {
				const availableMarkets = data.markets;
				marketOptions = availableMarkets.map((market) => ({ id: market, label: marketLabel(market) }));
				selectedMarkets = selectedMarkets.filter((market) => availableMarkets.includes(market));
				if (selectedMarkets.length === 0) selectedMarkets = [availableMarkets[0]];
			}
		} catch (err) {
			predictionCatalogError = err instanceof Error ? err.message : 'Failed to load prediction catalog';
		} finally {
			loadingPredictionCatalog = false;
		}
	}

	async function fetchStrategies() {
		strategyLoadError = '';
		try {
			const res = await fetch(`${BASE_URL}/api/v1/strategies`, { credentials: 'include' });
			if (!res.ok) {
				const err = await res.json().catch(() => ({ detail: 'Failed to load strategies' }));
				throw new Error(err.detail || `HTTP ${res.status}`);
			}

			strategies = normalizeStrategies(await res.json());
		} catch (err) {
			strategies = [];
			strategyLoadError = err instanceof Error ? err.message : 'Failed to load strategies';
		} finally {
			loadingStrategies = false;
		}
	}

	async function fetchScheduledJobs() {
		loadingScheduledJobs = true;
		scheduledJobsError = '';
		try {
			scheduledJobs = await jobsApi.getScheduledJobs();
		} catch (err) {
			scheduledJobsError = err instanceof ApiClientError ? err.message : 'Scheduled prediction jobs are unavailable';
		} finally {
			loadingScheduledJobs = false;
		}
	}

	async function fetchVerification() {
		verificationError = '';
		try {
			verification = await predictionsApi.verify();
		} catch (err) {
			verificationError = err instanceof ApiClientError ? err.message : 'Prediction verification metrics are unavailable';
		}
	}

	async function toggleScheduledJob(jobId: number) {
		scheduledJobsError = '';
		try {
			const updated = await jobsApi.toggleJob(jobId);
			scheduledJobs = scheduledJobs.map((job) => (job.id === jobId ? updated : job));
		} catch (err) {
			scheduledJobsError = err instanceof ApiClientError ? err.message : 'Could not toggle scheduled prediction job';
		}
	}

	async function saveAutomaticPredictionAction() {
		if (selectedStrategyIds.length === 0 || selectedMarkets.length === 0) {
			scheduledJobsError = 'Select at least one strategy and one market before saving autopredict';
			return;
		}

		savingScheduledJob = true;
		scheduledJobsError = '';
		try {
			const created = await jobsApi.createScheduledJob({
				name: `Autopredict ${selectedStrategyIds.length} strateg${selectedStrategyIds.length === 1 ? 'y' : 'ies'}`,
				task_type: 'run_predictions',
				cron_expression: cronFromInterval(autoInterval, autoIntervalUnit),
				config: {
					source_page: 'predict',
					area: 'prediction',
					strategy_ids: selectedStrategyIds,
					markets: selectedMarkets,
					filters: {
						countries: selectedCountries,
						leagues: selectedLeagues,
						date_from: dateFrom || undefined,
						date_to: dateTo || undefined
					},
					avoid_reprediction: avoidReprediction
				}
			});
			scheduledJobs = [created, ...scheduledJobs.filter((job) => job.id !== created.id)];
		} catch (err) {
			scheduledJobsError = err instanceof ApiClientError ? err.message : 'Could not save automatic prediction action';
		} finally {
			savingScheduledJob = false;
		}
	}

	type ValueBetApiItem = {
		id: number;
		match_id: number;
		league: string | null;
		home_team: string;
		away_team: string;
		market: string;
		selection: string;
		model_prob: number;
		odds: number;
		edge: number;
		confidence: number;
	};

	function predictionSelection(prediction: ModelPrediction): { selection: string; probability: number } {
		const options = [
			{ selection: 'home', probability: prediction.home_prob },
			{ selection: 'draw', probability: prediction.draw_prob ?? 0 },
			{ selection: 'away', probability: prediction.away_prob }
		];

		return options.reduce((best, candidate) =>
			candidate.probability > best.probability ? candidate : best
		);
	}

	function bestOddsForSelection(
		match: Match | undefined,
		market: string,
		selection: string
	): { odds: number | null; bookmaker: string | null } {
		if (!match) return { odds: null, bookmaker: null };
		const marketKey = market.toLowerCase();
		const candidates = match.odds.filter((odd) => {
			const oddMarket = odd.market.toLowerCase();
			const oddBase = oddMarket.split(':', 1)[0];
			if (marketKey === '1x2') return oddBase === '1x2' || oddBase === 'match_winner';
			if (marketKey === 'btts') return oddBase === 'btts' || oddBase === 'both_teams_to_score';
			if (marketKey === 'ou_2_5' || marketKey === 'over_under_2.5') {
				return ['ou_2_5', 'over_under_2_5', 'over_under'].includes(oddBase);
			}
			return oddMarket === marketKey;
		});

		let best: { odds: number; bookmaker: string } | null = null;
		for (const odd of candidates) {
			const odds =
				selection === 'home'
					? odd.home_odds
					: selection === 'draw'
						? odd.draw_odds
						: odd.away_odds;
			if (!odds || odds <= 0) continue;
			if (!best || odds > best.odds) {
				best = { odds, bookmaker: odd.bookmaker };
			}
		}

		return best ?? { odds: null, bookmaker: null };
	}

	function reliabilityVariant(label: string): 'success' | 'warning' | 'danger' | 'neutral' {
		if (label === 'reliable') return 'success';
		if (label === 'moderate') return 'warning';
		if (label === 'unreliable') return 'danger';
		return 'neutral';
	}

	async function loadMatchMap(matchIds: number[]): Promise<Map<number, Match>> {
		const uniqueIds = Array.from(new Set(matchIds));
		const entries = await Promise.all(
			uniqueIds.map(async (id) => {
				try {
					const res = await fetch(`${BASE_URL}/api/v1/matches/${id}`, { credentials: 'include' });
					if (!res.ok) return null;
					return [id, (await res.json()) as Match] as const;
				} catch {
					return null;
				}
			})
		);

		return new Map(entries.filter((entry): entry is readonly [number, Match] => entry !== null));
	}

	async function fetchResults() {
		try {
			const [valueRes, runsRes] = await Promise.all([
				fetch(`${BASE_URL}/api/v1/predictions/value-bets?min_edge=-100&max_results=100`, {
					credentials: 'include'
				}),
				fetch(`${BASE_URL}/api/v1/predictions/runs?per_page=10`, { credentials: 'include' })
			]);

			if (runsRes.ok) {
				const data = await runsRes.json();
				const runs = Array.isArray(data) ? (data as PredictionRun[]) : [];
				const detailedRuns = await Promise.all(
					runs.slice(0, 5).map(async (run) => {
						try {
							const res = await fetch(`${BASE_URL}/api/v1/predictions/runs/${run.id}`, {
								credentials: 'include'
							});
							return res.ok ? ((await res.json()) as PredictionRun) : run;
						} catch {
							return run;
						}
					})
				);
				recentRuns = detailedRuns;

				const predictions = detailedRuns.flatMap((run) =>
					(run.model_predictions ?? []).map((prediction) => ({ run, prediction }))
				);
				const matchMap = await loadMatchMap(predictions.map(({ prediction }) => prediction.match_id));
				modelPredictionRows = predictions.map(({ run, prediction }) => {
					const match = matchMap.get(prediction.match_id);
					const selected = predictionSelection(prediction);
					const bestOdds = bestOddsForSelection(match, prediction.market, selected.selection);
					const impliedProbability = bestOdds.odds ? 1 / bestOdds.odds : null;
					const edge =
						impliedProbability !== null
							? (selected.probability - impliedProbability) * 100
							: null;
					const reliability = prediction.quality_report?.reliability ?? null;
					const marketPick = prediction.quality_report?.market?.pick ?? null;
					const marketProbability =
						selected.selection && prediction.quality_report?.market?.probabilities
							? (prediction.quality_report.market.probabilities[selected.selection] ?? null)
							: null;

					return {
						runId: run.id,
						predictionId: prediction.id,
						model: prediction.model_type || run.model_type,
						matchId: prediction.match_id,
						match: match
							? `${match.home_team} vs ${match.away_team}`
							: `Match #${prediction.match_id}`,
						league: match?.league ?? '--',
						market: prediction.market,
						selection: selected.selection,
						probability: selected.probability,
						homeProb: prediction.home_prob,
						drawProb: prediction.draw_prob,
						awayProb: prediction.away_prob,
						bestOdds: bestOdds.odds,
						bookmaker: bestOdds.bookmaker,
						edge,
						reliability: reliability?.label ?? 'legacy/no-report',
						ticketEligible:
							reliability?.is_ticket_eligible === undefined ? null : reliability.is_ticket_eligible,
						qualityReasons: reliability?.block_reasons ?? [],
						marketPick,
						marketProbability
					};
				});
			}

			if (valueRes.ok) {
				const data = await valueRes.json();
				const items: ValueBetApiItem[] = Array.isArray(data) ? data : (data.items ?? []);
				results = items.map((item) => ({
					strategy_id: 0,
					match_id: item.match_id,
					match_home: item.home_team,
					match_away: item.away_team,
					league: item.league ?? '--',
					market: item.market,
					predicted: item.selection,
					probability: item.model_prob,
					confidence: item.confidence,
					edge: item.edge,
					odds: item.odds
				}));
			}
		} catch {
			// silently handle
		}
	}

	type StrategyRunApiResponse = {
		run_id: number;
		status: string;
		matches_count?: number;
		error?: string | null;
		deduped?: boolean;
	};

	async function runPredictions() {
		if (selectedStrategyIds.length === 0 || selectedMarkets.length === 0) {
			runError = 'Select at least one strategy and one market';
			return;
		}

		running = true;
		runError = '';
		runSuccess = '';
		runWarning = '';
		runProgress = 0;
		const warnings: string[] = [];

		const progressInterval = setInterval(() => {
			runProgress = Math.min(runProgress + 5, 90);
		}, 500);

		try {
			for (const strategyId of selectedStrategyIds) {
				const res = await fetch(`${BASE_URL}/api/v1/strategies/${strategyId}/run`, {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					credentials: 'include',
					body: JSON.stringify({
						match_ids: scopedMatchId !== null ? [scopedMatchId] : [],
						markets: selectedMarkets,
						filters: {
							countries: selectedCountries,
							leagues: selectedLeagues,
							date_from: dateFrom || undefined,
							date_to: dateTo || undefined
						},
						avoid_reprediction: avoidReprediction,
						autopredict: autoPredict
					})
				});

				if (!res.ok) {
					const err = await res.json().catch(() => ({ detail: 'Run failed' }));
					throw new Error(err.detail || `HTTP ${res.status}`);
				}

				const payload = (await res.json()) as StrategyRunApiResponse;
				if (payload.status === 'failed') {
					throw new Error(payload.error || 'Prediction run failed');
				}
				if (payload.status === 'no_matches') {
					throw new Error('No matches matched the selected prediction filters');
				}
				if (payload.status === 'partial') {
					warnings.push(payload.error || 'Prediction run completed partially');
				}
				if (payload.deduped || payload.status === 'deduped') {
					warnings.push(`Strategy ${strategyId}: reused existing prediction run #${payload.run_id}`);
				}
			}

			clearInterval(progressInterval);
			runProgress = 100;
			runSuccess = warnings.length > 0 ? 'Predictions completed with warnings' : 'Predictions completed successfully';
			runWarning = warnings.join(' ');
			await fetchResults();
			await fetchVerification();
			setTimeout(() => {
				runSuccess = '';
				runWarning = '';
				runProgress = 0;
			}, 4000);
		} catch (err) {
			clearInterval(progressInterval);
			runError = err instanceof Error ? err.message : 'Failed to run predictions';
			runProgress = 0;
		} finally {
			running = false;
		}
	}

	async function createStrategy() {
		if (!newStrategyName.trim()) {
			createError = 'Name is required';
			return;
		}

		creatingStrategy = true;
		createError = '';

		try {
			const body: StrategyCreateRequest = {
				name: newStrategyName.trim(),
				model_type: newStrategyModelType,
				description: newStrategyDescription.trim() || undefined
			};

			if (newStrategyParams.trim()) {
				try {
					body.parameters = JSON.parse(newStrategyParams);
				} catch {
					createError = 'Invalid JSON in parameters';
					return;
				}
			}

			const res = await fetch(`${BASE_URL}/api/v1/strategies`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				credentials: 'include',
				body: JSON.stringify(body)
			});

			if (!res.ok) {
				const err = await res.json().catch(() => ({ detail: 'Creation failed' }));
				throw new Error(err.detail || `HTTP ${res.status}`);
			}

			await fetchStrategies();
			dialogOpen = false;
			newStrategyName = '';
			newStrategyModelType = 'poisson';
			newStrategyDescription = '';
			newStrategyParams = '';
		} catch (err) {
			createError = err instanceof Error ? err.message : 'Failed to create strategy';
		} finally {
			creatingStrategy = false;
		}
	}

	function toggleCountry(country: string) {
		if (selectedCountries.includes(country)) {
			selectedCountries = selectedCountries.filter((c) => c !== country);
			const leagueIds = allLeagues
				.filter((l) => l.country === country)
				.map((l) => l.id);
			selectedLeagues = selectedLeagues.filter((id) => !leagueIds.includes(id));
		} else {
			selectedCountries = [...selectedCountries, country];
		}
	}

	function toggleLeague(id: string) {
		if (selectedLeagues.includes(id)) {
			selectedLeagues = selectedLeagues.filter((l) => l !== id);
		} else {
			selectedLeagues = [...selectedLeagues, id];
		}
	}

	function toggleStrategy(id: number) {
		if (selectedStrategyIds.includes(id)) {
			selectedStrategyIds = selectedStrategyIds.filter((s) => s !== id);
		} else {
			selectedStrategyIds = [...selectedStrategyIds, id];
		}
	}

	function toggleMarket(id: string) {
		if (selectedMarkets.includes(id)) {
			selectedMarkets = selectedMarkets.filter((m) => m !== id);
		} else {
			selectedMarkets = [...selectedMarkets, id];
		}
	}

	function exportCSV() {
		const data = sortedResults;
		if (data.length === 0) return;

		const headers = ['Match', 'League', 'Market', 'Predicted', 'Probability', 'Confidence', 'Edge', 'Odds'];
		const rows = data.map((r) => [
			`"${r.match_home} vs ${r.match_away}"`,
			`"${r.league}"`,
			r.market,
			r.predicted,
			r.probability.toFixed(3),
			r.confidence.toFixed(3),
			r.edge.toFixed(3),
			r.odds.toFixed(2)
		]);

		const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
		const blob = new Blob([csv], { type: 'text/csv' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `predictions-${new Date().toISOString().slice(0, 10)}.csv`;
		a.click();
		URL.revokeObjectURL(url);
	}

	function confidenceColor(conf: number): string {
		if (conf > 0.7) return 'text-football-green';
		if (conf > 0.5) return 'text-football-gold';
		return 'text-muted-foreground';
	}

	function edgeColor(edge: number): string {
		return edge > 0 ? 'text-football-green' : 'text-football-red';
	}

	function addPredictionToBetslip(result: StrategyRunResult) {
		betslip.addLeg(
			createBetslipLeg({
				matchId: result.match_id,
				matchName: `${result.match_home} vs ${result.match_away}`,
				market: result.market,
				selection: result.predicted,
				odds: result.odds,
				league: result.league,
				source: 'prediction'
			})
		);
	}

	function formatDateTime(iso: string | null | undefined): string {
		if (!iso) return '--';
		const date = new Date(iso);
		if (Number.isNaN(date.getTime())) return '--';
		return date.toLocaleString('en-GB', {
			day: 'numeric',
			month: 'short',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	onMount(() => {
		fetchCatalog();
		fetchPredictionCatalog();
		fetchStrategies();
		fetchScheduledJobs();
		fetchResults();
		fetchVerification();
		applyFuturePredictionInterval();
	});

	$effect(() => {
		if (autoPredict) {
			const num = parseInt(autoInterval, 10) || 24;
			const unitMap: Record<string, number> = { Hours: 3600000, Days: 86400000, Weeks: 604800000 };
			const ms = num * (unitMap[autoIntervalUnit] ?? 3600000);
			pollTimer = setInterval(runPredictions, ms);
			return () => {
				if (pollTimer) clearInterval(pollTimer);
			};
		} else {
			if (pollTimer) clearInterval(pollTimer);
		}
	});

	$effect(() => {
		resultPollTimer = setInterval(fetchResults, 15000);
		return () => {
			if (resultPollTimer) clearInterval(resultPollTimer);
		};
	});
</script>

<div class="max-w-4xl mx-auto space-y-8" transition:fade={{ duration: 200 }}>
	<div>
		<h1 class="text-2xl font-extrabold font-sport text-foreground">PREDICTIONS</h1>
		<p class="mt-1 text-muted-foreground">Run AI prediction models, view results, and analyze strategies</p>
	</div>

	<BetslipReviewCallout label="Prediction selections are ready for final ticket review." />

	{#if scopedMatchId !== null}
		<div class="flex flex-wrap items-center gap-2 border border-football-gold/30 bg-football-gold/10 px-3 py-2 text-sm text-foreground">
			<Badge variant="warning">Match #{scopedMatchId}</Badge>
			<span class="text-muted-foreground">Predictions will run only for the selected dashboard match.</span>
			<a href="/predict" class="ml-auto text-xs font-medium text-football-blue hover:text-football-gold">Clear</a>
		</div>
	{/if}

	<Card title="Metrics" variant="prediction">
		<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
			<div class="border border-border bg-muted/30 p-3">
				<p class="text-[10px] uppercase tracking-wide text-muted-foreground">Predictii castigate</p>
				<p class="mt-1 font-mono text-lg text-football-green">{verification?.correct_predictions ?? 0}</p>
			</div>
			<div class="border border-border bg-muted/30 p-3">
				<p class="text-[10px] uppercase tracking-wide text-muted-foreground">Predictii pierdute</p>
				<p class="mt-1 font-mono text-lg text-football-red">{verification?.incorrect_predictions ?? 0}</p>
			</div>
			<div class="border border-border bg-muted/30 p-3">
				<p class="text-[10px] uppercase tracking-wide text-muted-foreground">Win rate</p>
				<p class="mt-1 font-mono text-lg text-football-gold">
					{predictionWinRate === null ? '--' : `${predictionWinRate.toFixed(1)}%`}
				</p>
			</div>
			<div class="border border-border bg-muted/30 p-3">
				<p class="text-[10px] uppercase tracking-wide text-muted-foreground">Value candidates</p>
				<p class="mt-1 font-mono text-lg text-foreground">{results.length}</p>
			</div>
		</div>
		<div class="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
			<span>Recent runs: <span class="font-mono text-foreground">{recentRuns.length}</span></span>
			<span>Completed: <span class="font-mono text-football-green">{completedRunCount}</span></span>
			<span>Active: <span class="font-mono text-football-gold">{activeRunCount}</span></span>
			<span>Resolved predictions: <span class="font-mono text-foreground">{verification?.resolved_predictions ?? 0}</span></span>
		</div>
		{#if verificationError}
			<p class="mt-2 text-xs text-football-gold">{verificationError}</p>
		{/if}
	</Card>

	<Card title="Predictii pentru meciuri viitoare" variant="prediction">
		<div class="space-y-4">
			<div class="grid grid-cols-2 gap-3 md:grid-cols-4">
				<Input label="Future days" name="predict-future-days" type="number" min="0" bind:value={predictionFutureDays} />
				<Input label="Future weeks" name="predict-future-weeks" type="number" min="0" bind:value={predictionFutureWeeks} />
				<Input label="Future months" name="predict-future-months" type="number" min="0" bind:value={predictionFutureMonths} />
				<Input label="Future years" name="predict-future-years" type="number" min="0" bind:value={predictionFutureYears} />
			</div>
			<div class="flex flex-wrap items-center gap-3">
				<Button variant="secondary" size="sm" onclick={applyFuturePredictionInterval} disabled={predictionFutureTotalDays <= 0}>
					Apply future window ({predictionFutureTotalDays} days)
				</Button>
				<span class="text-xs text-muted-foreground">Sets the backend-supported strategy filters <span class="font-mono">date_from</span> and <span class="font-mono">date_to</span>.</span>
			</div>
			<div class="border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
				Current prediction target window: <span class="font-mono text-foreground">{dateFrom || 'not set'}</span> → <span class="font-mono text-foreground">{dateTo || 'not set'}</span>.
			</div>
		</div>
	</Card>

	<!-- Section 1: Prediction run form -->
	<Card title="Prediction run form" variant="prediction">
		<div class="space-y-6">
			<!-- Countries -->
			<div>
				<p class="text-sm font-medium text-foreground mb-3">Countries</p>
				{#if loadingCatalog}
					<div class="space-y-2">
						<Skeleton class="h-6 w-full" />
						<Skeleton class="h-6 w-3/4" />
					</div>
				{:else if countries.length === 0}
					<p class="text-sm text-muted-foreground">No countries available</p>
				{:else}
					<div class="grid grid-cols-2 md:grid-cols-3 gap-2">
						{#each countries as country (country.country)}
							<label class={cn(
								'flex items-center space-x-2 p-2 border cursor-pointer transition-colors duration-200',
								selectedCountries.includes(country.country)
									? 'border-football-gold bg-football-gold/5'
									: 'border-border hover:bg-muted'
							)}>
								<input
									type="checkbox"
									checked={selectedCountries.includes(country.country)}
									onchange={() => toggleCountry(country.country)}
									class="w-4 h-4 accent-[hsl(var(--football-gold))]"
								/>
								<span class="text-sm text-foreground">{country.country}</span>
							</label>
						{/each}
					</div>
					{#if selectedCountryBadges.length > 0}
						<div class="flex flex-wrap gap-1.5 mt-2">
							{#each selectedCountryBadges as badge (badge.value)}
								<Badge variant="info">{badge.label}</Badge>
							{/each}
						</div>
					{/if}
				{/if}
			</div>

			<Separator />

			<!-- Leagues -->
			<div>
				<p class="text-sm font-medium text-foreground mb-3">
					Leagues
					{#if selectedCountries.length > 0}
						<span class="text-muted-foreground font-normal">(filtered)</span>
					{/if}
				</p>
				{#if loadingCatalog}
					<div class="space-y-2">
						<Skeleton class="h-6 w-full" />
						<Skeleton class="h-6 w-2/3" />
					</div>
				{:else if filteredLeagues.length === 0}
					<p class="text-sm text-muted-foreground">No leagues available</p>
				{:else}
					<div class="max-h-36 overflow-y-auto scroll-thin space-y-1 border border-border p-2">
						{#each filteredLeagues as league (league.id)}
							<label class={cn(
								'flex items-center space-x-2 p-1.5 cursor-pointer transition-colors duration-200',
								selectedLeagues.includes(league.id) ? 'bg-football-gold/5' : 'hover:bg-muted'
							)}>
								<input
									type="checkbox"
									checked={selectedLeagues.includes(league.id)}
									onchange={() => toggleLeague(league.id)}
									class="w-4 h-4 accent-[hsl(var(--football-gold))]"
								/>
								<span class="text-sm text-foreground">{league.name}</span>
								<span class="text-xs text-muted-foreground ml-auto font-mono">{league.matches_count}</span>
							</label>
						{/each}
					</div>
					{#if selectedLeagueBadges.length > 0}
						<div class="flex flex-wrap gap-1.5 mt-2">
							{#each selectedLeagueBadges as badge (badge.value)}
								<Badge variant="info">{badge.label}</Badge>
							{/each}
						</div>
					{/if}
				{/if}
			</div>

			<Separator />

			<!-- Date Range -->
			<div>
				<p class="text-sm font-medium text-foreground mb-3">Date Range</p>
				<div class="grid grid-cols-2 gap-4">
					<div>
						<label for="predict-date-from" class="text-xs text-muted-foreground mb-1 block">From</label>
						<Input id="predict-date-from" type="date" bind:value={dateFrom} />
					</div>
					<div>
						<label for="predict-date-to" class="text-xs text-muted-foreground mb-1 block">To</label>
						<Input id="predict-date-to" type="date" bind:value={dateTo} />
					</div>
				</div>
			</div>

			<Separator />

			<div class="border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
				Run form summary: <span class="font-mono text-foreground">{selectedFilterCount}</span> selected filters across country, league, market, and strategy controls. Markets and strategies are selected in the sections below.
			</div>
		</div>
	</Card>

	<!-- Section 2: Strategy Selection -->
	<div class="space-y-4">
		<div class="flex items-center justify-between">
			<h2 class="text-lg font-semibold text-foreground">Strategy selectors</h2>
			<Button variant="secondary" size="sm" onclick={() => (dialogOpen = true)}>
				+ Add New Strategy
			</Button>
		</div>

		{#if loadingStrategies}
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
				{#each [1, 2, 3] as _, index (index)}
					<Skeleton class="h-32 w-full" />
				{/each}
			</div>
		{:else if strategyLoadError}
			<Card>
				<p class="text-sm text-football-red text-center py-6">{strategyLoadError}</p>
			</Card>
		{:else if strategies.length === 0}
			<Card>
				<p class="text-sm text-muted-foreground text-center py-6">No strategies yet. Create one to get started.</p>
			</Card>
		{:else}
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
				{#each strategies as strategy (strategy.id)}
					<button
						type="button"
						onclick={() => toggleStrategy(strategy.id)}
						class={cn(
							'text-left p-4 border transition-all duration-200',
							selectedStrategyIds.includes(strategy.id)
								? 'border-football-green bg-football-green/5 shadow-[0_0_20px_rgba(74,222,128,0.1)]'
								: 'border-border hover:border-muted-foreground/30 hover:bg-muted/50'
						)}
					>
						<div class="flex items-start justify-between mb-2">
							<h4 class="font-medium text-foreground">{strategy.name}</h4>
							<Badge variant={modelTypeBadgeVariant[strategy.model_type] ?? 'default'}>
								{strategy.model_type}
							</Badge>
						</div>
						{#if strategy.description}
							<p class="text-xs text-muted-foreground line-clamp-2 mb-2">{strategy.description}</p>
						{/if}
						<div class="flex items-center justify-between mt-auto">
							<Badge variant={strategy.is_active ? 'success' : 'neutral'}>
								{strategy.is_active ? 'Active' : 'Inactive'}
							</Badge>
							{#if hasStrategyAvgEdge(strategy)}
								<span class={cn('text-xs font-mono', edgeColor(strategy.avg_edge))}>
									Edge: {strategy.avg_edge > 0 ? '+' : ''}{strategy.avg_edge.toFixed(1)}%
								</span>
							{/if}
						</div>
					</button>
				{/each}
			</div>
		{/if}
	</div>

		<!-- Section 3: Market selectors -->
		<Card title="Market selectors" variant="prediction">
			<div class="space-y-3">
				<p class="text-sm text-muted-foreground">
					Select at least one market to predict. Options are loaded from the existing prediction catalog when available; fallback labels are shown only if that endpoint is unavailable.
				</p>
				{#if loadingPredictionCatalog}
					<p class="text-xs text-muted-foreground">Loading prediction catalog...</p>
				{:else if predictionCatalogError}
					<p class="text-xs text-football-gold">{predictionCatalogError}; using local fallback market labels.</p>
				{/if}
				<div class="grid grid-cols-2 md:grid-cols-3 gap-2">
					{#each marketOptions as market (market.id)}
						<label class={cn(
							'flex items-center space-x-2 p-2.5 border cursor-pointer transition-colors duration-200',
						selectedMarkets.includes(market.id)
							? 'border-football-gold bg-football-gold/5'
							: 'border-border hover:bg-muted'
					)}>
						<input
							type="checkbox"
							checked={selectedMarkets.includes(market.id)}
							onchange={() => toggleMarket(market.id)}
							class="w-4 h-4 accent-[hsl(var(--football-gold))]"
						/>
						<span class="text-sm text-foreground">{market.label}</span>
					</label>
					{/each}
				</div>
			</div>
		</Card>

	<!-- Section 4: Automatic prediction actions -->
	<Card title="Automatic prediction actions" variant="prediction">
		<div class="space-y-4">
		<div class="space-y-3 border border-border bg-muted/20 p-3">
			<div class="flex flex-wrap items-center justify-between gap-2">
				<div>
					<p class="text-sm font-semibold text-foreground">Predictii automate salvate</p>
					<p class="text-xs text-muted-foreground">
						Butoanele se incarca din joburile persistente <span class="font-mono">/api/v1/jobs</span>.
					</p>
				</div>
				<div class="flex flex-wrap gap-2">
					<Button variant="secondary" size="sm" onclick={fetchScheduledJobs} disabled={loadingScheduledJobs}>
						Refresh
					</Button>
					<Button variant="glow" size="sm" onclick={saveAutomaticPredictionAction} disabled={savingScheduledJob}>
						{savingScheduledJob ? 'Saving...' : 'Save autopredict'}
					</Button>
				</div>
			</div>

			{#if scheduledJobsError}
				<p class="text-xs text-destructive">{scheduledJobsError}</p>
			{/if}

			{#if loadingScheduledJobs}
				<p class="text-xs text-muted-foreground">Loading saved prediction actions...</p>
			{:else if automaticPredictionJobs.length === 0}
				<p class="text-xs text-muted-foreground">Nu exista inca predictii automate salvate.</p>
			{:else}
				<div class="flex flex-wrap gap-2">
					{#each automaticPredictionJobs as scheduledJob (scheduledJob.id)}
						<Button
							variant={scheduledJob.enabled ? 'secondary' : 'ghost'}
							size="sm"
							title={describeScheduledJob(scheduledJob)}
							onclick={() => toggleScheduledJob(scheduledJob.id)}
						>
							{scheduledJob.name}
							<span class="ml-1 font-mono text-[10px]">
								{scheduledJob.enabled ? 'running' : 'paused'}
							</span>
						</Button>
					{/each}
				</div>
			{/if}
		</div>

		<ScheduledJobRunTable jobs={automaticPredictionJobs} title="Recent prediction automation runs" />

		<!-- Progress bar -->
		{#if running}
			<div class="space-y-2" transition:slide={{ duration: 200 }}>
				<div class="flex items-center justify-between text-sm">
					<span class="text-muted-foreground">Running predictions...</span>
					<span class="font-mono text-football-gold">{runProgress}%</span>
				</div>
				<div class="w-full h-2 bg-muted">
					<div
						class="h-2 bg-football-green transition-all duration-500"
						style="width: {runProgress}%"
					></div>
				</div>
			</div>
		{/if}

		{#if runSuccess}
			<div class="p-3 text-sm bg-football-green/10 border border-football-green/30 text-football-green" transition:slide={{ duration: 200 }}>
				{runSuccess}
			</div>
		{/if}

		{#if runWarning}
			<div class="p-3 text-sm bg-football-gold/10 border border-football-gold/30 text-football-gold" transition:slide={{ duration: 200 }}>
				{runWarning}
			</div>
		{/if}

		{#if runError}
			<div class="p-3 text-sm bg-destructive/10 border border-destructive/30 text-destructive" transition:slide={{ duration: 200 }}>
				{runError}
			</div>
		{/if}

		<div class="space-y-4">
			<div class="flex flex-wrap items-center gap-4">
				<Button
					variant="glow"
					size="lg"
					disabled={running || selectedStrategyIds.length === 0 || selectedMarkets.length === 0}
					onclick={runPredictions}
				>
					{#if running}
						<span class="flex items-center gap-2">
							<span class="h-4 w-4 border-2 border-foreground border-t-transparent animate-spin"></span>
							Running...
						</span>
					{:else}
						Run Predictions
					{/if}
				</Button>

				<div class="flex flex-wrap items-center gap-3">
					<label class="flex items-center gap-2 text-sm text-muted-foreground">
						<input
							type="checkbox"
							checked={autoPredict}
							onchange={() => (autoPredict = !autoPredict)}
							class="h-4 w-4 accent-[hsl(var(--football-green))]"
						/>
						Autopredict
					</label>
					<label class="flex items-center gap-2 text-sm text-muted-foreground">
						<input
							type="checkbox"
							checked={avoidReprediction}
							onchange={() => (avoidReprediction = !avoidReprediction)}
							class="h-4 w-4 accent-[hsl(var(--football-gold))]"
						/>
						Avoid reprediction
					</label>
				</div>
			</div>

			{#if autoPredict}
				<div class="flex items-end gap-2 border-l-2 border-football-green/30 pl-4" transition:slide={{ duration: 200 }}>
					<div>
						<label for="predict-auto-interval" class="text-xs text-muted-foreground mb-1 block">Autopredict interval</label>
						<Input id="predict-auto-interval" type="number" bind:value={autoInterval} class="w-24" />
					</div>
					<Select bind:value={autoIntervalUnit} options={unitOptions} />
				</div>
			{/if}

			{#if predictionControlNotes.length > 0}
				<div class="space-y-1 border border-football-gold/30 bg-football-gold/10 p-3 text-xs text-football-gold">
					{#each predictionControlNotes as note (note)}
						<p>{note}</p>
					{/each}
				</div>
			{/if}
		</div>
		</div>
	</Card>

	{#if recentRuns.length > 0}
		<Card title="Recent Prediction Runs" variant="prediction">
			<div class="space-y-2">
				{#each recentRuns as run (run.id)}
					<div class="flex flex-wrap items-center justify-between gap-3 border border-border bg-muted/20 px-3 py-2">
						<div class="min-w-0">
							<p class="font-mono text-sm text-foreground">Run #{run.id}</p>
							<p class="text-xs text-muted-foreground">
								{run.model_type} · {run.matches_count ?? 0} matches · {formatDateTime(run.completed_at ?? run.created_at)}
							</p>
						</div>
						<div class="flex items-center gap-2">
							<Badge
								variant={
									run.status === 'completed'
										? 'success'
										: run.status === 'failed'
											? 'danger'
											: run.status === 'partial'
												? 'warning'
												: 'info'
								}
							>
								{run.status}
							</Badge>
							<a href="/data" class="text-xs font-medium text-football-blue hover:text-football-gold">
								Open Data Hub
							</a>
						</div>
					</div>
				{/each}
				<p class="text-xs text-muted-foreground">
					Value candidates below are loaded from the latest completed prediction run.
				</p>
			</div>
		</Card>
	{/if}

	{#if sortedModelPredictionRows.length > 0}
		<Card title="Model Predictions" variant="prediction">
			<div class="space-y-3">
				<p class="text-sm text-muted-foreground">
					These are the raw model outputs. The pick is the highest-probability 1X2 outcome for each match.
				</p>
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="border-b border-border bg-muted/50 text-xs uppercase text-muted-foreground">
							<tr>
								<th class="px-3 py-2 text-left">Run</th>
								<th class="px-3 py-2 text-left">Match</th>
								<th class="px-3 py-2 text-left">Model</th>
								<th class="px-3 py-2 text-left">Pick</th>
								<th class="px-3 py-2 text-left">Reliability</th>
								<th class="px-3 py-2 text-left">Market</th>
								<th class="px-3 py-2 text-right">Home</th>
								<th class="px-3 py-2 text-right">Draw</th>
								<th class="px-3 py-2 text-right">Away</th>
								<th class="px-3 py-2 text-right">Best Odds</th>
								<th class="px-3 py-2 text-right">Edge</th>
							</tr>
						</thead>
						<tbody>
							{#each sortedModelPredictionRows.slice(0, 30) as prediction (prediction.predictionId)}
								<tr class="border-b border-border last:border-0 hover:bg-muted/30">
									<td class="px-3 py-2 font-mono text-xs">#{prediction.runId}</td>
									<td class="px-3 py-2">
										<div class="font-medium text-foreground">{prediction.match}</div>
										<div class="text-xs text-muted-foreground">{prediction.league}</div>
									</td>
									<td class="px-3 py-2 text-xs text-muted-foreground">{prediction.model}</td>
									<td class="px-3 py-2">
										<Badge variant="success">{prediction.selection}</Badge>
										<span class="ml-2 font-mono text-xs">
											{(prediction.probability * 100).toFixed(1)}%
										</span>
									</td>
									<td class="px-3 py-2">
										<div class="flex flex-col gap-1">
											<Badge variant={reliabilityVariant(prediction.reliability)}>
												{prediction.reliability}
											</Badge>
											<span class="text-[10px] text-muted-foreground">
												{prediction.ticketEligible === null
													? 'legacy prediction'
													: prediction.ticketEligible
														? 'ticket eligible'
														: 'blocked from tickets'}
											</span>
											{#if prediction.qualityReasons.length > 0}
												<span class="max-w-44 truncate text-[10px] text-muted-foreground" title={prediction.qualityReasons.join(', ')}>
													{prediction.qualityReasons.join(', ')}
												</span>
											{/if}
										</div>
									</td>
									<td class="px-3 py-2 text-xs">
										{#if prediction.marketPick}
											<div class="font-medium text-foreground">{prediction.marketPick}</div>
											<div class="font-mono text-[10px] text-muted-foreground">
												{prediction.marketProbability === null
													? '--'
													: `${(prediction.marketProbability * 100).toFixed(1)}% market`}
											</div>
										{:else}
											<span class="text-muted-foreground">--</span>
										{/if}
									</td>
									<td class="px-3 py-2 text-right font-mono text-xs">
										{(prediction.homeProb * 100).toFixed(1)}%
									</td>
									<td class="px-3 py-2 text-right font-mono text-xs">
										{prediction.drawProb === null ? '--' : `${(prediction.drawProb * 100).toFixed(1)}%`}
									</td>
									<td class="px-3 py-2 text-right font-mono text-xs">
										{(prediction.awayProb * 100).toFixed(1)}%
									</td>
									<td class="px-3 py-2 text-right">
										{#if prediction.bestOdds}
											<div class="font-mono text-xs">{prediction.bestOdds.toFixed(2)}</div>
											<div class="text-[10px] text-muted-foreground">{prediction.bookmaker}</div>
										{:else}
											<span class="text-xs text-muted-foreground">--</span>
										{/if}
									</td>
									<td class="px-3 py-2 text-right">
										{#if prediction.edge !== null}
											<span class={cn('font-mono text-xs font-semibold', edgeColor(prediction.edge))}>
												{prediction.edge > 0 ? '+' : ''}{prediction.edge.toFixed(2)}%
											</span>
										{:else}
											<span class="text-xs text-muted-foreground">--</span>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		</Card>
	{/if}

	<!-- Section 5: Results -->
	{#if results.length > 0}
		<div class="space-y-4">
			<div class="flex items-center justify-between">
				<h2 class="text-lg font-semibold text-foreground">Prediction Value Candidates</h2>
				<Button variant="secondary" size="sm" onclick={exportCSV}>
					Export CSV
				</Button>
			</div>

			{#if resultTabs.length > 1}
				<Tabs bind:activeTab={activeResultTab} tabs={resultTabs}>
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead class="text-xs uppercase bg-muted border-b border-border text-muted-foreground">
								<tr>
									<th class="px-3 py-2 text-left">Match</th>
									<th class="px-3 py-2 text-left">League</th>
									<th class="px-3 py-2 text-left">Market</th>
									<th class="px-3 py-2 text-left">Predicted</th>
									<th class="px-3 py-2 text-right">Probability</th>
									<th class="px-3 py-2 text-right">Confidence</th>
									<th class="px-3 py-2 text-right">Edge</th>
									<th class="px-3 py-2 text-right">Action</th>
								</tr>
							</thead>
							<tbody>
								{#each sortedResults as result, i (i)}
									<tr class="border-b border-border transition-colors duration-200 hover:bg-muted">
										<td class="px-3 py-2.5 text-foreground">
											{result.match_home} vs {result.match_away}
										</td>
										<td class="px-3 py-2.5 text-muted-foreground text-xs">
											{result.league}
										</td>
										<td class="px-3 py-2.5">
											<Badge variant="neutral">{result.market}</Badge>
										</td>
										<td class="px-3 py-2.5 font-medium text-foreground">
											{result.predicted}
										</td>
										<td class="px-3 py-2.5 text-right font-mono text-xs">
											{(result.probability * 100).toFixed(1)}%
										</td>
										<td class="px-3 py-2.5 text-right">
											<span class={cn('font-mono text-xs', confidenceColor(result.confidence))}>
												{(result.confidence * 100).toFixed(1)}%
											</span>
										</td>
										<td class="px-3 py-2.5 text-right">
											<span class={cn('font-mono text-xs font-semibold', edgeColor(result.edge))}>
												{result.edge > 0 ? '+' : ''}{result.edge.toFixed(2)}%
											</span>
										</td>
										<td class="px-3 py-2.5 text-right">
											<Button variant="secondary" size="sm" onclick={() => addPredictionToBetslip(result)}>
												Add
											</Button>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</Tabs>
			{:else}
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="text-xs uppercase bg-muted border-b border-border text-muted-foreground">
							<tr>
								<th class="px-3 py-2 text-left">Match</th>
								<th class="px-3 py-2 text-left">League</th>
								<th class="px-3 py-2 text-left">Market</th>
								<th class="px-3 py-2 text-left">Predicted</th>
								<th class="px-3 py-2 text-right">Probability</th>
								<th class="px-3 py-2 text-right">Confidence</th>
								<th class="px-3 py-2 text-right">Edge</th>
								<th class="px-3 py-2 text-right">Action</th>
							</tr>
						</thead>
						<tbody>
							{#each sortedResults as result, i (i)}
								<tr class="border-b border-border transition-colors duration-200 hover:bg-muted">
									<td class="px-3 py-2.5 text-foreground">
										{result.match_home} vs {result.match_away}
									</td>
									<td class="px-3 py-2.5 text-muted-foreground text-xs">
										{result.league}
									</td>
									<td class="px-3 py-2.5">
										<Badge variant="neutral">{result.market}</Badge>
									</td>
									<td class="px-3 py-2.5 font-medium text-foreground">
										{result.predicted}
									</td>
									<td class="px-3 py-2.5 text-right font-mono text-xs">
										{(result.probability * 100).toFixed(1)}%
									</td>
									<td class="px-3 py-2.5 text-right">
										<span class={cn('font-mono text-xs', confidenceColor(result.confidence))}>
											{(result.confidence * 100).toFixed(1)}%
										</span>
									</td>
									<td class="px-3 py-2.5 text-right">
										<span class={cn('font-mono text-xs font-semibold', edgeColor(result.edge))}>
											{result.edge > 0 ? '+' : ''}{result.edge.toFixed(2)}%
										</span>
									</td>
									<td class="px-3 py-2.5 text-right">
										<Button variant="secondary" size="sm" onclick={() => addPredictionToBetslip(result)}>
											Add
										</Button>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{:else if !loadingStrategies}
		<Card variant="prediction">
			<p class="text-sm text-muted-foreground text-center py-6">
				{recentRuns.length > 0
					? 'Prediction runs exist, but no value candidates matched the latest completed run yet.'
					: 'No prediction results yet. Select strategies and run predictions to see results.'}
			</p>
		</Card>
	{/if}
</div>

<!-- Strategy Creation Dialog -->
{#if dialogOpen}
	<DialogRoot onOpenChange={(open) => { if (!open) dialogOpen = false; }}>
		<DialogContent>
			<DialogHeader>
				<DialogTitle>Create New Strategy</DialogTitle>
			</DialogHeader>

			<div class="space-y-4">
				{#if createError}
					<div class="p-3 text-sm bg-destructive/10 border border-destructive/30 text-destructive">
						{createError}
					</div>
				{/if}

				<Input
					label="Name"
					bind:value={newStrategyName}
					placeholder="e.g., Poisson Model v2"
				/>

				<Select
					label="Model Type"
					bind:value={newStrategyModelType}
					options={modelTypeOptions}
				/>

				<div>
					<label for="strategy-description" class="text-sm font-medium leading-none mb-1.5 block">Description</label>
					<textarea
						id="strategy-description"
						bind:value={newStrategyDescription}
						placeholder="Optional description of the strategy"
						rows="2"
						class="flex w-full border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
					></textarea>
				</div>

				<div>
					<label for="strategy-params" class="text-sm font-medium leading-none mb-1.5 block">Parameters (JSON)</label>
					<textarea
						id="strategy-params"
						bind:value={newStrategyParams}
						placeholder={'{"rho": -0.13, "home_advantage": 0.25}'}
						rows="3"
						class="flex w-full border border-border bg-background px-3 py-2 text-sm font-mono placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
					></textarea>
				</div>
			</div>

			<DialogFooter>
				<Button variant="ghost" onclick={() => (dialogOpen = false)}>Cancel</Button>
				<Button
					variant="primary"
					disabled={creatingStrategy || !newStrategyName.trim()}
					onclick={createStrategy}
				>
					{creatingStrategy ? 'Creating...' : 'Create Strategy'}
				</Button>
			</DialogFooter>
		</DialogContent>
	</DialogRoot>
{/if}
