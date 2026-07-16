<script lang="ts">
	import { onMount } from 'svelte';
	import { SvelteMap } from 'svelte/reactivity';
	import { page } from '$app/state';
	import { fade } from 'svelte/transition';
	import {
		AlertTriangle,
		ArrowRight,
		BarChart3,
		CheckCircle2,
		ChevronDown,
		Clock3,
		Layers3,
		Link2,
		Loader2,
		Play,
		RefreshCw,
		Search,
		Settings2,
		ShieldCheck,
		Ticket,
		XCircle
	} from 'lucide-svelte';
	import BetslipReviewCallout from '$lib/components/BetslipReviewCallout.svelte';
	import RiskLadder from '$lib/components/RiskLadder.svelte';
	import StrategyComparison from '$lib/components/StrategyComparison.svelte';
	import AnalysisModelEvidence from '$lib/components/AnalysisModelEvidence.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Skeleton from '$lib/components/ui/skeleton/skeleton.svelte';
	import { createRequestGeneration } from '$lib/async-request';
	import { ApiClientError } from '$lib/api/client';
	import { dataApi } from '$lib/api/data';
	import { matchesApi } from '$lib/api/matches';
	import { predictionsApi } from '$lib/api/predictions';
	import { strategiesApi } from '$lib/api/strategies';
	import { betslip, createBetslipLeg } from '$lib/stores/betslip';
	import type {
		Match,
		PredictionRun,
		PredictionCalibrationReport,
		PredictionScoreGridItem,
		Strategy,
		StrategyBatchRunResponse
	} from '$lib/types';
	import {
		buildTicketsHandoffUrl,
		candidateCountLabel,
		chooseAnalysisDataset,
		datasetCoverage,
		datasetCountryLabel,
		datasetJobId,
		isStrategyRunnable,
		normalizeStrategies,
		parseAnalysisReturnContext,
		progressFromBatchRun,
		runCountLabel,
		selectModelOutcome,
		nextCandidateWindowSize,
		strategyCountLabel,
		strategyUnavailableReason,
		type DatasetReadiness,
		type StrategyProgress,
		visibleCandidateWindow
	} from './strategy.helpers';

	type MarketOption = { id: string; label: string; description: string };
	type AnalysisCandidate = {
		id: number;
		runId: number;
		strategyId: number;
		strategyName: string;
		model: string;
		matchId: number;
		match: string;
		league: string;
		kickoff: string | null;
		market: string;
		selection: string;
		probability: number;
		odds: number | null;
		edge: number | null;
		marketProbability: number | null;
		marketGap: number | null;
		trainingMatches: number | null;
		reliability: string;
		reliabilityScore: number | null;
		ticketEligible: boolean | null;
		qualityReasons: string[];
	};

	const marketOptions: MarketOption[] = [
		{ id: '1x2', label: 'Rezultat final (1X2)', description: 'Gazde, egal sau oaspeți' },
		{ id: 'btts', label: 'Ambele marchează', description: 'Da / Nu' },
		{ id: 'ou_2_5', label: 'Peste / sub 2.5', description: 'Total goluri' }
	];
	const resultRequests = createRequestGeneration();

	let loading = $state(true);
	let loadError = $state('');
	let datasetItems = $state<DatasetReadiness[]>([]);
	let selectedDatasetId = $state('');
	let strategies = $state<Strategy[]>([]);
	let selectedStrategyIds = $state<number[]>([]);
	let showUnavailableStrategies = $state(false);
	let strategySearch = $state('');
	let selectedMarkets = $state<string[]>((['1x2', 'btts', 'ou_2_5']));
	let avoidReprediction = $state(true);
	let dateFrom = $state('');
	let dateTo = $state('');
	let batchRunning = $state(false);
	let progress = $state<StrategyProgress[]>([]);
	let batchError = $state('');
	let batchNotice = $state('');
	let lastBatchResponses = $state<StrategyBatchRunResponse[]>([]);
	let detailedRuns = $state<PredictionRun[]>([]);
	let recentRuns = $state<PredictionRun[]>([]);
	let runStrategyMap = $state<Record<number, number>>({});
	let candidates = $state<AnalysisCandidate[]>([]);
	let resultsLoading = $state(false);
	let resultsError = $state('');
	let calibrationReport = $state<PredictionCalibrationReport | null>(null);
	let calibrationLoading = $state(false);
	let calibrationError = $state('');
	let scoreGridRows = $state<PredictionScoreGridItem[]>([]);
	let scoreGridLoading = $state(false);
	let scoreGridError = $state('');
	let resultSearch = $state('');
	let resultStrategy = $state('all');
	let resultLeague = $state('all');
	let resultMarket = $state('all');
	let resultReliability = $state('all');
	let eligibleOnly = $state(false);
	let minEdge = $state('');
	let minProbability = $state('');
	let minMarketGap = $state('');
	let selectedPredictionIds = $state<number[]>([]);
	let visibleCandidateLimit = $state(25);

	const selectedReadiness = $derived(
		datasetItems.find((item) => String(item.dataset.id) === selectedDatasetId) ?? null
	);
	const selectedDataset = $derived(selectedReadiness?.dataset ?? null);
	const selectedDatasetCountry = $derived(
		selectedDataset ? datasetCountryLabel(selectedDataset) : 'nespecificat'
	);
	const coverage = $derived(
		selectedDataset
			? datasetCoverage(selectedDataset)
			: { leagues: [] as string[], dateFrom: null, dateTo: null }
	);
	const selectedDatasetReady = $derived(
		['completed', 'partial'].includes(selectedReadiness?.jobStatus ?? '') &&
			(selectedDataset?.matches_count ?? 0) > 0
	);
	const runnableStrategies = $derived(strategies.filter(isStrategyRunnable));
	const unavailableStrategies = $derived(strategies.filter((strategy) => !isStrategyRunnable(strategy)));
	const filteredStrategies = $derived.by(() => {
		const term = strategySearch.trim().toLocaleLowerCase('ro');
		const visibleStrategies = showUnavailableStrategies
			? strategies
			: runnableStrategies;
		if (!term) return visibleStrategies;
		return visibleStrategies.filter((strategy) =>
			[strategy.name, strategy.model_type, strategy.description]
				.filter(Boolean)
				.join(' ')
				.toLocaleLowerCase('ro')
				.includes(term)
		);
	});
	const selectedRunnableCount = $derived(
		runnableStrategies.filter((strategy) => selectedStrategyIds.includes(strategy.id)).length
	);
	const allRunnableSelected = $derived(
		runnableStrategies.length > 0 && selectedRunnableCount === runnableStrategies.length
	);
	const analysisCanRun = $derived(
		selectedDatasetReady &&
			selectedStrategyIds.length > 0 &&
			selectedMarkets.length > 0 &&
			!batchRunning &&
			!resultsLoading
	);
	const preflightReason = $derived(
		!selectedDatasetReady
			? 'Pregătește un set de date valid înainte de rulare.'
			: selectedStrategyIds.length === 0
				? 'Selectează cel puțin o strategie rulabilă.'
				: selectedMarkets.length === 0
					? 'Selectează cel puțin o piață.'
					: ''
	);
	const progressRows = $derived(
		strategies
			.filter((strategy) => selectedStrategyIds.includes(strategy.id))
			.map((strategy) => ({
				strategy,
				progress:
					progress.find((item) => item.strategyId === strategy.id) ??
					({
						strategyId: strategy.id,
						status: 'idle',
						runId: null,
						matchesCount: 0,
						error: null
					} satisfies StrategyProgress)
			}))
	);
	const terminalProgress = $derived(
		progress.filter((item) => !['idle', 'queued', 'running'].includes(item.status))
	);
	const completedCount = $derived(
		terminalProgress.filter((item) => item.status === 'completed' || item.status === 'reused').length
	);
	const partialCount = $derived(terminalProgress.filter((item) => item.status === 'partial').length);
	const failedIds = $derived(
		progress.filter((item) => item.status === 'failed').map((item) => item.strategyId)
	);
	const successfulRunIds = $derived(
		Array.from(
			new Set(
				progress
					.filter((item) => ['completed', 'partial', 'reused'].includes(item.status))
					.map((item) => item.runId)
					.filter((id): id is number => id !== null)
			)
		)
	);
	const batchProgressPercent = $derived(
		selectedStrategyIds.length > 0
			? Math.round((terminalProgress.length / selectedStrategyIds.length) * 100)
			: 0
	);
	const latestResolution = $derived(lastBatchResponses.at(-1) ?? null);
	const candidateStrategyOptions = $derived([
		{ value: 'all', label: 'Toate strategiile' },
		...Array.from(new Set(candidates.map((candidate) => candidate.strategyId))).map((id) => ({
			value: String(id),
			label: strategies.find((strategy) => strategy.id === id)?.name ?? `Strategia #${id}`
		}))
	]);
	const candidateMarketOptions = $derived([
		{ value: 'all', label: 'Toate piețele' },
		...Array.from(new Set(candidates.map((candidate) => candidate.market))).map((market) => ({
			value: market,
			label: marketLabel(market)
		}))
	]);
	const candidateLeagueOptions = $derived([
		{ value: 'all', label: 'Toate ligile' },
		...Array.from(new Set(candidates.map((candidate) => candidate.league))).map((league) => ({
			value: league,
			label: league
		}))
	]);
	const candidateReliabilityOptions = $derived([
		{ value: 'all', label: 'Orice fiabilitate' },
		...Array.from(new Set(candidates.map((candidate) => candidate.reliability))).map((label) => ({
			value: label,
			label: reliabilityLabel(label)
		}))
	]);
	const filteredCandidates = $derived.by(() => {
		const search = resultSearch.trim().toLocaleLowerCase('ro');
		const edgeThreshold = Number.parseFloat(minEdge);
		const probabilityThreshold = Number.parseFloat(minProbability);
		const marketGapThreshold = Number.parseFloat(minMarketGap);
		return [...candidates]
			.filter((candidate) => resultStrategy === 'all' || candidate.strategyId === Number(resultStrategy))
			.filter((candidate) => resultLeague === 'all' || candidate.league === resultLeague)
			.filter((candidate) => resultMarket === 'all' || candidate.market === resultMarket)
			.filter((candidate) => resultReliability === 'all' || candidate.reliability === resultReliability)
			.filter((candidate) => !eligibleOnly || candidate.ticketEligible === true)
			.filter((candidate) => !Number.isFinite(edgeThreshold) || (candidate.edge ?? -Infinity) >= edgeThreshold)
			.filter((candidate) => !Number.isFinite(probabilityThreshold) || candidate.probability * 100 >= probabilityThreshold)
			.filter((candidate) => !Number.isFinite(marketGapThreshold) || (candidate.marketGap ?? -Infinity) >= marketGapThreshold)
			.filter(
				(candidate) =>
					!search ||
					[candidate.match, candidate.league, candidate.strategyName, candidate.selection]
						.join(' ')
						.toLocaleLowerCase('ro')
						.includes(search)
			)
			.sort((a, b) => (b.edge ?? -Infinity) - (a.edge ?? -Infinity));
	});
	const visibleCandidates = $derived(
		visibleCandidateWindow(filteredCandidates, visibleCandidateLimit)
	);
	const candidateFiltersActive = $derived(
		resultSearch.trim() !== '' ||
		resultStrategy !== 'all' ||
		resultLeague !== 'all' ||
		resultMarket !== 'all' ||
		resultReliability !== 'all' ||
		eligibleOnly ||
		minEdge.trim() !== '' ||
		minProbability.trim() !== '' ||
		minMarketGap.trim() !== ''
	);
	const eligibleCandidateCount = $derived(candidates.filter((candidate) => candidate.ticketEligible === true).length);
	const warningCandidateCount = $derived(
		candidates.filter((candidate) => candidate.qualityReasons.length > 0).length
	);
	const eligibleMatchProbabilities = $derived.by(() => {
		const bestByMatch: Record<number, number> = {};
		for (const candidate of candidates) {
			if (candidate.ticketEligible !== true || !Number.isFinite(candidate.probability)) continue;
			const current = bestByMatch[candidate.matchId] ?? 0;
			bestByMatch[candidate.matchId] = Math.max(current, candidate.probability);
		}
		return Object.values(bestByMatch).sort((a, b) => b - a);
	});
	const eligibleUniqueMatchCount = $derived(new Set(candidates.filter((candidate) => candidate.ticketEligible === true).map((candidate) => candidate.matchId)).size);
	const ticketsUrl = $derived(
		selectedDataset
			? buildTicketsHandoffUrl(selectedDataset.id, successfulRunIds, selectedPredictionIds)
			: '/tickets'
	);

	function marketLabel(market: string): string {
		return (
			{
				'1x2': 'Rezultat final (1X2)',
				btts: 'Ambele marchează',
				ou_2_5: 'Peste / sub 2.5',
				'over_under_2.5': 'Peste / sub 2.5'
			} as Record<string, string>
		)[market] ?? market;
	}

	function reliabilityLabel(label: string): string {
		return (
			{
				reliable: 'Fiabilă',
				moderate: 'Moderată',
				unreliable: 'Slabă',
				'legacy/no-report': 'Neverificată',
				neverificat: 'Neverificată'
			} as Record<string, string>
		)[label] ?? label;
	}

	function formatDateTime(value: string | null | undefined): string {
		if (!value) return '—';
		const date = new Date(value);
		if (Number.isNaN(date.getTime())) return '—';
		return date.toLocaleString('ro-RO', {
			day: '2-digit',
			month: 'short',
			year: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function formatPercent(value: number | null, digits = 1): string {
		return value === null || !Number.isFinite(value) ? '—' : `${value.toFixed(digits)}%`;
	}

	function formatProbability(value: number): string {
		return `${(value * 100).toFixed(1)}%`;
	}

	function datasetLabel(item: DatasetReadiness): string {
		const state = item.jobStatus === 'completed' ? 'pregătit' : item.jobStatus ?? 'neverificat';
		return `#${item.dataset.id} · ${item.dataset.matches_count ?? 0} meciuri · ${state}`;
	}

	function toggleStrategy(id: number) {
		const strategy = strategies.find((item) => item.id === id);
		if (!strategy || !isStrategyRunnable(strategy) || batchRunning) return;
		selectedStrategyIds = selectedStrategyIds.includes(id)
			? selectedStrategyIds.filter((item) => item !== id)
			: [...selectedStrategyIds, id];
	}

	function selectAllRunnable() {
		selectedStrategyIds = runnableStrategies.map((strategy) => strategy.id);
	}

	function clearStrategies() {
		selectedStrategyIds = [];
	}

	function toggleMarket(id: string) {
		if (batchRunning) return;
		selectedMarkets = selectedMarkets.includes(id)
			? selectedMarkets.filter((market) => market !== id)
			: [...selectedMarkets, id];
	}

	function changeDataset() {
		if (batchRunning) return;
		resultRequests.invalidate();
		resultsLoading = false;
		calibrationLoading = false;
		scoreGridLoading = false;
		progress = [];
		lastBatchResponses = [];
		detailedRuns = [];
		candidates = [];
		resetCandidateWindow();
		selectedPredictionIds = [];
		batchError = '';
		batchNotice = '';
	}

	function setProgress(strategyId: number, update: Partial<StrategyProgress>) {
		const current = progress.find((item) => item.strategyId === strategyId) ?? {
			strategyId,
			status: 'idle' as const,
			runId: null,
			matchesCount: 0,
			error: null
		};
		progress = [
			...progress.filter((item) => item.strategyId !== strategyId),
			{ ...current, ...update }
		];
	}

	async function fetchInitialData() {
		loading = true;
		loadError = '';
		try {
			const [datasets, strategyResponse, runs] = await Promise.all([
				dataApi.getDatasets(),
				strategiesApi.list(),
				predictionsApi.getRuns().catch(() => [])
			]);
			const jobResults = await Promise.allSettled(
				datasets.map(async (dataset) => {
					const jobId = datasetJobId(dataset);
					if (!jobId) return { dataset, jobId: null, jobStatus: null } satisfies DatasetReadiness;
					const job = await dataApi.getJob(jobId);
					return { dataset, jobId, jobStatus: job.status } satisfies DatasetReadiness;
				})
			);
			datasetItems = jobResults.map((result, index) =>
				result.status === 'fulfilled'
					? result.value
					: {
						dataset: datasets[index],
						jobId: datasetJobId(datasets[index]),
						jobStatus: null
					}
			);
			const requestedRaw = page.url.searchParams.get('dataset_id') ?? page.url.searchParams.get('dataset');
			const requestedId = requestedRaw ? Number.parseInt(requestedRaw, 10) : null;
			const preferred = chooseAnalysisDataset(
				datasetItems,
				requestedId && Number.isFinite(requestedId) ? requestedId : null
			);
			selectedDatasetId = preferred ? String(preferred.dataset.id) : '';
			strategies = normalizeStrategies(strategyResponse);
			selectedStrategyIds = strategies.filter(isStrategyRunnable).map((strategy) => strategy.id);
			recentRuns = runs.slice(0, 8);
			const returnContext = parseAnalysisReturnContext(page.url.searchParams);
			if (returnContext.runIds.length > 0) {
				await loadRunResults(returnContext.runIds, returnContext.predictionIds);
				batchNotice = `Am restaurat ${detailedRuns.length} run${detailedRuns.length === 1 ? '' : '-uri'} și ${selectedPredictionIds.length} selecți${selectedPredictionIds.length === 1 ? 'e' : 'i'} din fluxul de bilete.`;
			}
		} catch (error) {
			loadError = error instanceof ApiClientError ? error.message : 'Nu am putut încărca datele pentru analiză.';
		} finally {
			loading = false;
		}
	}

	function runRequestFilters() {
		if (!dateFrom && !dateTo) return undefined;
		return {
			countries: [],
			leagues: [],
			date_from: dateFrom || undefined,
			date_to: dateTo || undefined
		};
	}

	async function executeQueue(strategyIds: number[], resetAll = false) {
		if (
			!selectedDatasetReady ||
			selectedMarkets.length === 0 ||
			strategyIds.length === 0 ||
			batchRunning ||
			resultsLoading
		) return;
		resultRequests.invalidate();
		resultsLoading = false;
		calibrationLoading = false;
		scoreGridLoading = false;
		batchRunning = true;
		batchError = '';
		batchNotice = '';
		if (resetAll) {
			progress = selectedStrategyIds.map((strategyId) => ({
				strategyId,
				status: 'queued',
				runId: null,
				matchesCount: 0,
				error: null
			}));
			lastBatchResponses = [];
			runStrategyMap = {};
			detailedRuns = [];
			candidates = [];
			resetCandidateWindow();
			selectedPredictionIds = [];
		} else {
			for (const strategyId of strategyIds) {
				setProgress(strategyId, { status: 'queued', runId: null, matchesCount: 0, error: null });
			}
		}

		for (const strategyId of strategyIds) {
			setProgress(strategyId, { status: 'running', runId: null, matchesCount: 0, error: null });
		}

		try {
			const response = await predictionsApi.runStrategyBatch({
				dataset_id: selectedDataset!.id,
				strategy_ids: strategyIds,
				markets: selectedMarkets,
				filters: runRequestFilters(),
				avoid_reprediction: avoidReprediction,
				allow_partial_resolution: false
			});
			lastBatchResponses = [...lastBatchResponses, response];
			const returnedRuns = new Map(
				response.runs
					.filter((run) => typeof run.strategy_id === 'number')
					.map((run) => [run.strategy_id as number, run])
			);

			for (const strategyId of strategyIds) {
				const run = returnedRuns.get(strategyId);
				if (!run) {
					setProgress(strategyId, {
						status: response.status === 'no_matches' ? 'no_matches' : 'failed',
						error:
							response.status === 'no_matches'
								? 'Setul de date nu conține meciuri rezolvabile pentru această strategie.'
								: 'Backendul nu a returnat rezultatul strategiei.'
					});
					continue;
				}
				const normalized = progressFromBatchRun(run);
				if (!normalized) {
					setProgress(strategyId, { status: 'failed', error: 'Rezultatul strategiei este invalid.' });
					continue;
				}
				setProgress(strategyId, normalized);
				if (normalized.runId) {
					runStrategyMap = { ...runStrategyMap, [normalized.runId]: strategyId };
				}
			}
		} catch (error) {
			const message = error instanceof ApiClientError ? error.message : 'Analiza nu a putut fi rulată.';
			for (const strategyId of strategyIds) {
				setProgress(strategyId, { status: 'failed', error: message });
			}
		}
		try {
			await loadRunResults();
		} finally {
			batchRunning = false;
		}
		const failed = progress.filter((item) => item.status === 'failed').length;
		batchNotice = failed > 0
			? `Analiza s-a încheiat cu ${failed} strateg${failed === 1 ? 'ie eșuată' : 'ii eșuate'}. Rezultatele reușite au fost păstrate.`
			: 'Toate strategiile selectate au primit un rezultat terminal.';
	}

	async function runAnalysis() {
		if (!selectedDatasetReady) {
			batchError = 'Alege un set de date creat de un job de colectare finalizat.';
			return;
		}
		if (selectedStrategyIds.length === 0) {
			batchError = 'Selectează cel puțin o strategie rulabilă.';
			return;
		}
		if (selectedMarkets.length === 0) {
			batchError = 'Selectează cel puțin o piață.';
			return;
		}
		await executeQueue(selectedStrategyIds, true);
	}

	async function retryFailed() {
		await executeQueue(failedIds, false);
	}

	async function loadRunResults(
		restoredRunIds?: number[],
		restoredPredictionIds: number[] = []
	) {
		const requestId = resultRequests.next();
		const runIds = restoredRunIds ?? Array.from(
			new Set(
				progress
					.filter((item) => ['completed', 'partial', 'reused'].includes(item.status))
					.map((item) => item.runId)
					.filter((id): id is number => id !== null)
			)
		);
		if (runIds.length === 0) {
			resultsLoading = false;
			return;
		}
		resultsLoading = true;
		resultsError = '';
		calibrationReport = null;
		calibrationError = '';
		scoreGridRows = [];
		scoreGridError = '';
		try {
			const runResults = await Promise.allSettled(runIds.map((runId) => predictionsApi.getRun(runId)));
			if (!resultRequests.isCurrent(requestId)) return;
			detailedRuns = runResults
				.filter((result): result is PromiseFulfilledResult<PredictionRun> => result.status === 'fulfilled')
				.map((result) => result.value);
			void loadCalibration(runIds, requestId);
			void loadScoreGrids(runIds, requestId);
			const restoredStrategyIds = Array.from(
				new Set(
					detailedRuns
						.map((run) => run.strategy_id)
						.filter((strategyId): strategyId is number => typeof strategyId === 'number')
				)
			);
			if (restoredRunIds) {
				runStrategyMap = Object.fromEntries(
					detailedRuns.map((run) => [run.id, run.strategy_id ?? 0])
				);
				progress = detailedRuns
					.filter((run) => typeof run.strategy_id === 'number')
					.map((run) => ({
						strategyId: run.strategy_id as number,
						status:
							run.status === 'completed' || run.status === 'partial' || run.status === 'failed'
								? run.status
								: run.status === 'running'
									? 'running'
									: 'failed',
						runId: run.id,
						matchesCount: run.matches_count,
						error: run.error
					}));
				if (restoredStrategyIds.length > 0) selectedStrategyIds = restoredStrategyIds;
			}
			const predictions = detailedRuns.flatMap((run) => run.model_predictions ?? []);
			const matchIds = Array.from(new Set(predictions.map((prediction) => prediction.match_id)));
			const matchResults = await Promise.allSettled(matchIds.map((matchId) => matchesApi.getMatch(matchId)));
			if (!resultRequests.isCurrent(requestId)) return;
			const matchMap = new SvelteMap<number, Match>();
			for (const result of matchResults) {
				if (result.status === 'fulfilled') matchMap.set(result.value.id, result.value);
			}
			candidates = detailedRuns.flatMap((run) => {
				const strategyId = runStrategyMap[run.id] ?? 0;
				const strategy = strategies.find((item) => item.id === strategyId);
				return (run.model_predictions ?? []).map((prediction) => {
					const match = matchMap.get(prediction.match_id);
					const outcome = selectModelOutcome(prediction);
					const quality = prediction.quality_report;
					const edge = typeof quality?.edge?.pick_edge_pct === 'number'
						? quality.edge.pick_edge_pct
						: outcome.odds && outcome.odds > 1
							? (outcome.probability * outcome.odds - 1) * 100
							: null;
					const marketProbability = typeof quality?.market?.probabilities?.[outcome.selection] === 'number'
						? quality.market.probabilities[outcome.selection]
						: outcome.odds && outcome.odds > 1
							? 1 / outcome.odds
							: null;
					const marketGap = typeof quality?.edge?.market_gap_pct === 'number'
						? quality.edge.market_gap_pct
						: marketProbability !== null
							? (outcome.probability - marketProbability) * 100
							: null;
					const reliability = quality?.reliability;
					return {
						id: prediction.id,
						runId: run.id,
						strategyId,
						strategyName: strategy?.name ?? `Strategia #${strategyId || '—'}`,
						model: prediction.model_type || run.model_type,
						matchId: prediction.match_id,
						match: match ? `${match.home_team} – ${match.away_team}` : `Meci #${prediction.match_id}`,
						league: match?.league ?? 'Ligă necunoscută',
						kickoff: match?.start_time ?? null,
						market: prediction.market,
						selection: outcome.selection,
						probability: outcome.probability,
						odds: outcome.odds,
						edge,
						marketProbability,
						marketGap,
						trainingMatches: typeof quality?.training?.total_matches === 'number' ? quality.training.total_matches : null,
						reliability: reliability?.label ?? 'neverificat',
						reliabilityScore:
							typeof reliability?.score === 'number' ? reliability.score : null,
						ticketEligible:
							typeof reliability?.is_ticket_eligible === 'boolean'
								? reliability.is_ticket_eligible
								: null,
						qualityReasons: reliability?.block_reasons ?? []
					} satisfies AnalysisCandidate;
				});
			});
			resetCandidateWindow();
			if (restoredRunIds) {
				const availableIds = new Set(candidates.map((candidate) => candidate.id));
				selectedPredictionIds = restoredPredictionIds.filter((id) => availableIds.has(id));
			}
			if (runResults.some((result) => result.status === 'rejected')) {
				resultsError = 'Unele run-uri nu au putut fi încărcate; rezultatele disponibile rămân vizibile.';
			}
		} catch (error) {
			if (!resultRequests.isCurrent(requestId)) return;
			resultsError = error instanceof ApiClientError ? error.message : 'Rezultatele nu au putut fi încărcate.';
		} finally {
			if (resultRequests.isCurrent(requestId)) resultsLoading = false;
		}
	}

	async function loadCalibration(runIds: number[], requestId: number) {
		calibrationLoading = true;
		calibrationError = '';
		try {
			const reports = await Promise.allSettled(
				runIds.map((runId) => predictionsApi.getCalibration(runId))
			);
			if (!resultRequests.isCurrent(requestId)) return;
			const available = reports.flatMap((report, index) =>
				report.status === 'fulfilled'
					? [{ runId: runIds[index], report: report.value }]
					: []
			);
			calibrationReport = {
				resolved_predictions: available.reduce(
					(total, item) => total + item.report.resolved_predictions,
					0
				),
				groups: available.flatMap((item) =>
					item.report.groups.map((group) => ({ ...group, source_run_id: item.runId }))
				)
			};
			if (available.length === 0 && reports.some((report) => report.status === 'rejected')) {
				calibrationError = 'Calibrarea este disponibilă doar pentru o parte dintre run-uri.';
			}
		} catch {
			if (!resultRequests.isCurrent(requestId)) return;
			calibrationReport = null;
			calibrationError = 'Calibrarea nu a putut fi încărcată.';
		} finally {
			if (resultRequests.isCurrent(requestId)) calibrationLoading = false;
		}
	}

	async function loadScoreGrids(runIds: number[], requestId: number) {
		scoreGridLoading = true;
		scoreGridError = '';
		try {
			const reports = await Promise.allSettled(
				runIds.map((runId) => predictionsApi.getScoreGrids(runId))
			);
			if (!resultRequests.isCurrent(requestId)) return;
			scoreGridRows = reports.flatMap((report, index) =>
				report.status === 'fulfilled'
					? report.value.items.map((item) => ({ ...item, source_run_id: runIds[index] }))
					: []
			);
			if (scoreGridRows.length === 0 && reports.some((report) => report.status === 'rejected')) {
				scoreGridError = 'Grilele de scor nu au putut fi încărcate pentru run-urile curente.';
			}
		} catch {
			if (!resultRequests.isCurrent(requestId)) return;
			scoreGridRows = [];
			scoreGridError = 'Grilele de scor nu au putut fi încărcate.';
		} finally {
			if (resultRequests.isCurrent(requestId)) scoreGridLoading = false;
		}
	}

	function togglePrediction(id: number) {
		const candidate = candidates.find((item) => item.id === id);
		if (!candidate || candidate.ticketEligible !== true || !candidate.odds || candidate.odds <= 1) return;
		selectedPredictionIds = selectedPredictionIds.includes(id)
			? selectedPredictionIds.filter((item) => item !== id)
			: [...selectedPredictionIds, id];
	}

	function selectVisiblePredictions() {
		const selectableIds = visibleCandidates
			.filter((candidate) => candidate.ticketEligible === true && candidate.odds && candidate.odds > 1)
			.map((candidate) => candidate.id);
		selectedPredictionIds = Array.from(
			new Set([...selectedPredictionIds, ...selectableIds])
		);
	}

	function clearPredictionSelection() {
		selectedPredictionIds = [];
	}

	function resetCandidateFilters() {
		resultSearch = '';
		resultStrategy = 'all';
		resultLeague = 'all';
		resultMarket = 'all';
		resultReliability = 'all';
		eligibleOnly = false;
		minEdge = '';
		minProbability = '';
		minMarketGap = '';
		resetCandidateWindow();
	}

	function resetCandidateWindow() {
		visibleCandidateLimit = 25;
	}

	function loadMoreCandidates() {
		visibleCandidateLimit = nextCandidateWindowSize(
			visibleCandidateLimit,
			filteredCandidates.length
		);
	}

	function addCandidateToBetslip(candidate: AnalysisCandidate) {
		if (candidate.ticketEligible !== true || !candidate.odds || candidate.odds <= 1) return;
		if (!selectedPredictionIds.includes(candidate.id)) {
			selectedPredictionIds = [...selectedPredictionIds, candidate.id];
		}
		betslip.addLeg(
			createBetslipLeg({
				matchId: candidate.matchId,
				modelPredictionId: candidate.id,
				matchName: candidate.match,
				market: candidate.market,
				selection: candidate.selection,
				odds: candidate.odds,
				league: candidate.league,
				source: 'prediction'
			})
		);
	}

	function addSelectedToBetslip() {
		for (const candidate of candidates.filter((item) => selectedPredictionIds.includes(item.id))) {
			addCandidateToBetslip(candidate);
		}
	}

	function statusLabel(status: StrategyProgress['status']): string {
		return (
			{
				idle: 'Pregătită',
				queued: 'În coadă',
				running: 'Rulează',
				completed: 'Finalizată',
				partial: 'Parțial',
				failed: 'Eșuată',
				reused: 'Run reutilizat',
				no_matches: 'Fără meciuri'
			} as Record<StrategyProgress['status'], string>
		)[status];
	}

	function statusVariant(
		status: StrategyProgress['status']
	): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
		if (status === 'completed') return 'success';
		if (status === 'failed') return 'danger';
		if (status === 'partial' || status === 'reused' || status === 'no_matches') return 'warning';
		if (status === 'running') return 'info';
		return 'neutral';
	}

	onMount(fetchInitialData);
</script>

<svelte:head>
	<title>Analiză | Bet</title>
	<meta
		name="description"
		content="Rulează toate strategiile rulabile pe setul de date pregătit și transferă rezultatele verificate către bilete."
	/>
</svelte:head>

<section class="workbench-page min-w-0 space-y-4 pb-52 sm:space-y-5 sm:pb-44 lg:space-y-6 lg:pb-12" transition:fade={{ duration: 180 }}>
	<header class="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-end sm:justify-between sm:pb-5">
		<div class="max-w-2xl">
			<p class="workbench-eyebrow"><span class="sm:hidden">Pasul 2 din 4</span><span class="hidden sm:inline">Pregătire → Analiză → Bilete</span></p>
			<h1 class="mt-1 text-3xl font-semibold tracking-tight text-foreground sm:mt-2 sm:text-4xl">Analiză</h1>
			<p class="mt-2 text-sm leading-5 text-muted-foreground sm:mt-3 sm:text-base sm:leading-6">Rulează toate strategiile rulabile pe setul pregătit și păstrează sursa exactă până la bilete.</p>
		</div>
		<a href="/settings/strategies" class="inline-flex min-h-11 w-fit items-center gap-2 border border-border bg-card px-3 text-sm font-medium text-foreground transition-colors hover:border-football-gold/60 hover:text-football-gold">
			<Settings2 class="size-4" aria-hidden="true" />
			Configurează strategii
		</a>
	</header>

	<nav aria-label="Progresul fluxului" class="grid grid-cols-4 border border-border bg-card">
		<a href="/prepare" class="flex min-h-12 items-center justify-center gap-1.5 border-r border-border px-1 text-[11px] font-medium text-football-green sm:min-h-14 sm:justify-start sm:gap-2 sm:px-3 sm:text-sm">
			<CheckCircle2 class="size-4 shrink-0" aria-hidden="true" />
			<span class="sm:hidden">Date</span><span class="hidden sm:inline">Pregătire</span>
		</a>
		<div aria-current="step" class="flex min-h-12 items-center justify-center gap-1.5 border-r border-football-gold bg-football-gold/10 px-1 text-[11px] font-semibold text-foreground sm:min-h-14 sm:justify-start sm:gap-2 sm:px-3 sm:text-sm">
			<BarChart3 class="size-4 shrink-0 text-football-gold" aria-hidden="true" />
			<span>Analiză</span>
		</div>
		{#if successfulRunIds.length > 0}
			<a href={ticketsUrl} class="flex min-h-12 items-center justify-center gap-1.5 border-r border-border px-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground sm:min-h-14 sm:justify-start sm:gap-2 sm:px-3 sm:text-sm">
				<Ticket class="size-4 shrink-0" aria-hidden="true" />
				<span>Bilete</span>
			</a>
		{:else}
			<span aria-disabled="true" class="flex min-h-12 cursor-not-allowed items-center justify-center gap-1.5 border-r border-border px-1 text-[11px] font-medium text-muted-foreground/70 sm:min-h-14 sm:justify-start sm:gap-2 sm:px-3 sm:text-sm">
				<Ticket class="size-4 shrink-0" aria-hidden="true" />
				<span>Bilete</span>
			</span>
		{/if}
		<a href="/monitoring" class="flex min-h-12 items-center justify-center gap-1.5 px-1 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground sm:min-h-14 sm:justify-start sm:gap-2 sm:px-3 sm:text-sm">
			<Clock3 class="size-4 shrink-0" aria-hidden="true" />
			<span class="sm:hidden">Monitor</span><span class="hidden sm:inline">Monitorizare</span>
		</a>
	</nav>

	{#if loading}
		<div class="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
			<Skeleton class="h-[32rem] w-full" />
			<Skeleton class="h-80 w-full" />
		</div>
	{:else if loadError}
		<Card variant="prediction">
			<div role="alert" class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
				<div class="flex gap-3">
					<XCircle class="mt-0.5 size-5 shrink-0 text-football-red" aria-hidden="true" />
					<div>
						<h2 class="font-semibold text-foreground">Analiza nu poate fi configurată</h2>
						<p class="mt-1 text-sm text-muted-foreground">{loadError}</p>
					</div>
				</div>
				<Button variant="secondary" onclick={fetchInitialData}>Reîncearcă</Button>
			</div>
		</Card>
	{:else}
		<div class="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(19rem,0.85fr)]">
			<div class="min-w-0 space-y-6">
				<Card variant="data">
					<div class="space-y-4">
						<h2 class="text-lg font-semibold text-foreground">1. Date pregătite</h2>
						{#if selectedReadiness && selectedDataset}
							<Select
								label="Set de date sursă"
								name="analysis-dataset"
								options={datasetItems.map((item) => ({ value: String(item.dataset.id), label: datasetLabel(item) }))}
								bind:value={selectedDatasetId}
								onchange={changeDataset}
								disabled={batchRunning}
								class="min-h-11"
							/>
						{:else}
							<div class="flex flex-col gap-4 border border-football-gold/40 bg-football-gold/10 p-4 sm:flex-row sm:items-center sm:justify-between" role="status">
								<div class="flex gap-3">
									<AlertTriangle class="mt-0.5 size-5 shrink-0 text-football-gold" aria-hidden="true" />
									<div>
										<h3 class="font-semibold text-foreground">Nu există un set de date pregătit</h3>
										<p class="mt-1 text-sm leading-6 text-muted-foreground">
											{datasetItems.length === 0
												? 'Nu a fost găsit niciun set de date disponibil.'
												: datasetItems.length === 1
													? 'Setul găsit nu este utilizabil acum.'
													: `Cele ${datasetItems.length} seturi găsite nu sunt utilizabile acum.`}
										</p>
									</div>
								</div>
								<a href="/prepare" class="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 bg-primary px-4 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90">Pregătește datele <ArrowRight class="size-4" aria-hidden="true" /></a>
							</div>
							{#if datasetItems.length > 0}
								<details class="border border-border bg-muted/20">
									<summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-3 text-sm font-medium text-foreground"><span>Vezi seturile indisponibile ({datasetItems.length})</span><ChevronDown class="size-4 text-muted-foreground" aria-hidden="true" /></summary>
									<ul class="space-y-2 border-t border-border p-3">
										{#each datasetItems as item (item.dataset.id)}
											<li class="flex items-center justify-between gap-3 text-sm"><span class="font-mono text-foreground">#{item.dataset.id} · {item.dataset.matches_count ?? 0} meciuri</span><Badge variant="warning">{item.jobStatus ?? 'Neverificat'}</Badge></li>
										{/each}
									</ul>
								</details>
							{/if}
						{/if}

						{#if selectedReadiness && selectedDataset}
							<div class="grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
								<div class="bg-card p-3">
									<p class="text-xs text-muted-foreground">Sursă exactă</p>
									<p class="mt-1 font-mono text-sm text-foreground">Set #{selectedDataset.id}</p>
									<p class="mt-1 font-mono text-xs text-muted-foreground">Job #{selectedReadiness.jobId ?? '—'}</p>
								</div>
								<div class="bg-card p-3">
									<p class="text-xs text-muted-foreground">Meciuri țintă</p>
									<p class="mt-1 font-mono text-xl text-foreground">{selectedDataset.matches_count ?? 0}</p>
									<p class="mt-1 text-xs text-muted-foreground">rezolvate exact de backend</p>
								</div>
								<div class="bg-card p-3">
									<p class="text-xs text-muted-foreground">Acoperire ligi</p>
									<p class="mt-1 font-mono text-xl text-foreground">{coverage.leagues.length || '—'}</p>
					<p class="mt-1 truncate text-xs text-muted-foreground">{datasetCountryLabel(selectedDataset)}</p>
								</div>
								<div class="bg-card p-3">
									<p class="text-xs text-muted-foreground">Pregătit la</p>
									<p class="mt-1 text-sm text-foreground">{formatDateTime(selectedDataset.created_at)}</p>
									<p class="mt-1 text-xs text-muted-foreground">{coverage.dateFrom ? `${formatDateTime(coverage.dateFrom)} → ${formatDateTime(coverage.dateTo)}` : 'Interval indisponibil'}</p>
								</div>
							</div>

							{#if selectedDatasetReady}
								<div class="flex gap-3 border border-football-green/30 bg-football-green/10 p-3 text-sm">
									<ShieldCheck class="mt-0.5 size-5 shrink-0 text-football-green" aria-hidden="true" />
									<div>
										<p class="font-medium text-foreground">Set de date pregătit pentru analiză</p>
										<p class="mt-1 text-muted-foreground">Jobul sursă este finalizat. Fiecare model validează separat istoricul de antrenare; o strategie poate eșua fără să invalideze rezultatele celorlalte.</p>
									</div>
								</div>
							{:else}
								<div role="alert" class="flex flex-col gap-3 border border-football-gold/40 bg-football-gold/10 p-3 sm:flex-row sm:items-center sm:justify-between">
									<div class="flex gap-3 text-sm">
										<AlertTriangle class="mt-0.5 size-5 shrink-0 text-football-gold" aria-hidden="true" />
										<div>
										<p class="font-medium text-foreground">Setul de date nu este gata</p>
											<p class="mt-1 text-muted-foreground">Jobul sursă este {selectedReadiness.jobStatus ?? 'neverificat'}. Nu îl folosim automat pentru predicții.</p>
										</div>
									</div>
									<a href="/prepare" class="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 border border-border bg-card px-3 text-sm font-medium text-foreground hover:border-football-blue/60">
									Revino la Pregătire <ArrowRight class="size-4" aria-hidden="true" />
									</a>
								</div>
							{/if}

							{#if coverage.leagues.length > 0}
								<details class="border border-border bg-muted/20">
									<summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-3 text-sm font-medium text-foreground">
										<span>{coverage.leagues.length} ligi incluse în setul de date</span>
										<ChevronDown class="size-4 text-muted-foreground" aria-hidden="true" />
									</summary>
									<div class="flex flex-wrap gap-2 border-t border-border p-3">
										{#each coverage.leagues as league (league)}
											<Badge variant="info">{league}</Badge>
										{/each}
									</div>
								</details>
							{/if}
						{/if}
					</div>
				</Card>

				<Card variant="prediction">
					<div class="space-y-4">
						<h2 class="text-lg font-semibold text-foreground">2. Strategii</h2>
						<div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
							<div class="relative min-w-0 flex-1">
								<Search class="pointer-events-none absolute left-3 top-[2.35rem] size-4 text-muted-foreground" aria-hidden="true" />
								<Input label="Caută în catalog" name="strategy-search" placeholder="Nume sau model" bind:value={strategySearch} class="min-h-11 pl-9" />
							</div>
							<div class="flex gap-2">
								<Button class="min-h-11" variant="secondary" size="sm" onclick={selectAllRunnable} disabled={allRunnableSelected || batchRunning}>Selectează toate rulabile</Button>
								<Button class="min-h-11" variant="ghost" size="sm" onclick={clearStrategies} disabled={selectedStrategyIds.length === 0 || batchRunning}>Golește</Button>
							</div>
						</div>

						<div class="flex flex-wrap items-center gap-2 text-sm">
							<Badge variant="success">{strategyCountLabel(selectedRunnableCount)} {selectedRunnableCount === 1 ? 'selectată' : 'selectate'}</Badge>
							<span class="text-muted-foreground">din {strategyCountLabel(runnableStrategies.length)} {runnableStrategies.length === 1 ? 'rulabilă' : 'rulabile'}</span>
							{#if unavailableStrategies.length > 0}
								<Button class="min-h-11" variant="ghost" size="sm" onclick={() => (showUnavailableStrategies = !showUnavailableStrategies)}>
									{showUnavailableStrategies ? 'Ascunde' : 'Arată'} {strategyCountLabel(unavailableStrategies.length)} {unavailableStrategies.length === 1 ? 'indisponibilă' : 'indisponibile'}
								</Button>
							{/if}
						</div>

						<div class="space-y-2 border border-border bg-muted/10 p-2 lg:max-h-[28rem] lg:overflow-y-auto" role="group" aria-label="Catalog strategii">
							{#each filteredStrategies as strategy (strategy.id)}
								<label class="flex min-h-16 items-start gap-3 border border-border bg-card p-3 transition-colors has-[:checked]:border-football-gold/60 has-[:checked]:bg-football-gold/5 has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60">
									<input
										type="checkbox"
										class="mt-1 size-4 shrink-0 accent-[var(--football-gold)]"
										checked={selectedStrategyIds.includes(strategy.id)}
									disabled={!isStrategyRunnable(strategy) || batchRunning}
										onchange={() => toggleStrategy(strategy.id)}
									/>
									<span class="min-w-0 flex-1">
										<span class="flex flex-wrap items-center gap-2">
										<span class="font-medium text-foreground">{strategy.name}</span>
										<Badge variant={isStrategyRunnable(strategy) ? 'success' : 'neutral'}>{isStrategyRunnable(strategy) ? 'Rulabilă' : 'Indisponibilă'}</Badge>
									</span>
									<span class="mt-1 block text-sm leading-5 text-muted-foreground">{strategy.description || 'Fără descriere'} · <span class="font-mono text-xs">{strategy.model_type}</span></span>
									{#if !isStrategyRunnable(strategy)}<span class="mt-1 block text-sm leading-5 text-football-gold">{strategyUnavailableReason(strategy)} <a href="/settings/strategies" class="font-medium underline underline-offset-2">Deschide configurarea</a>.</span>{/if}
									</span>
								</label>
							{:else}
								<p class="p-4 text-center text-sm text-muted-foreground">Nicio strategie nu corespunde căutării.</p>
							{/each}
						</div>
					</div>
				</Card>

				<Card variant="prediction">
					<div class="space-y-4">
						<h2 class="text-lg font-semibold text-foreground">3. Piețe și opțiuni</h2>
						<fieldset>
							<legend class="text-sm font-medium text-foreground">Piețe analizate</legend>
							<div class="mt-2 grid gap-2 md:grid-cols-3">
								{#each marketOptions as market (market.id)}
									<label class="flex min-h-16 items-start gap-3 border border-border bg-card p-3 transition-colors has-[:checked]:border-football-gold/60 has-[:checked]:bg-football-gold/5">
										<input type="checkbox" class="mt-1 size-4 accent-[var(--football-gold)]" checked={selectedMarkets.includes(market.id)} disabled={batchRunning || resultsLoading} onchange={() => toggleMarket(market.id)} />
										<span><span class="block text-sm font-medium text-foreground">{market.label}</span><span class="mt-1 block text-xs text-muted-foreground">{market.description}</span></span>
									</label>
								{/each}
							</div>
						</fieldset>

						<details class="border border-border bg-muted/20">
							<summary class="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-3 text-sm font-medium text-foreground">
								<span class="flex items-center gap-2"><Settings2 class="size-4 text-muted-foreground" aria-hidden="true" /> Opțiuni avansate</span>
								<ChevronDown class="size-4 text-muted-foreground" aria-hidden="true" />
							</summary>
							<div class="space-y-4 border-t border-border p-3">
								<label class="flex min-h-11 items-start gap-3">
									<input type="checkbox" class="mt-1 size-4 accent-[var(--football-green)]" bind:checked={avoidReprediction} disabled={batchRunning || resultsLoading} />
									<span><span class="block text-sm font-medium text-foreground">Reutilizează run-uri identice finalizate</span><span class="mt-1 block text-xs text-muted-foreground">Evită recalcularea când datasetul, strategia și piețele sunt identice.</span></span>
								</label>
								<div class="grid gap-3 sm:grid-cols-2">
									<Input class="min-h-11" label="De la (opțional)" name="analysis-date-from" type="date" bind:value={dateFrom} disabled={batchRunning || resultsLoading} />
									<Input class="min-h-11" label="Până la (opțional)" name="analysis-date-to" type="date" bind:value={dateTo} disabled={batchRunning || resultsLoading} />
								</div>
								<p class="text-sm leading-5 text-muted-foreground">Setul de date rămâne sursa exactă a meciurilor. Filtrele sunt trimise ca metadate suplimentare și nu schimbă proveniența setului.</p>
								<a href="/monitoring" class="inline-flex min-h-11 items-center gap-2 text-sm font-medium text-football-blue hover:text-football-gold"><Clock3 class="size-4" aria-hidden="true" /> Configurează automatizarea în Monitorizare</a>
							</div>
						</details>
					</div>
				</Card>
			</div>

			<aside class="hidden min-w-0 lg:sticky lg:top-4 lg:block lg:self-start">
				<Card variant="active">
					<div class="space-y-4 text-sm">
						<h2 class="text-lg font-semibold text-foreground">Pre-verificare</h2>
						<div class="flex items-start justify-between gap-3"><span class="text-muted-foreground">Set de date</span><span class="font-mono text-right text-foreground">{selectedDataset ? `#${selectedDataset.id}` : '—'}</span></div>
						<div class="flex items-start justify-between gap-3"><span class="text-muted-foreground">Job sursă</span><span class="font-mono text-right text-foreground">{selectedReadiness?.jobId ? `#${selectedReadiness.jobId}` : '—'}</span></div>
						<div class="flex items-start justify-between gap-3"><span class="text-muted-foreground">Meciuri</span><span class="font-mono text-right text-foreground">{selectedDataset?.matches_count ?? 0}</span></div>
						<div class="flex items-start justify-between gap-3"><span class="text-muted-foreground">Strategii</span><span class="font-mono text-right text-foreground">{selectedStrategyIds.length}</span></div>
						<div class="flex items-start justify-between gap-3"><span class="text-muted-foreground">Piețe</span><span class="font-mono text-right text-foreground">{selectedMarkets.length}</span></div>
						<div class="border-t border-border pt-4">
							{#if analysisCanRun}
								<div class="flex gap-2 text-football-green"><CheckCircle2 class="mt-0.5 size-4 shrink-0" aria-hidden="true" /><span>Configurația este gata pentru {strategyCountLabel(selectedStrategyIds.length)}.</span></div>
							{:else}
								<div class="flex gap-2 text-football-gold"><AlertTriangle class="mt-0.5 size-4 shrink-0" aria-hidden="true" /><span>{batchRunning || resultsLoading ? 'Analiza și rezultatele sunt în curs de procesare.' : preflightReason}</span></div>
							{/if}
						</div>
						<Button fullWidth size="lg" onclick={runAnalysis} disabled={!analysisCanRun}>
								{#if batchRunning || resultsLoading}<Loader2 class="size-4 animate-spin" aria-hidden="true" /> Procesează rezultatele{:else}<Play class="size-4" aria-hidden="true" /> Rulează analiza pentru {strategyCountLabel(selectedStrategyIds.length)}{/if}
						</Button>
						<p class="text-sm leading-5 text-muted-foreground">Rezultatele finalizate rămân vizibile dacă o strategie eșuează.</p>
					</div>
				</Card>
			</aside>
		</div>

		{#if progressRows.length > 0 && (batchRunning || terminalProgress.length > 0)}
			<Card variant="prediction">
				<div class="space-y-3">
					<h2 class="text-lg font-semibold text-foreground">Progres pe strategie</h2>
					<div class="h-2 overflow-hidden bg-muted" aria-label={`Progres analiză ${batchProgressPercent}%`} role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={batchProgressPercent}>
						<div class="h-full bg-football-gold transition-[width] duration-200" style={`width: ${batchProgressPercent}%`}></div>
					</div>
					<p class="text-sm text-muted-foreground" aria-live="polite">{terminalProgress.length} din {strategyCountLabel(selectedStrategyIds.length)} {selectedStrategyIds.length === 1 ? 'are' : 'au'} status terminal.</p>
					<ul class="grid gap-2 lg:grid-cols-2" aria-label="Starea strategiilor">
						{#each progressRows as row (row.strategy.id)}
							<li class="border border-border bg-muted/20 p-3">
								<div class="flex items-start justify-between gap-2">
									<div class="min-w-0"><p class="truncate text-sm font-medium text-foreground">{row.strategy.name}</p><p class="mt-1 font-mono text-xs text-muted-foreground">{row.strategy.model_type}{row.progress.runId ? ` · run #${row.progress.runId}` : ''}</p></div>
									<Badge variant={statusVariant(row.progress.status)}>{statusLabel(row.progress.status)}</Badge>
								</div>
								{#if row.progress.error}<p class="mt-2 text-sm leading-5 text-football-red">{row.progress.error}</p>{/if}
								{#if row.progress.matchesCount > 0}<p class="mt-2 text-sm text-muted-foreground">{row.progress.matchesCount} meciuri procesate</p>{/if}
							</li>
						{/each}
					</ul>
					{#if failedIds.length > 0 && !batchRunning && !resultsLoading}<Button variant="secondary" onclick={retryFailed}><RefreshCw class="size-4" aria-hidden="true" /> Reîncearcă {strategyCountLabel(failedIds.length)} {failedIds.length === 1 ? 'eșuată' : 'eșuate'}</Button>{/if}
				</div>
			</Card>
		{/if}

		{#if batchError}
			<div role="alert" class="flex gap-3 border border-football-red/40 bg-football-red/10 p-3 text-sm text-foreground"><XCircle class="mt-0.5 size-5 shrink-0 text-football-red" aria-hidden="true" /><span>{batchError}</span></div>
		{/if}
		{#if batchNotice}
			<div class="flex gap-3 border border-football-blue/30 bg-football-blue/10 p-3 text-sm text-foreground" aria-live="polite"><Link2 class="mt-0.5 size-5 shrink-0 text-football-blue" aria-hidden="true" /><span>{batchNotice}</span></div>
		{/if}
		{#if latestResolution && latestResolution.dataset_records_count !== undefined}
			<div class="grid gap-px border border-border bg-border sm:grid-cols-3">
				<div class="bg-card p-3"><p class="text-xs text-muted-foreground">Înregistrări în set</p><p class="mt-1 font-mono text-lg text-foreground">{latestResolution.dataset_records_count}</p></div>
				<div class="bg-card p-3"><p class="text-xs text-muted-foreground">Meciuri rezolvate</p><p class="mt-1 font-mono text-lg text-football-green">{latestResolution.resolved_records_count ?? 0}</p></div>
				<div class="bg-card p-3"><p class="text-xs text-muted-foreground">Nerezolvate</p><p class="mt-1 font-mono text-lg {latestResolution.unresolved_records_count ? 'text-football-gold' : 'text-foreground'}">{latestResolution.unresolved_records_count ?? 0}</p></div>
			</div>
		{/if}

		{#if terminalProgress.length > 0 || resultsLoading || candidates.length > 0}
			<section aria-labelledby="analysis-results-heading" class="space-y-4">
				<div class="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
					<div>
						<p class="workbench-eyebrow">Rezultatul curent</p>
						<h2 id="analysis-results-heading" class="mt-2 font-sport text-2xl font-bold text-foreground">Revizuiește candidații</h2>
					</div>
					{#if successfulRunIds.length > 0}<Badge variant="info">{runCountLabel(successfulRunIds.length)} · {successfulRunIds.map((id) => `#${id}`).join(', ')}</Badge>{/if}
				</div>

				<div class="grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-6">
					{#each [
						['Finalizate', completedCount, 'text-football-green'],
						['Parțiale', partialCount, 'text-football-gold'],
						['Eșuate', failedIds.length, 'text-football-red'],
						['Candidați', candidates.length, 'text-foreground'],
						['Eligibili bilete', eligibleCandidateCount, 'text-football-green'],
						['Cu avertismente', warningCandidateCount, 'text-football-gold']
					] as metric (metric[0])}
						<div class="bg-card p-3"><p class="text-xs text-muted-foreground">{metric[0]}</p><p class={`mt-1 font-mono text-xl ${metric[2]}`}>{metric[1]}</p></div>
					{/each}
				</div>
				<div class="grid gap-2 border border-border bg-card p-3 text-xs sm:grid-cols-5" aria-label="Proveniența fluxului de analiză">
					<div><p class="font-semibold text-football-green">1 · Date</p><p class="mt-1 text-muted-foreground">Set #{selectedDataset?.id ?? '—'} · {selectedDatasetCountry}</p></div>
					<div><p class="font-semibold text-football-green">2 · Run-uri</p><p class="mt-1 text-muted-foreground">{successfulRunIds.length} finalizate</p></div>
					<div><p class="font-semibold text-football-green">3 · Predicții</p><p class="mt-1 text-muted-foreground">{candidates.length} candidați</p></div>
					<div><p class="font-semibold text-football-green">4 · Filtrare</p><p class="mt-1 text-muted-foreground">{eligibleCandidateCount} eligibili · {warningCandidateCount} avertismente</p></div>
					<div><p class="font-semibold text-football-gold">5 · Bilete</p><p class="mt-1 text-muted-foreground">{selectedPredictionIds.length > 0 ? `${selectedPredictionIds.length} selectați` : 'alege selecții'}</p></div>
				</div>

				<RiskLadder
					title="Gradaj de expunere pentru bilete"
					probabilities={eligibleMatchProbabilities}
					eligibleCandidates={eligibleCandidateCount}
					uniqueMatches={eligibleUniqueMatchCount}
				/>

				{#if candidates.length > 0}
					<StrategyComparison candidates={candidates} />
				{/if}

				<AnalysisModelEvidence
					calibration={calibrationReport}
					{calibrationLoading}
					{calibrationError}
					scoreRows={scoreGridRows}
					{scoreGridLoading}
					{scoreGridError}
				/>

				{#if resultsLoading}
					<Skeleton class="h-64 w-full" />
				{:else}
					{#if resultsError}<div role="alert" class="border border-football-gold/40 bg-football-gold/10 p-3 text-sm text-foreground">{resultsError}</div>{/if}
					<Card variant="prediction">
						<div class="space-y-4">
							<div class="grid gap-3 md:grid-cols-2 xl:grid-cols-8">
								<div class="relative md:col-span-2 xl:col-span-2"><label for="result-search" class="mb-1.5 block text-sm font-medium text-foreground">Caută echipă sau ligă</label><Search class="pointer-events-none absolute left-3 top-[2.45rem] size-4 text-muted-foreground" aria-hidden="true" /><input id="result-search" class="min-h-11 w-full border border-input bg-background pl-9 pr-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring" placeholder="Echipă sau ligă" bind:value={resultSearch} oninput={resetCandidateWindow} /></div>
								<Select class="min-h-11" label="Strategie" name="result-strategy" options={candidateStrategyOptions} bind:value={resultStrategy} onchange={resetCandidateWindow} />
								<Select class="min-h-11" label="Ligă" name="result-league" options={candidateLeagueOptions} bind:value={resultLeague} onchange={resetCandidateWindow} />
								<Select class="min-h-11" label="Piață" name="result-market" options={candidateMarketOptions} bind:value={resultMarket} onchange={resetCandidateWindow} />
								<Select class="min-h-11" label="Fiabilitate" name="result-reliability" options={candidateReliabilityOptions} bind:value={resultReliability} onchange={resetCandidateWindow} />
								<Input class="min-h-11" label="Prob. model min %" name="minimum-probability" type="number" min="0" max="100" step="0.1" placeholder="Oricare" bind:value={minProbability} oninput={resetCandidateWindow} />
								<Input class="min-h-11" label="Gap piață min %" name="minimum-market-gap" type="number" step="0.1" placeholder="Oricare" bind:value={minMarketGap} oninput={resetCandidateWindow} />
							</div>
							<div class="flex flex-col gap-3 border-t border-border pt-3 sm:flex-row sm:items-end sm:justify-between">
								<div class="flex flex-col gap-3 sm:flex-row sm:items-center">
									<div class="w-full sm:w-36"><Input class="min-h-11" label="EV minim %" name="minimum-edge" type="number" step="0.1" placeholder="Oricare" bind:value={minEdge} oninput={resetCandidateWindow} /></div>
									<label class="flex min-h-11 items-center gap-2 text-sm text-foreground"><input type="checkbox" class="size-4 accent-[var(--football-green)]" bind:checked={eligibleOnly} onchange={resetCandidateWindow} /> Doar eligibili</label>
								</div>
								<div class="flex flex-wrap gap-2"><Button class="min-h-11" variant="secondary" size="sm" onclick={selectVisiblePredictions} disabled={visibleCandidates.length === 0}>Selectează afișate ({visibleCandidates.length})</Button><Button class="min-h-11" variant="ghost" size="sm" onclick={clearPredictionSelection} disabled={selectedPredictionIds.length === 0}>Golește selecția</Button><Button class="min-h-11" variant="ghost" size="sm" onclick={resetCandidateFilters} disabled={!candidateFiltersActive}>Resetează filtrele</Button></div>
							</div>
							<p class="border-l-2 border-football-blue pl-3 text-xs leading-5 text-muted-foreground">Model p = probabilitatea estimată de model · Piață p = probabilitatea de piață normalizată când există · EV = randamentul așteptat al selecției (p × cotă − 1), nu garanție de câștig.</p>

							{#if filteredCandidates.length === 0}
								<div class="border border-dashed border-border p-8 text-center"><Layers3 class="mx-auto size-7 text-muted-foreground" aria-hidden="true" /><p class="mt-3 font-medium text-foreground">Nu există candidați pentru filtrele curente</p><p class="mt-1 text-sm text-muted-foreground">Păstrează rezultatele strategiilor și relaxează filtrele de revizuire.</p></div>
							{:else}
								<div class="hidden overflow-x-auto border border-border lg:block">
									<table class="w-full min-w-[980px] border-collapse text-left text-sm">
										<caption class="sr-only">Candidați rezultați din analiza curentă</caption>
										<thead class="sticky top-0 bg-muted"><tr><th class="w-12 p-3"><span class="sr-only">Selectează</span></th><th class="p-3 font-medium">Meci</th><th class="p-3 font-medium">Strategie</th><th class="p-3 font-medium">Piață / selecție</th><th class="p-3 text-right font-medium">Model p</th><th class="p-3 text-right font-medium">Piață p</th><th class="p-3 text-right font-medium">Cotă</th><th class="p-3 text-right font-medium">EV</th><th class="p-3 font-medium">Calitate</th><th class="p-3"><span class="sr-only">Acțiune</span></th></tr></thead>
										<tbody class="divide-y divide-border">
										{#each visibleCandidates as candidate (candidate.id)}
											<tr class="bg-card align-top hover:bg-muted/30">
												<td class="p-1.5"><label class="flex size-11 items-center justify-center"><input aria-label={`Selectează ${candidate.match}`} type="checkbox" class="size-5 accent-[var(--football-green)]" checked={selectedPredictionIds.includes(candidate.id)} disabled={candidate.ticketEligible !== true || !candidate.odds || candidate.odds <= 1} onchange={() => togglePrediction(candidate.id)} /></label></td>
												<td class="p-3"><p class="font-medium text-foreground">{candidate.match}</p><p class="mt-1 text-xs text-muted-foreground">{candidate.league} · {formatDateTime(candidate.kickoff)}</p></td>
												<td class="p-3"><p class="text-foreground">{candidate.strategyName}</p><p class="mt-1 font-mono text-xs text-muted-foreground">{candidate.model} · run #{candidate.runId}</p></td>
												<td class="p-3"><p class="text-foreground">{marketLabel(candidate.market)}</p><p class="mt-1 font-medium text-football-gold">{candidate.selection}</p></td>
														<td class="p-3 text-right font-mono text-foreground">{formatProbability(candidate.probability)}</td><td class="p-3 text-right font-mono text-muted-foreground">{candidate.marketProbability === null ? '—' : formatProbability(candidate.marketProbability)}</td><td class="p-3 text-right font-mono text-foreground">{candidate.odds?.toFixed(2) ?? '—'}</td><td class="p-3 text-right font-mono {candidate.edge !== null && candidate.edge > 0 ? 'text-football-green' : 'text-muted-foreground'}">{formatPercent(candidate.edge)}</td>
												<td class="p-3"><div class="flex flex-wrap gap-1"><Badge variant={candidate.ticketEligible ? 'success' : candidate.ticketEligible === false ? 'warning' : 'neutral'}>{candidate.ticketEligible ? 'Eligibil' : candidate.ticketEligible === false ? 'Blocat' : 'Neverificat'}</Badge><Badge variant="neutral">{reliabilityLabel(candidate.reliability)}</Badge></div>{#if candidate.qualityReasons.length > 0}<p class="mt-2 max-w-52 text-xs leading-5 text-muted-foreground">{candidate.qualityReasons.join(' · ')}</p>{/if}</td>
														<td class="p-3"><Button class="min-h-11" size="sm" variant="ghost" onclick={() => addCandidateToBetslip(candidate)} disabled={candidate.ticketEligible !== true || !candidate.odds || candidate.odds <= 1}>Adaugă</Button></td>
											</tr>
										{/each}
										</tbody>
									</table>
								</div>

								<div class="space-y-3 lg:hidden">
									{#each visibleCandidates as candidate (candidate.id)}
										<article class="border border-border bg-card p-4">
											<div class="flex items-start gap-2">
												<label class="flex size-11 shrink-0 items-center justify-center"><input aria-label={`Selectează ${candidate.match}`} type="checkbox" class="size-5 accent-[var(--football-green)]" checked={selectedPredictionIds.includes(candidate.id)} disabled={candidate.ticketEligible !== true || !candidate.odds || candidate.odds <= 1} onchange={() => togglePrediction(candidate.id)} /></label>
												<div class="min-w-0 flex-1"><h3 class="font-medium text-foreground">{candidate.match}</h3><p class="mt-1 text-sm text-muted-foreground">{candidate.league} · {formatDateTime(candidate.kickoff)}</p></div>
											</div>
											<div class="mt-3 flex flex-wrap gap-1"><Badge variant={candidate.ticketEligible ? 'success' : candidate.ticketEligible === false ? 'warning' : 'neutral'}>{candidate.ticketEligible ? 'Eligibil' : candidate.ticketEligible === false ? 'Blocat' : 'Neverificat'}</Badge><Badge variant="neutral">{reliabilityLabel(candidate.reliability)}{candidate.reliabilityScore !== null ? ` · ${candidate.reliabilityScore.toFixed(0)}` : ''}</Badge></div>
													<div class="mt-4 grid grid-cols-2 gap-3 text-sm"><div><p class="text-xs text-muted-foreground">Strategie / run</p><p class="mt-1 text-foreground">{candidate.strategyName}</p><p class="mt-1 font-mono text-xs text-muted-foreground">{candidate.model} · run #{candidate.runId}</p></div><div><p class="text-xs text-muted-foreground">Piață</p><p class="mt-1 text-foreground">{marketLabel(candidate.market)} · <span class="text-football-gold">{candidate.selection}</span></p></div><div><p class="text-xs text-muted-foreground">Probabilitate model</p><p class="mt-1 font-mono text-foreground">{formatProbability(candidate.probability)}</p><p class="mt-1 text-xs text-muted-foreground">piață: {candidate.marketProbability === null ? '—' : formatProbability(candidate.marketProbability)} · gap {formatPercent(candidate.marketGap)}</p></div><div><p class="text-xs text-muted-foreground">Cotă / EV</p><p class="mt-1 font-mono text-foreground">{candidate.odds?.toFixed(2) ?? '—'} · {formatPercent(candidate.edge)}</p><p class="mt-1 text-xs text-muted-foreground">istoric: {candidate.trainingMatches ?? '—'} meciuri</p></div></div>
											{#if candidate.qualityReasons.length > 0}<p class="mt-3 border-l-2 border-football-gold pl-3 text-sm leading-5 text-muted-foreground">{candidate.qualityReasons.join(' · ')}</p>{/if}
											<Button class="mt-4" fullWidth variant="secondary" onclick={() => addCandidateToBetslip(candidate)} disabled={candidate.ticketEligible !== true || !candidate.odds || candidate.odds <= 1}>Adaugă în slip</Button>
										</article>
									{/each}
								</div>
								<div class="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between" aria-live="polite"><p class="text-sm text-muted-foreground">Afișate {visibleCandidates.length} din {filteredCandidates.length} rezultate · {selectedPredictionIds.length} selectate în total</p>{#if visibleCandidates.length < filteredCandidates.length}<Button variant="secondary" onclick={loadMoreCandidates}>Încarcă încă {Math.min(25, filteredCandidates.length - visibleCandidates.length)}</Button>{/if}</div>
							{/if}
						</div>
					</Card>
				{/if}
			</section>
		{/if}

		<details class="border border-border bg-card">
			<summary class="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 text-sm font-medium text-foreground"><span>{recentRuns.length === 1 ? '1 run recent' : `${recentRuns.length} run-uri recente`}</span><ChevronDown class="size-4 text-muted-foreground" aria-hidden="true" /></summary>
			<div class="grid gap-2 border-t border-border p-3 md:grid-cols-2">
				{#each recentRuns as run (run.id)}
					<div class="flex items-start justify-between gap-3 border border-border bg-muted/20 p-3"><div><p class="font-mono text-sm text-foreground">Run #{run.id}</p><p class="mt-1 text-xs text-muted-foreground">{run.model_type} · {run.matches_count} meciuri · {formatDateTime(run.created_at)}</p></div><Badge variant={run.status === 'completed' ? 'success' : run.status === 'failed' ? 'danger' : 'warning'}>{run.status}</Badge></div>
				{:else}
					<p class="p-3 text-sm text-muted-foreground">Nu există run-uri recente.</p>
				{/each}
			</div>
		</details>
	{/if}

	{#if !loading && !loadError && successfulRunIds.length === 0}
		<div class="mobile-above-nav fixed inset-x-3 z-30 border border-football-gold/40 bg-background/95 p-3 shadow-2xl backdrop-blur sm:inset-x-4 lg:hidden">
			<div class="mx-auto grid max-w-4xl grid-cols-[minmax(0,1fr)_auto] items-center gap-2 sm:flex sm:justify-between sm:gap-4">
				<div class="min-w-0"><p class="text-sm font-semibold leading-5 text-foreground">{selectedDataset ? `Set #${selectedDataset.id}` : 'Set nepregătit'} · {strategyCountLabel(selectedStrategyIds.length)} · {selectedMarkets.length} {selectedMarkets.length === 1 ? 'piață' : 'piețe'}</p><p class="mt-1 hidden text-xs leading-4 text-muted-foreground min-[390px]:block">{batchRunning || resultsLoading ? `${terminalProgress.length} din ${strategyCountLabel(selectedStrategyIds.length)} ${selectedStrategyIds.length === 1 ? 'are' : 'au'} status terminal.` : preflightReason || 'Configurația este gata de rulare.'}</p></div>
				<Button class="shrink-0" size="lg" onclick={runAnalysis} disabled={!analysisCanRun} aria-label={`Rulează analiza pentru ${strategyCountLabel(selectedStrategyIds.length)}`}>{#if batchRunning || resultsLoading}<Loader2 class="size-4 animate-spin" aria-hidden="true" /> Procesează{:else}<Play class="size-4" aria-hidden="true" /><span class="sm:hidden">Rulează {strategyCountLabel(selectedStrategyIds.length)}</span><span class="hidden sm:inline">Rulează analiza pentru {strategyCountLabel(selectedStrategyIds.length)}</span>{/if}</Button>
			</div>
		</div>
	{/if}

	{#if successfulRunIds.length > 0}
		<div class="mobile-above-nav fixed inset-x-0 z-30 border-t border-football-green/40 bg-background/95 p-3 shadow-2xl backdrop-blur lg:sticky lg:bottom-4 lg:ml-auto lg:max-w-4xl lg:border lg:p-4">
			<div class="mx-auto flex max-w-7xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
				<div class="min-w-0"><p class="text-sm font-semibold text-foreground">{selectedPredictionIds.length > 0 ? `${candidateCountLabel(selectedPredictionIds.length)} ${selectedPredictionIds.length === 1 ? 'selectat' : 'selectați'}` : `${runCountLabel(successfulRunIds.length)} gata pentru bilete`}</p><p class="mt-1 truncate text-xs text-muted-foreground">Set #{selectedDataset?.id} · {runCountLabel(successfulRunIds.length)}: {successfulRunIds.map((id) => `#${id}`).join(', ')}</p></div>
				<div class="flex shrink-0 gap-2">{#if selectedPredictionIds.length > 0}<Button variant="secondary" onclick={addSelectedToBetslip}>Adaugă în slip</Button>{/if}<a href={ticketsUrl} class="inline-flex min-h-11 flex-1 items-center justify-center gap-2 bg-primary px-4 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 sm:flex-none">Continuă la bilete <ArrowRight class="size-4" aria-hidden="true" /></a></div>
			</div>
		</div>
	{/if}

	<BetslipReviewCallout label="Selecțiile analizate pot fi revizuite înainte de generarea biletelor." />
</section>
