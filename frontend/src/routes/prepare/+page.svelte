<script lang="ts">
	import { onMount } from 'svelte';
	import { SvelteDate } from 'svelte/reactivity';
	import { fade, slide } from 'svelte/transition';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Skeleton from '$lib/components/ui/skeleton/skeleton.svelte';
	import Separator from '$lib/components/ui/separator/separator.svelte';
	import ScheduledJobRunTable from '$lib/components/jobs/ScheduledJobRunTable.svelte';
	import { jobsApi } from '$lib/api/jobs';
	import { ApiClientError } from '$lib/api/client';
	import { apiBaseUrl } from '$lib/api/base';
	import { cronFromInterval, describeScheduledJob, scheduledJobsForArea } from '$lib/scheduled-jobs.helpers';
	import { cn } from '$lib/utils';
	import type { Country, LeagueInfo, ScheduledJob, ScrapeJob, ScrapeJobLogEntry, ScrapeJobLogPage } from '$lib/types';
	import {
		HISTORY_PRESET_OPTIONS,
		buildHistoricSeasons,
		buildHistoryDateRange,
		buildScrapeLeagueSlugs,
		catalogAvailabilityLabel,
		filterScrapeLeagueGroups,
		formatCatalogRefreshTime,
		getLeagueCatalogAvailability,
		getLargeScrapeScopeWarning,
		historicRangeMetadata,
		isLeagueScrapeSelectable,
		parseScrapeCatalog,
		type CatalogAvailability
	} from './catalog.helpers';
	import {
		safeScrapeFailureReason,
		scrapeAttemptNotice,
		type FailedScrapeAttempt
	} from './scrape-attempts.helpers';
	import {
		autoScrapeIntervalHours,
		PREPARE_INTERVAL_UNIT_OPTIONS,
		type PrepareIntervalUnit
	} from './interval.helpers';

	const BASE_URL = apiBaseUrl();

	type WorldCupPipelineSummary = {
		future_days: number;
		target_date?: string | null;
		target_date_from?: string | null;
		target_date_to?: string | null;
		history_years: number;
		historic_seasons: number[];
		scrape_jobs: number;
		completed_scrape_jobs: number;
		failed_scrape_jobs: number;
		target_matches: number;
		prediction_runs: number;
		completed_prediction_runs: number;
		partial_prediction_runs: number;
		failed_prediction_runs: number;
		top_candidates: number;
		watchlist_candidates?: number;
		ticket_generation_blocked?: boolean;
		difficulty_tiers: number;
		tiered_ticket_candidates: number;
		created_tickets: number;
		created_experimental_tickets?: number;
		ticket_generation_mode?: string;
		scraped_markets: string;
	};

	type WorldCupTicketCandidate = {
		match_id: number;
		match: string;
		league: string | null;
		kickoff: string | null;
		market: string;
		selection: string;
		probability: number;
		odds: number;
		bookmaker: string | null;
		model_types: string[];
		model_prediction_id: number;
		expected_return_score: number;
		is_ticket_eligible?: boolean;
		reliability?: string;
		reliability_score?: number;
		quality_reasons?: string[];
	};

	type WorldCupDifficultyBilet = {
		rank: number;
		ticket_id: number | null;
		ticket_type: string;
		leg_count: number;
		combined_probability: number;
		total_odds: number;
		expected_return_score: number;
		legs: WorldCupTicketCandidate[];
	};

	type WorldCupDifficultyTier = {
		level: number;
		label: string;
		leg_count: number;
		difficulty: string;
		tickets: WorldCupDifficultyBilet[];
	};

	type WorldCupPipelineResponse = {
		status: string;
		summary: WorldCupPipelineSummary;
		scrape_job_ids: number[];
		prediction_run_ids: number[];
		created_ticket_ids: number[];
		created_experimental_ticket_ids?: number[];
		top_candidates: WorldCupTicketCandidate[];
		watchlist_candidates?: WorldCupTicketCandidate[];
		difficulty_tiers: WorldCupDifficultyTier[];
		experimental_difficulty_tiers?: WorldCupDifficultyTier[];
		errors: { type: string; id: number; error: string }[];
	};

	type FootballCatalogValidationResponse = {
		requested: number;
		checked: number;
		results_page_ok: number;
		unavailable: number;
		pending: number;
	};

	function localDateString(date: Date): string {
		const year = date.getFullYear();
		const month = String(date.getMonth() + 1).padStart(2, '0');
		const day = String(date.getDate()).padStart(2, '0');
		return `${year}-${month}-${day}`;
	}

function tomorrowLocalDate(): string {
		const date = new SvelteDate();
		date.setDate(date.getDate() + 1);
		return localDateString(date);
	}

	// --- State ---
	let countries = $state<Country[]>([]);
	let allLeagues = $state<LeagueInfo[]>([]);
	let selectedCountries = $state<string[]>([]);
	let selectedLeagues = $state<string[]>([]);
	let countryQuery = $state('');
	let leagueQuery = $state('');
	let showAllCountries = $state(false);
	let acknowledgedLargeScopeKey = $state<string | null>(null);
	let loadingCatalog = $state(true);
	let catalogSource = $state<string | null>(null);
	let catalogStatus = $state<CatalogAvailability>(null);
	let catalogLastRefreshedAt = $state<string | null>(null);
	let validatingCatalog = $state(false);
	let catalogValidationMessage = $state('');
	let catalogValidationError = $state('');
	let catalogLoadError = $state('');
	let jobsLoadError = $state('');

	// Past Istoric
	let pastEnabled = $state(true);
	let pastFrom = $state('');
	let pastTo = $state('');
	let historyPresetYears = $state('10');
	let historicMaxPages = $state('3');
	let historicDays = $state('0');
	let historicWeeks = $state('0');
	let historicMonths = $state('0');
	let historicYears = $state('10');

	// Future Mecies
	let futureEnabled = $state(true);
	let futureDays = $state('7');
	let futureWeeks = $state('0');
	let futureMonths = $state('0');
	let futureYears = $state('0');

	// Options
	let autoScrape = $state(false);
	let autoIntervalNumber = $state('24');
	let autoIntervalUnit = $state<PrepareIntervalUnit>('Hours');
	let autoRunPredictions = $state(false);
	let autoPredictionStrategyIds = $state('');
	let autoPredictionMarkets = $state<string[]>(['1x2']);
	let autoCreateTickets = $state(false);
	let autoTicketCount = $state('3');
	let autoTicketDifficulty = $state('balanced');
	let autoTicketMinCote = $state('1.20');
	let autoTicketMaxCote = $state('5.00');
	let autoTicketMiză = $state('10');
	let scraperEngine = $state('auto');
	let dedupSkip = $state(true);

	// Jobs
	let jobs = $state<ScrapeJob[]>([]);
	let loadingJobs = $state(true);
	let scheduledJobs = $state<ScheduledJob[]>([]);
	let loadingScheduledJobs = $state(true);
	let scheduledJobsError = $state('');
	let savingScheduledJob = $state(false);
	let interactive = $state(false);
	let expandedJobId = $state<number | null>(null);
	let logsPanelDeschide = $state(false);
	let loadingJobLogs = $state(false);
	let selectedLogJobId = $state<number | null>(null);
	let jobLogs = $state<ScrapeJobLogEntry[]>([]);
	let jobLogsError = $state('');

	// Submit
	let submitting = $state(false);
	let submitSuccess = $state('');
	let submitError = $state('');
	let submitPartial = $state('');
	let failedScrapeAttempts = $state<FailedScrapeAttempt[]>([]);
	let retryingFailedScrapes = $state(false);
	let pipelineRunning = $state(false);
	let pipelineError = $state('');
	let pipelineResult = $state<WorldCupPipelineResponse | null>(null);
	let pipelineStartedJobId = $state<number | null>(null);
	let pipelineTargetDate = $state(tomorrowLocalDate());
	let pipelineTicketCount = $state('5');
	let pipelineTicketMiză = $state('10');
	let pipelineAllowExperimental = $state(true);

	let pollTimer: ReturnType<typeof setInterval> | null = null;

	// --- Derived ---
	const filteredLeagueGroups = $derived(
		filterScrapeLeagueGroups(countries, selectedCountries, leagueQuery)
	);
	const filteredLeagues = $derived(filteredLeagueGroups.flatMap((country) => country.leagues));
	const filteredCountries = $derived(
		countries.filter((country) =>
			country.country.toLocaleLowerCase().includes(countryQuery.trim().toLocaleLowerCase())
		)
	);
	const displayedCountries = $derived(
		countryQuery.trim() || showAllCountries ? filteredCountries : filteredCountries.slice(0, 12)
	);
	const hiddenCountryCount = $derived(Math.max(0, filteredCountries.length - displayedCountries.length));
	const displayedLeagueGroups = $derived(
		selectedCountries.length > 0 || leagueQuery.trim() ? filteredLeagueGroups : []
	);
	const catalogStatusLabel = $derived(catalogAvailabilityLabel(catalogStatus));
	const catalogRefreshLabel = $derived(formatCatalogRefreshTime(catalogLastRefreshedAt));

	const selectedCountryBadges = $derived(
		selectedCountries.map((c) => ({
			value: c,
			label: c
		}))
	);
	const selectedCountryPendingCandidates = $derived.by(() => {
		if (selectedCountries.length !== 1) return 0;
		return (
			countries
				.find((country) => country.country === selectedCountries[0])
				?.leagues.filter((league) => {
					const availability = getLeagueCatalogAvailability(league);
					return availability === 'discovered' || availability === 'validated_url';
				}).length ?? 0
		);
	});
	const catalogValidationBatchSize = $derived(Math.min(selectedCountryPendingCandidates, 25));

	const selectedLeagueBadges = $derived(
		selectedLeagues.map((id) => {
			const league = allLeagues.find((l) => l.id === id);
			return { value: id, label: league?.name ?? id };
		})
	);

	const selectedScrapeLeagueSlugs = $derived(buildScrapeLeagueSlugs(allLeagues, selectedLeagues));

	const latestPipelineJob = $derived.by(() => {
		const pipelineJobs = jobs.filter((job) => job.job_type === 'world_cup_pipeline');
		if (pipelineStartedJobId !== null) {
			return pipelineJobs.find((job) => job.id === pipelineStartedJobId) ?? pipelineJobs[0] ?? null;
		}
		return pipelineJobs[0] ?? null;
	});

	const displayedPipelineResult = $derived.by(() => {
		if (pipelineResult) return pipelineResult;
		if (!latestPipelineJob?.output) return null;
		try {
			return JSON.parse(latestPipelineJob.output) as WorldCupPipelineResponse;
		} catch {
			return null;
		}
	});

	const automaticScrapeJobs = $derived(scheduledJobsForArea(scheduledJobs, 'scrape'));
	const orchestrationJobs = $derived(scheduledJobsForArea(scheduledJobs, 'orchestration'));

	const intervalUnitOptions = PREPARE_INTERVAL_UNIT_OPTIONS;

	const scraperEngineOptions = [
		{ value: 'auto', label: 'Automat: Scrapling, apoi rezervă Playwright' },
		{ value: 'playwright', label: 'Numai Playwright (compatibilitate maximă)' },
		{ value: 'scrapling-http', label: 'Numai Scrapling HTTP (rapid pentru piețele principale)' },
		{ value: 'scrapling-stealth', label: 'Numai browserul discret Scrapling' }
	];

	const predictionMarketOptions = [
		{ value: '1x2', label: '1X2' },
		{ value: 'over_under_2.5', label: 'Over/Under 2.5' },
		{ value: 'btts', label: 'BTTS' }
	];

	const historyPresetOptions = HISTORY_PRESET_OPTIONS;

	const historicSeasonPreview = $derived(buildHistoricSeasons(pastFrom, pastTo, buildScrapeLeagueSlugs(allLeagues, selectedLeagues)));
	const largeScopeWarning = $derived(
		pastEnabled
			? getLargeScrapeScopeWarning(selectedScrapeLeagueSlugs.length, historicSeasonPreview.length)
			: null
	);
	const isLargeScopeAcknowledged = $derived(
		largeScopeWarning === null || acknowledgedLargeScopeKey === largeScopeWarning.key
	);

	const historicIntervalDays = $derived(
		intervalToDays(historicDays, historicWeeks, historicMonths, historicYears)
	);

	const futureIntervalDays = $derived(
		intervalToDays(futureDays, futureWeeks, futureMonths, futureYears)
	);
	const scopeReady = $derived(selectedLeagues.length > 0 || (!pastEnabled && selectedCountries.length > 0));
	const coverageReady = $derived((pastEnabled && Boolean(pastFrom && pastTo)) || (futureEnabled && futureIntervalDays > 0));
	const canStartScrape = $derived(
		!submitting &&
		isLargeScopeAcknowledged &&
		(selectedCountries.length > 0 || selectedLeagues.length > 0) &&
		(!pastEnabled || selectedScrapeLeagueSlugs.length > 0) &&
		coverageReady
	);
	const setupSummary = $derived.by(() => {
		const scope = selectedLeagues.length > 0
			? `${selectedLeagues.length} ${selectedLeagues.length === 1 ? 'ligă' : 'ligi'}`
			: selectedCountries.length > 0
				? `${selectedCountries.length} ${selectedCountries.length === 1 ? 'țară' : 'țări'}`
				: 'Nicio competiție selectată';
		const ranges: string[] = [];
		if (pastEnabled) ranges.push(`${historyPresetYears || 'personalizat'} ani de istoric`);
		if (futureEnabled && futureIntervalDays > 0) ranges.push(`${futureIntervalDays} zile viitoare`);
		return `${scope} · ${ranges.length > 0 ? ranges.join(' + ') : 'Nicio acoperire selectată'}`;
	});

	const unsupportedControlNotes = $derived.by(() => {
		const notes: string[] = [];
		if (dedupSkip) {
			notes.push('Backendul evită recolectarea joburilor finalizate care au aceiași parametri de intrare.');
		}
		if (autoScrape) {
			notes.push('Colectarea automată poate fi salvată ca acțiune persistentă prin /api/v1/jobs.');
		}
		if (autoRunPredictions) {
			notes.push('Orchestrarea colectare → predicții va pune automat predicțiile în coadă după fiecare colectare programată.');
		}
		if (autoCreateTickets) {
			notes.push('Orchestrarea programată va crea și bilete din cel mai recent lot după finalizarea predicțiilor.');
		}
		if (pastEnabled && (positiveInteger(historicDays) > 0 || positiveInteger(historicWeeks) > 0 || positiveInteger(historicMonths) > 0)) {
			notes.push('Valorile istorice în zile/săptămâni/luni sunt transformate într-un interval și sezoane; colectarea istorică OddsHarvester suportă sezoane, nu ferestre exacte pe zile.');
		}
		return notes;
	});

	// --- Data Fetching ---
	async function fetchCatalog() {
		catalogLoadError = '';
		try {
			const res = await fetch(`${BASE_URL}/api/v1/catalog/countries`, { credentials: 'include' });
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			if (res.ok) {
				const catalog = parseScrapeCatalog(await res.json());
				countries = catalog.countries;
				allLeagues = countries.flatMap((c) => c.leagues);
				catalogSource = catalog.source;
				catalogStatus = catalog.status;
				catalogLastRefreshedAt = catalog.lastRefreshedAt;
			}
		} catch (error) {
			catalogLoadError = error instanceof Error ? error.message : 'Catalogul nu a putut fi încărcat.';
		} finally {
			loadingCatalog = false;
		}
	}

	async function validatePendingCatalogCandidates() {
		if (selectedCountries.length !== 1 || catalogValidationBatchSize === 0) return;
		validatingCatalog = true;
		catalogValidationError = '';
		catalogValidationMessage = '';
		try {
			const res = await fetch(`${BASE_URL}/api/v1/catalog/football/validate`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				credentials: 'include',
				body: JSON.stringify({ country: selectedCountries[0], limit: 25 })
			});
			if (!res.ok) {
				const err = await res.json().catch(() => ({ detail: 'Validarea catalogului a eșuat' }));
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			const result = (await res.json()) as FootballCatalogValidationResponse;
			catalogValidationMessage = `Verificate ${result.checked}: ${result.results_page_ok} pagini de rezultate validate, ${result.unavailable} indisponibile, ${result.pending} amânate pentru reîncercare.`;
			await fetchCatalog();
		} catch (err) {
			catalogValidationError = err instanceof Error ? err.message : 'Validarea catalogului a eșuat';
		} finally {
			validatingCatalog = false;
		}
	}

	async function fetchJobs() {
		jobsLoadError = '';
		try {
			const res = await fetch(`${BASE_URL}/api/v1/data/scrape`, { credentials: 'include' });
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			if (res.ok) {
				jobs = await res.json();
				if (selectedLogJobId === null && jobs.length > 0) {
					selectedLogJobId = jobs[0].id;
				}
			}
		} catch (error) {
			jobsLoadError = error instanceof Error ? error.message : 'Joburile nu au putut fi încărcate.';
		} finally {
			loadingJobs = false;
		}

		if (logsPanelDeschide) {
			void fetchJobLogs(selectedLogJobId ?? jobs[0]?.id ?? null);
		}
	}

	async function fetchScheduledJobs() {
		loadingScheduledJobs = true;
		scheduledJobsError = '';
		try {
			scheduledJobs = await jobsApi.getScheduledJobs();
		} catch (err) {
			scheduledJobsError = err instanceof ApiClientError ? err.message : 'Joburile programate de colectare nu sunt disponibile';
		} finally {
			loadingScheduledJobs = false;
		}
	}

	async function toggleScheduledJob(jobId: number) {
		scheduledJobsError = '';
		try {
			const updated = await jobsApi.toggleJob(jobId);
			scheduledJobs = scheduledJobs.map((job) => (job.id === jobId ? updated : job));
		} catch (err) {
			scheduledJobsError = err instanceof ApiClientError ? err.message : 'Starea jobului programat nu a putut fi schimbată';
		}
	}

	async function saveAutomatScrapeAction() {
		savingScheduledJob = true;
		scheduledJobsError = '';
		try {
			const scrapeLeagueSlugs = buildScrapeLeagueSlugs(allLeagues, selectedLeagues);
			const strategyIds = autoPredictionStrategyIds
				.split(',')
				.map((value) => Number.parseInt(value.trim(), 10))
				.filter((value) => Number.isFinite(value) && value > 0);
			if (autoRunPredictions && strategyIds.length === 0) {
				scheduledJobsError = 'Adaugă cel puțin un ID de strategie înainte de salvarea automatizării colectare → predicții';
				return;
			}
			const orchestrationTaskType = autoRunPredictions
				? autoCreateTickets
					? 'scrape_predict_tickets'
					: 'scrape_then_predict'
				: 'scrape_odds';
			const created = await jobsApi.createScheduledJob({
				name: `${autoRunPredictions ? 'Colectare + predicții' : 'Colectare automată'} ${selectedLeagues.length > 0 ? selectedLeagues.length : 'toate'} ${selectedLeagues.length === 1 ? 'ligă' : 'ligi'}`,
				task_type: orchestrationTaskType,
				cron_expression: cronFromInterval(autoIntervalNumber, autoIntervalUnit),
				config: {
					source_page: 'scrape',
					area: autoRunPredictions ? 'orchestration' : 'scrape',
					workflow: autoRunPredictions
						? autoCreateTickets
							? 'scrape_predict_tickets'
							: 'scrape_then_predict'
						: 'scrape_only',
					strategy_ids: autoRunPredictions ? strategyIds : undefined,
					markets: autoRunPredictions ? autoPredictionMarkets : undefined,
					avoid_reprediction: autoRunPredictions ? true : undefined,
					tickets: autoRunPredictions && autoCreateTickets
						? {
								ticket_count: parseInt(autoTicketCount, 10) || 1,
								difficulty: autoTicketDifficulty,
								market_types: autoPredictionMarkets,
								min_odds: parseFloat(autoTicketMinCote) || 1.01,
								max_odds: parseFloat(autoTicketMaxCote) || 100,
								stake: parseFloat(autoTicketMiză) || 10
							}
						: undefined,
					params: {
						...buildBaseScrapeParams(scrapeLeagueSlugs),
						command: 'upcoming',
						future_days: futureIntervalDays,
						future_range: {
							days: positiveInteger(futureDays),
							weeks: positiveInteger(futureWeeks),
							months: positiveInteger(futureMonths),
							years: positiveInteger(futureYears)
						},
						historic_range_days: historicIntervalDays,
						past_from: pastFrom || undefined,
						past_to: pastTo || undefined
					}
				}
			});
			scheduledJobs = [created, ...scheduledJobs.filter((job) => job.id !== created.id)];
		} catch (err) {
			scheduledJobsError = err instanceof ApiClientError ? err.message : 'Acțiunea de colectare automată nu a putut fi salvată';
		} finally {
			savingScheduledJob = false;
		}
	}

	async function fetchJobLogs(jobId = selectedLogJobId) {
		if (jobId === null) {
			jobLogs = [];
			jobLogsError = 'Selectează un job de colectare pentru a vedea jurnalul';
			return;
		}

		selectedLogJobId = jobId;
		loadingJobLogs = true;
		jobLogsError = '';
		try {
			const res = await fetch(`${BASE_URL}/api/v1/data/scrape/${jobId}/logs?page=1&per_page=200`, { credentials: 'include' });
			if (!res.ok) {
				const err = await res.json().catch(() => ({ detail: 'Jurnalele jobului de colectare nu sunt disponibile' }));
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			const payload = (await res.json()) as ScrapeJobLogPage;
			jobLogs = payload.items;
		} catch (err) {
			jobLogs = [];
			jobLogsError = err instanceof Error ? err.message : 'Jurnalele jobului de colectare nu sunt disponibile';
		} finally {
			loadingJobLogs = false;
		}
	}

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

	function applyHistoryPreset(yearsValue = historyPresetYears) {
		const years = Number.parseInt(yearsValue, 10) || 10;
		historicDays = '0';
		historicWeeks = '0';
		historicMonths = '0';
		historicYears = String(years);
		const range = buildHistoryDateRange(years);
		pastEnabled = true;
		pastFrom = range.from;
		pastTo = range.to;
		historyPresetYears = String(years);
	}

	function applyHistoricInterval() {
		const zile = historicIntervalDays;
		if (zile <= 0) return;
		const end = new SvelteDate();
		const start = new SvelteDate();
		start.setDate(start.getDate() - zile);
		pastEnabled = true;
		pastFrom = localDateString(start);
		pastTo = localDateString(end);
		historyPresetYears = String(positiveInteger(historicYears));
	}

	function buildBaseScrapeParams(scrapeLeagueSlugs: string[]): Record<string, unknown> {
		const params: Record<string, unknown> = {
			countries: selectedCountries,
			leagues: scrapeLeagueSlugs,
			sport: 'football',
			headless: true,
			scraper_engine: scraperEngine
		};

		if (dedupSkip) {
			params.dedup_skip_requested = true;
		}
		if (autoScrape) {
			params.auto_scrape_requested = true;
		}

		if (autoScrape) {
			const num = parseInt(autoIntervalNumber, 10) || 24;
			params.auto_interval_hours = autoScrapeIntervalHours(String(num), autoIntervalUnit);
		}

		return params;
	}

	class ScrapeLaunchError extends Error {
		jobId?: number;

		constructor(message: string, jobId?: number) {
			super(message);
			this.jobId = jobId;
		}
	}

	async function executeScrapeJob(jobId: number): Promise<number> {
		const executeRes = await fetch(`${BASE_URL}/api/v1/data/scrape/${jobId}/execute-background`, {
			method: 'POST',
			credentials: 'include'
		});

		if (!executeRes.ok) {
			const err = await executeRes.json().catch(() => ({ detail: 'Jobul creat nu a putut fi pornit' }));
			throw new ScrapeLaunchError(err.detail || `HTTP ${executeRes.status}`, jobId);
		}

		return jobId;
	}

	function newScrapeIdempotencyKey(): string {
		const uuid = typeof crypto !== 'undefined' && 'randomUUID' in crypto
			? crypto.randomUUID()
			: `${Date.now()}-${Math.random().toString(36).slice(2)}`;
		return `prepare-scrape-${uuid}`;
	}

	async function createAndExecuteScrapeJob(
		params: Record<string, unknown>,
		league: string | undefined,
		idempotencyKey: string
	): Promise<number> {
		const createRes = await fetch(`${BASE_URL}/api/v1/data/scrape`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'Idempotency-Key': idempotencyKey
			},
			credentials: 'include',
			body: JSON.stringify({ job_type: 'scrape_odds', league, params })
		});

		if (!createRes.ok) {
			const err = await createRes.json().catch(() => ({ detail: 'Jobul nu a putut fi creat' }));
			throw new ScrapeLaunchError(err.detail || `HTTP ${createRes.status}`);
		}

		const createdJob = (await createRes.json()) as { id: number };
		return executeScrapeJob(createdJob.id);
	}

	async function startScrape() {
		submitError = '';
		submitSuccess = '';
		submitPartial = '';
		failedScrapeAttempts = [];

		if (largeScopeWarning && !isLargeScopeAcknowledged) {
			submitError = 'Confirmă aria mare de colectare istorică înainte de pornire.';
			return;
		}

		submitting = true;

		const scrapeLeagueSlugs = buildScrapeLeagueSlugs(allLeagues, selectedLeagues);
		if (selectedLeagues.length > 0 && scrapeLeagueSlugs.length !== selectedLeagues.length) {
			submitError = 'Unele ligi selectate nu sunt încă suportate de motorul de colectare';
			submitting = false;
			return;
		}
		if (pastEnabled && scrapeLeagueSlugs.length === 0) {
			submitError = 'Selectează cel puțin o ligă suportată înainte de colectarea sezoanelor istorice.';
			submitting = false;
			return;
		}
		if (
			pastEnabled &&
			scrapeLeagueSlugs.includes('world-cup') &&
			scrapeLeagueSlugs.some((slug) => slug !== 'world-cup')
		) {
			submitError = 'Pentru colectarea istorică, rulează Cupa Mondială separat de ligile pe sezoane';
			submitting = false;
			return;
		}

		try {
			const baseParams = buildBaseScrapeParams(scrapeLeagueSlugs);
			const createdJobIds: number[] = [];
			const failedAttempts: FailedScrapeAttempt[] = [];

			if (pastEnabled && (!pastFrom || !pastTo)) {
				applyHistoricInterval();
			}

			if (pastEnabled && pastFrom && pastTo) {
				const sezoane = buildHistoricSeasons(pastFrom, pastTo, scrapeLeagueSlugs);
				const historicMetadata = historicRangeMetadata(pastFrom, pastTo, historicIntervalDays);
				if (sezoane.length === 0) {
					throw new Error('Nu există sezoane istorice pentru intervalul selectat.');
				}

				const maxPages = Number.parseInt(historicMaxPages, 10) || 3;
				const isWorldCupOnly = scrapeLeagueSlugs.length > 0 && scrapeLeagueSlugs.every((slug) => slug === 'world-cup');
				for (const season of sezoane) {
					const params = {
						...baseParams,
						command: 'historic',
						season,
						past_from: pastFrom,
						past_to: pastTo,
						historic_range_days: historicMetadata.days || undefined,
						history_years: historicMetadata.years || undefined,
						max_pages: isWorldCupOnly ? Math.max(maxPages, 3) : maxPages,
						timeout_seconds: isWorldCupOnly ? 2400 : undefined
					};
					const league = scrapeLeagueSlugs.length === 1 ? scrapeLeagueSlugs[0] : undefined;
					const idempotencyKey = newScrapeIdempotencyKey();
					try {
						createdJobIds.push(await createAndExecuteScrapeJob(params, league, idempotencyKey));
					} catch (error) {
						failedAttempts.push({
							label: `sezonul ${season}`,
							params,
							league,
							jobId: error instanceof ScrapeLaunchError ? error.jobId : undefined,
							idempotencyKey,
							reason: safeScrapeFailureReason(error)
						});
					}
				}
			}

			if (futureEnabled && futureIntervalDays > 0) {
				const params = {
					...baseParams,
					command: 'upcoming',
					future_days: futureIntervalDays,
					future_range: {
						days: positiveInteger(futureDays),
						weeks: positiveInteger(futureWeeks),
						months: positiveInteger(futureMonths),
						years: positiveInteger(futureYears)
					}
				};
				const idempotencyKey = newScrapeIdempotencyKey();
				try {
					createdJobIds.push(await createAndExecuteScrapeJob(params, undefined, idempotencyKey));
				} catch (error) {
					failedAttempts.push({
						label: 'meciurile viitoare',
						params,
						jobId: error instanceof ScrapeLaunchError ? error.jobId : undefined,
						idempotencyKey,
						reason: safeScrapeFailureReason(error)
					});
				}
			}

			if (createdJobIds.length === 0 && failedAttempts.length === 0) {
				throw new Error('Activează istoricul sau meciurile viitoare înainte de pornirea colectării.');
			}

			failedScrapeAttempts = failedAttempts;
			submitSuccess = failedAttempts.length === 0 ? scrapeAttemptNotice(createdJobIds, failedAttempts) : '';
			submitPartial = failedAttempts.length ? scrapeAttemptNotice(createdJobIds, failedAttempts) : '';
			await fetchJobs();
			setTimeout(() => (submitSuccess = ''), 4000);
		} catch (err) {
			submitError = err instanceof Error ? err.message : 'Colectarea nu a putut fi pornită';
		} finally {
			submitting = false;
		}
	}

	async function retryFailedScrapes() {
		if (!failedScrapeAttempts.length || retryingFailedScrapes) return;
		retryingFailedScrapes = true;
		const remaining: FailedScrapeAttempt[] = [];
		const created: number[] = [];
		for (const attempt of failedScrapeAttempts) {
			try {
				created.push(
					attempt.jobId
						? await executeScrapeJob(attempt.jobId)
						: await createAndExecuteScrapeJob(attempt.params, attempt.league, attempt.idempotencyKey)
				);
			} catch (error) {
				remaining.push({
					...attempt,
					jobId: error instanceof ScrapeLaunchError ? error.jobId ?? attempt.jobId : attempt.jobId,
					reason: safeScrapeFailureReason(error)
				});
			}
		}
		failedScrapeAttempts = remaining;
		submitPartial = remaining.length ? scrapeAttemptNotice(created, remaining) : '';
		submitSuccess = remaining.length === 0 ? `Reluare reușită. Joburi pornite: #${created.join(', ')}.` : '';
		retryingFailedScrapes = false;
		await fetchJobs();
	}

	async function runWorldCupPipeline() {
		pipelineRunning = true;
		pipelineError = '';
		pipelineResult = null;

		try {
			const targetStart = new Date(`${pipelineTargetDate}T00:00:00`);
			const targetEnd = new Date(`${pipelineTargetDate}T23:59:59.999`);
			const ticketCount = Number.parseInt(pipelineTicketCount, 10) || 5;
			const ticketMiză = Number.parseFloat(pipelineTicketMiză) || 10;
			const res = await fetch(`${BASE_URL}/api/v1/data/world-cup-pipeline`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				credentials: 'include',
				body: JSON.stringify({
					target_date: pipelineTargetDate,
					target_date_from: targetStart.toISOString(),
					target_date_to: targetEnd.toISOString(),
					future_days: 1,
					history_years: 0,
					all_markets: false,
					odds_history: false,
					max_historic_pages: 1,
					scraper_engine: scraperEngine,
					ticket_count: ticketCount,
					ticket_stake: ticketMiză,
					create_tickets: true,
					allow_experimental_tickets: pipelineAllowExperimental,
					training_limit: 120
				})
			});

			if (!res.ok) {
				const err = await res.json().catch(() => ({ detail: 'Fluxul pentru Cupa Mondială a eșuat' }));
				throw new Error(err.detail || `HTTP ${res.status}`);
			}

			const job = (await res.json()) as ScrapeJob;
			pipelineStartedJobId = job.id;
			jobs = [job, ...jobs.filter((entry) => entry.id !== job.id)];
			await fetchJobs();
		} catch (err) {
			pipelineError = err instanceof Error ? err.message : 'Fluxul pentru Cupa Mondială a eșuat';
		} finally {
			pipelineRunning = false;
		}
	}

	function toggleCountry(country: string) {
		if (selectedCountries.includes(country)) {
			selectedCountries = selectedCountries.filter((c) => c !== country);
			const leagueIds = countries
				.find((c) => c.country === country)
				?.leagues.map((l) => l.id) ?? [];
			selectedLeagues = selectedLeagues.filter((id) => !leagueIds.includes(id));
		} else {
			selectedCountries = [...selectedCountries, country];
		}
	}

	function preferredLeague(countryName: string, patterns: RegExp[]): LeagueInfo | null {
		const country = countries.find((entry) => entry.country.toLocaleLowerCase() === countryName.toLocaleLowerCase());
		if (!country) return null;
		return (
			country.leagues.find(
				(league) =>
					isLeagueScrapeSelectable(league) &&
					patterns.some((pattern) => pattern.test(league.name) || pattern.test(league.scrape_slug ?? ''))
			) ?? country.leagues.find(isLeagueScrapeSelectable) ?? null
		);
	}

	function applyScopePreset(preset: 'romania' | 'top-five' | 'world-cup') {
		const definitions: Record<typeof preset, { country: string; patterns: RegExp[] }[]> = {
			romania: [{ country: 'Romania', patterns: [/superliga/i, /liga[- ]?1/i] }],
			'top-five': [
				{ country: 'England', patterns: [/^premier league$/i] },
				{ country: 'Spain', patterns: [/^la ?liga$/i] },
				{ country: 'Italy', patterns: [/^serie a$/i] },
				{ country: 'Germany', patterns: [/^bundesliga$/i] },
				{ country: 'France', patterns: [/^ligue 1$/i] }
			],
			'world-cup': [{ country: 'World', patterns: [/world cup/i, /^world-cup$/i] }]
		};

		const selected = definitions[preset]
			.map((definition) => ({ ...definition, league: preferredLeague(definition.country, definition.patterns) }))
			.filter((entry): entry is { country: string; patterns: RegExp[]; league: LeagueInfo } => entry.league !== null);

		selectedCountries = selected.map((entry) => entry.country);
		selectedLeagues = selected.map((entry) => entry.league.id);
		countryQuery = '';
		leagueQuery = '';
		showAllCountries = false;
		acknowledgedLargeScopeKey = null;
	}

	function clearScope() {
		selectedCountries = [];
		selectedLeagues = [];
		countryQuery = '';
		leagueQuery = '';
		showAllCountries = false;
		acknowledgedLargeScopeKey = null;
	}

	function setFuturePreset(zile: number) {
		futureEnabled = true;
		futureDays = String(zile);
		futureWeeks = '0';
		futureMonths = '0';
		futureYears = '0';
	}

	function toggleLeague(id: string) {
		const league = allLeagues.find((entry) => entry.id === id);
		if (!league || !isLeagueScrapeSelectable(league)) {
			return;
		}

		if (selectedLeagues.includes(id)) {
			selectedLeagues = selectedLeagues.filter((l) => l !== id);
		} else {
			selectedLeagues = [...selectedLeagues, id];
		}
	}

	function toggleAllLeagues() {
		const filteredIds = filteredLeagues.filter(isLeagueScrapeSelectable).map((l) => l.id);
		if (filteredIds.every((id) => selectedLeagues.includes(id))) {
			selectedLeagues = selectedLeagues.filter((id) => !filteredIds.includes(id));
		} else {
			selectedLeagues = [...new Set([...selectedLeagues, ...filteredIds])];
		}
	}

	function toggleExpandJob(id: number) {
		expandedJobId = expandedJobId === id ? null : id;
	}


	function handleLogsDetailsToggle(event: Event) {
		logsPanelDeschide = (event.currentTarget as HTMLDetailsElement).open;
		if (logsPanelDeschide && jobLogs.length === 0) {
			void fetchJobLogs(selectedLogJobId ?? jobs[0]?.id ?? null);
		}
	}

	function openLogsForJob(jobId: number) {
		selectedLogJobId = jobId;
		logsPanelDeschide = true;
		void fetchJobLogs(jobId);
	}

	function formatDuration(created: string, completed: string | null): string {
		if (!completed) return '—';
		const ms = new Date(completed).getTime() - new Date(created).getTime();
		const secs = Math.floor(ms / 1000);
		if (secs < 60) return `${secs}s`;
		const mins = Math.floor(secs / 60);
		return `${mins}m ${secs % 60}s`;
	}

	function statusVariant(status: string): 'default' | 'success' | 'warning' | 'danger' | 'info' {
		const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
			completed: 'success',
			running: 'warning',
			queued: 'info',
			failed: 'danger',
			cancelled: 'danger'
		};
		return map[status] ?? 'default';
	}

	function statusLabel(status: string): string {
		const labels: Record<string, string> = {
			completed: 'finalizat',
			running: 'în desfășurare',
			queued: 'în așteptare',
			failed: 'eșuat',
			cancelled: 'anulat'
		};
		return labels[status] ?? status;
	}

	function logLevelVariant(level: string): 'default' | 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
		const normalized = level.toLowerCase();
		if (normalized === 'error') return 'danger';
		if (normalized === 'warning' || normalized === 'warn') return 'warning';
		if (normalized === 'debug') return 'neutral';
		return 'info';
	}

	function jobLabel(job: ScrapeJob): string {
		return job.job_type || 'necunoscut';
	}

	function jobProgress(job: ScrapeJob): number {
		if (job.status === 'completed') return 100;
		if (job.status === 'running') return 60;
		if (job.status === 'failed' || job.status === 'cancelled') return 100;
		return 0;
	}

	function formatProbability(value: number): string {
		return `${(value * 100).toFixed(1)}%`;
	}

	function formatOdds(value: number): string {
		return value.toFixed(2);
	}

	onMount(() => {
		interactive = true;
		applyHistoryPreset(historyPresetYears);
		fetchCatalog();
		fetchJobs();
		fetchScheduledJobs();
		pollTimer = setInterval(fetchJobs, 10000);
		return () => {
			if (pollTimer) clearInterval(pollTimer);
		};
	});
</script>

<svelte:head>
	<title>Pregătire date meciuri · Bet</title>
</svelte:head>

<div
	class="mx-auto flex min-w-0 max-w-6xl flex-col gap-6 overflow-hidden pb-8"
	data-testid="prepare-panel"
	data-interactive={interactive ? 'true' : 'false'}
	transition:fade={{ duration: 200 }}
>
	<header class="order-1 space-y-5">
		<div class="max-w-3xl">
			<p class="text-xs font-semibold uppercase tracking-[0.16em] text-football-blue">Pregătire date</p>
			<h1 class="mt-1 text-2xl font-extrabold font-sport text-foreground sm:text-3xl">Pregătește datele meciurilor</h1>
			<p class="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Configurează colectarea datelor: alege aria, acoperirea și apoi confirmă o singură acțiune.</p>
		</div>

		<nav aria-label="Pașii pregătirii colectării" class="grid grid-cols-1 gap-2 sm:grid-cols-3">
			<a href="#selection" class={cn('flex min-w-0 items-center gap-3 border px-4 py-3 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-football-blue', scopeReady ? 'border-football-green/40 bg-football-green/5' : 'border-football-blue/40 bg-football-blue/5')}>
				<span class={cn('grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold', scopeReady ? 'bg-football-green text-background' : 'bg-football-blue text-background')}>{scopeReady ? '✓' : '1'}</span>
				<span><span class="block text-sm font-semibold text-foreground">Alege aria</span><span class="block text-xs text-muted-foreground">{selectedLeagues.length || 0} ligi selectate</span></span>
			</a>
			<a href="#coverage" class={cn('flex min-w-0 items-center gap-3 border px-4 py-3 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-football-blue', coverageReady ? 'border-football-green/40 bg-football-green/5' : 'border-border bg-muted/20')}>
				<span class={cn('grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold', coverageReady ? 'bg-football-green text-background' : 'bg-muted text-foreground')}>{coverageReady ? '✓' : '2'}</span>
				<span><span class="block text-sm font-semibold text-foreground">Stabilește acoperirea</span><span class="block text-xs text-muted-foreground">Istoric și meciuri viitoare</span></span>
			</a>
			<a href="#controls" class={cn('flex min-w-0 items-center gap-3 border px-4 py-3 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-football-blue', canStartScrape ? 'border-football-green/40 bg-football-green/5' : 'border-border bg-muted/20')}>
				<span class={cn('grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold', canStartScrape ? 'bg-football-green text-background' : 'bg-muted text-foreground')}>{canStartScrape ? '✓' : '3'}</span>
				<span><span class="block text-sm font-semibold text-foreground">Verifică și pornește</span><span class="block text-xs text-muted-foreground">O singură acțiune finală</span></span>
			</a>
		</nav>

		<div class="flex flex-col gap-3 border border-border bg-muted/20 px-4 py-3 sm:flex-row sm:items-center sm:justify-between" aria-live="polite">
			<div class="min-w-0">
				<p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Configurarea curentă</p>
				<p class="mt-1 truncate text-sm font-medium text-foreground">{setupSummary}</p>
			</div>
			<a href="#controls" class="shrink-0 text-sm font-semibold text-football-blue hover:text-football-green">Verifică configurarea →</a>
		</div>
	</header>

		<Card variant="prediction" class="order-6">
			<details id="automation" class="group">
				<summary class="flex cursor-pointer list-none items-center justify-between gap-4 rounded px-1 py-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-football-blue">
					<span><span class="block text-lg font-semibold text-foreground">Automatizare și fluxuri specializate</span><span class="mt-1 block text-sm text-muted-foreground">Programări opționale, orchestrare colectare-predicții și fluxul pentru Cupa Mondială.</span></span>
					<span class="shrink-0 text-xs font-medium text-football-blue group-open:hidden">Arată</span><span class="hidden shrink-0 text-xs font-medium text-football-blue group-open:inline">Ascunde</span>
				</summary>
			<div class="space-y-5">
				<div class="space-y-3 border border-border bg-muted/20 p-3">
					<div class="flex flex-wrap items-center justify-between gap-2">
						<div>
							<p class="text-sm font-semibold text-foreground">Scraping-uri automate salvate</p>
							<p class="text-xs text-muted-foreground">
								Butoanele de mai jos provin din endpoint-ul persistent <span class="font-mono">/api/v1/jobs</span>.
							</p>
						</div>
						<div class="flex flex-wrap gap-2">
							<Button
								variant="secondary"
								size="sm"
								onclick={fetchScheduledJobs}
								disabled={!interactive || loadingScheduledJobs}
							>
								Reîmprospătează
							</Button>
						</div>
					</div>

					{#if scheduledJobsError}
						<p class="text-xs text-destructive">{scheduledJobsError}</p>
					{/if}

					{#if loadingScheduledJobs}
						<p class="text-xs text-muted-foreground">Se încarcă acțiunile de colectare salvate...</p>
					{:else if automaticScrapeJobs.length === 0}
						<p class="text-xs text-muted-foreground">Nu exista inca scraping-uri automate salvate.</p>
					{:else}
						<div class="flex flex-wrap gap-2">
							{#each automaticScrapeJobs as scheduledJob (scheduledJob.id)}
								<Button
									variant={scheduledJob.enabled ? 'secondary' : 'ghost'}
									size="sm"
									title={describeScheduledJob(scheduledJob)}
									onclick={() => toggleScheduledJob(scheduledJob.id)}
								>
									{scheduledJob.name}
									<span class="ml-1 font-mono text-[10px]">
										{scheduledJob.enabled ? 'activ' : 'pauzat'}
									</span>
								</Button>
							{/each}
						</div>
					{/if}
				</div>

				<ScheduledJobRunTable jobs={[...automaticScrapeJobs, ...orchestrationJobs]} title="Rulări recente ale automatizării de colectare" />

				<div class="space-y-3 border border-border bg-muted/20 p-3">
					<div>
						<p class="text-sm font-semibold text-foreground">Orchestrare opțională colectare → predicții</p>
						<p class="text-xs text-muted-foreground">
							Transformă jobul de colectare salvat într-un flux compus de orchestrare.
						</p>
					</div>
					<label class="flex items-center gap-2 text-sm text-foreground">
						<input
							type="checkbox"
							class="h-4 w-4 accent-football-blue"
							bind:checked={autoRunPredictions}
						/>
						<span>Rulează predicțiile automat după fiecare ciclu de colectare</span>
					</label>
					<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
						<Input
							label="ID-uri strategii (separate prin virgulă)"
							placeholder="ex. 1,2,5"
							bind:value={autoPredictionStrategyIds}
							disabled={!autoRunPredictions}
						/>
						<div class="space-y-2">
							<p class="text-xs text-muted-foreground">Piețe de predicție</p>
							<div class="flex flex-wrap gap-2">
								{#each predictionMarketOptions as option (option.value)}
									<label
										class={cn(
											'flex items-center gap-2 rounded border px-3 py-2 text-xs',
											autoRunPredictions
												? 'border-border bg-background text-foreground'
												: 'border-border/40 bg-muted/30 text-muted-foreground'
										)}
									>
										<input
											type="checkbox"
											class="h-4 w-4 accent-football-blue"
											checked={autoPredictionMarkets.includes(option.value)}
											disabled={!autoRunPredictions}
											onchange={() => {
												if (autoPredictionMarkets.includes(option.value)) {
													autoPredictionMarkets = autoPredictionMarkets.filter((item) => item !== option.value);
												} else {
													autoPredictionMarkets = [...autoPredictionMarkets, option.value];
												}
											}}
										/>
										<span>{option.label}</span>
									</label>
								{/each}
							</div>
						</div>
					</div>
					<label class="flex items-center gap-2 text-sm text-foreground">
						<input
							type="checkbox"
							class="h-4 w-4 accent-football-green"
							bind:checked={autoCreateTickets}
							disabled={!autoRunPredictions}
						/>
						<span>Creează bilete automat după finalizarea predicțiilor</span>
					</label>
					{#if autoRunPredictions && autoCreateTickets}
						<div class="grid grid-cols-1 gap-3 md:grid-cols-3">
							<Input label="Număr bilete" type="number" min="1" max="50" bind:value={autoTicketCount} />
							<Select
								label="Dificultatea biletelor"
								bind:value={autoTicketDifficulty}
								options={[
									{ value: 'safe', label: 'Sigur' },
									{ value: 'balanced', label: 'Echilibrat' },
									{ value: 'aggressive', label: 'Agresiv' }
								]}
							/>
							<Input label="Miză" type="number" min="0.5" step="0.5" bind:value={autoTicketMiză} />
							<Input label="Cotă minimă" type="number" min="1.01" step="0.01" bind:value={autoTicketMinCote} />
							<Input label="Cotă maximă" type="number" min="1.01" step="0.01" bind:value={autoTicketMaxCote} />
						</div>
					{/if}
					{#if orchestrationJobs.length > 0}
						<div class="flex flex-wrap gap-2">
							{#each orchestrationJobs as scheduledJob (scheduledJob.id)}
								<Badge variant={scheduledJob.enabled ? 'info' : 'default'}>
									{scheduledJob.name} · {scheduledJob.enabled ? 'activ' : 'pauzat'}
								</Badge>
							{/each}
						</div>
					{/if}
				</div>

				<details id="world-cup" class="group rounded border border-border bg-muted/10 p-3">
					<summary class="flex cursor-pointer list-none items-center justify-between gap-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-football-blue">
						<span><span class="block text-sm font-semibold text-foreground">Flux de bilete pentru Cupa Mondială</span><span class="mt-1 block text-xs text-muted-foreground">Flux specializat: colectează, prezice și creează bilete pentru o dată țintă.</span></span>
						<span class="shrink-0 text-xs font-medium text-football-blue group-open:hidden">Configurează</span><span class="hidden shrink-0 text-xs font-medium text-football-blue group-open:inline">Ascunde</span>
					</summary>
					<div class="mt-4 space-y-5">
				<div class="grid grid-cols-2 md:grid-cols-4 gap-3">
					<div class="border border-border bg-muted/30 p-3">
						<p class="text-[10px] uppercase tracking-wide text-muted-foreground">Data țintă</p>
						<p class="mt-1 font-mono text-lg text-foreground">{pipelineTargetDate}</p>
					</div>
					<div class="border border-border bg-muted/30 p-3">
						<p class="text-[10px] uppercase tracking-wide text-muted-foreground">Istoric</p>
						<p class="mt-1 font-mono text-lg text-foreground">extern</p>
					</div>
					<div class="border border-border bg-muted/30 p-3">
						<p class="text-[10px] uppercase tracking-wide text-muted-foreground">Cote</p>
						<p class="mt-1 font-mono text-lg text-foreground">Principal</p>
					</div>
					<div class="border border-border bg-muted/30 p-3">
						<p class="text-[10px] uppercase tracking-wide text-muted-foreground">Bilete</p>
						<p class="mt-1 font-mono text-lg text-foreground">{pipelineTicketCount} niveluri</p>
					</div>
				</div>

				<div class="grid grid-cols-1 gap-3 md:grid-cols-4">
					<div>
						<label for="world-cup-target-date" class="mb-1 block text-xs text-muted-foreground">Mâine / data țintă</label>
						<Input id="world-cup-target-date" type="date" bind:value={pipelineTargetDate} />
					</div>
					<div>
						<label for="world-cup-ticket-count" class="mb-1 block text-xs text-muted-foreground">Bilete pe nivel</label>
						<Input id="world-cup-ticket-count" type="number" min="1" max="50" bind:value={pipelineTicketCount} />
					</div>
					<div>
						<label for="world-cup-ticket-stake" class="mb-1 block text-xs text-muted-foreground">Miză</label>
						<Input id="world-cup-ticket-stake" type="number" min="0" step="0.5" bind:value={pipelineTicketMiză} />
					</div>
					<label class="flex items-center gap-2 border border-border bg-muted/20 px-3 py-2 text-sm text-foreground">
						<input
							id="world-cup-experimental"
							type="checkbox"
							class="h-4 w-4 accent-football-blue"
							bind:checked={pipelineAllowExperimental}
						/>
						<span>Creează bilete de urmărire dacă biletele sigure sunt blocate</span>
					</label>
				</div>

				<div class="flex flex-wrap items-center gap-3">
					<Button variant="glow" onclick={runWorldCupPipeline} disabled={pipelineRunning}>
						{pipelineRunning ? 'Se generează biletele pentru mâine...' : 'Generează bilete pentru Cupa Mondială de mâine'}
					</Button>
					<a href="/analyze" class="text-sm text-football-blue hover:text-football-green">Deschide predicțiile</a>
					<a href="/tickets" class="text-sm text-football-blue hover:text-football-green">Deschide biletele</a>
				</div>

				{#if pipelineError}
					<div class="border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
						{pipelineError}
					</div>
				{/if}

				{#if latestPipelineJob}
					<div class="flex flex-wrap items-center gap-2 text-sm">
						<Badge variant={statusVariant(latestPipelineJob.status)}>Job #{latestPipelineJob.id} · {latestPipelineJob.status}</Badge>
						{#if latestPipelineJob.status === 'running'}
							<span class="font-mono text-xs text-muted-foreground">Fluxul rulează în fundal</span>
						{/if}
						{#if latestPipelineJob.error}
							<span class="text-xs text-destructive">{latestPipelineJob.error}</span>
						{/if}
					</div>
				{/if}

				{#if displayedPipelineResult}
					<div class="space-y-4 border border-border bg-muted/20 p-4">
						<div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
							<div>
								<p class="text-xs text-muted-foreground">Joburi de colectare</p>
								<p class="font-mono text-foreground">{displayedPipelineResult.summary.completed_scrape_jobs}/{displayedPipelineResult.summary.scrape_jobs}</p>
							</div>
							<div>
								<p class="text-xs text-muted-foreground">Meciuri țintă</p>
								<p class="font-mono text-foreground">{displayedPipelineResult.summary.target_matches}</p>
							</div>
							<div>
								<p class="text-xs text-muted-foreground">Rulări de predicție</p>
								<p class="font-mono text-foreground">{displayedPipelineResult.summary.completed_prediction_runs}/{displayedPipelineResult.summary.prediction_runs}</p>
							</div>
							<div>
								<p class="text-xs text-muted-foreground">Bilete create</p>
								<p class="font-mono text-foreground">
									{displayedPipelineResult.summary.created_tickets}
									{#if displayedPipelineResult.summary.created_experimental_tickets}
										<span class="text-football-gold">+{displayedPipelineResult.summary.created_experimental_tickets} în lista de urmărire</span>
									{/if}
								</p>
								{#if displayedPipelineResult.summary.ticket_generation_mode}
									<p class="text-[10px] text-muted-foreground">{displayedPipelineResult.summary.ticket_generation_mode}</p>
								{/if}
							</div>
						</div>

						{#if displayedPipelineResult.created_ticket_ids.length > 0}
							<div class="space-y-2">
								<p class="text-xs uppercase tracking-wide text-muted-foreground">
									ID-uri de bilete create ({displayedPipelineResult.created_ticket_ids.length})
								</p>
								<div class="flex flex-wrap gap-1.5">
									{#each displayedPipelineResult.created_ticket_ids.slice(0, 24) as ticketId (ticketId)}
									<Badge variant="success">Bilet #{ticketId}</Badge>
									{/each}
									{#if displayedPipelineResult.created_ticket_ids.length > 24}
										<Badge variant="info">+{displayedPipelineResult.created_ticket_ids.length - 24} în plus</Badge>
									{/if}
								</div>
							</div>
						{/if}

						{#if (displayedPipelineResult.created_experimental_ticket_ids?.length ?? 0) > 0}
							<div class="space-y-2">
								<p class="text-xs uppercase tracking-wide text-muted-foreground">
									ID-uri de bilete în lista de urmărire ({displayedPipelineResult.created_experimental_ticket_ids?.length ?? 0})
								</p>
								<div class="flex flex-wrap gap-1.5">
									{#each (displayedPipelineResult.created_experimental_ticket_ids ?? []).slice(0, 24) as ticketId (ticketId)}
										<Badge variant="warning">Urmărire #{ticketId}</Badge>
									{/each}
									{#if (displayedPipelineResult.created_experimental_ticket_ids?.length ?? 0) > 24}
										<Badge variant="info">+{(displayedPipelineResult.created_experimental_ticket_ids?.length ?? 0) - 24} în plus</Badge>
									{/if}
								</div>
							</div>
						{/if}

						{#if displayedPipelineResult.difficulty_tiers?.length > 0}
							<div class="space-y-4">
								<div>
									<p class="text-sm font-semibold text-foreground">Niveluri de dificultate</p>
									<p class="text-xs text-muted-foreground">
										Primele 10 pe nivel: nivelul 1 conține selecții simple mai sigure, iar nivelul 7 acumulatoare cu șapte selecții.
									</p>
								</div>
								<div class="space-y-3">
									{#each displayedPipelineResult.difficulty_tiers as tier (tier.level)}
										<div class="border border-border bg-background/60 p-3">
											<div class="flex flex-wrap items-center justify-between gap-2">
												<div>
													<p class="text-sm font-semibold text-foreground">
														Nivelul {tier.level}: {tier.label}
													</p>
													<p class="text-xs text-muted-foreground">
														{tier.leg_count} selecții · {tier.tickets.length} bilete candidate
													</p>
												</div>
												<Badge variant={tier.level <= 2 ? 'success' : tier.level <= 4 ? 'info' : 'warning'}>
													{tier.difficulty}
												</Badge>
											</div>

											{#if tier.tickets.length > 0}
												<div class="mt-3 overflow-x-auto">
													<table class="w-full text-xs">
														<thead class="uppercase text-muted-foreground">
															<tr>
																<th class="py-2 text-left">Rang</th>
																<th class="py-2 text-left">Bilet</th>
																<th class="py-2 text-left">Selecții</th>
																<th class="py-2 text-right">Probabilitate</th>
																<th class="py-2 text-right">Cote</th>
																<th class="py-2 text-right">Scor EV</th>
															</tr>
														</thead>
														<tbody>
															{#each tier.tickets as ticket (`${tier.level}-${ticket.rank}`)}
																<tr class="border-t border-border align-top">
																	<td class="py-2 pr-3 font-mono text-muted-foreground">#{ticket.rank}</td>
																	<td class="py-2 pr-3">
																		<div class="font-mono text-foreground">
																			{ticket.ticket_id ? `#${ticket.ticket_id}` : 'necreat'}
																		</div>
																		<div class="text-muted-foreground">{ticket.ticket_type}</div>
																	</td>
																	<td class="py-2 pr-3">
																		<div class="space-y-1">
																			{#each ticket.legs as leg (leg.model_prediction_id)}
																				<div>
																					<span class="text-foreground">{leg.match}</span>
																					<span class="font-mono text-football-blue"> · {leg.market}/{leg.selection}</span>
																					<span class="font-mono text-muted-foreground"> @ {formatOdds(leg.odds)}</span>
																				</div>
																			{/each}
																		</div>
																	</td>
																	<td class="py-2 text-right font-mono text-football-green">
																		{formatProbability(ticket.combined_probability)}
																	</td>
																	<td class="py-2 text-right font-mono text-foreground">{formatOdds(ticket.total_odds)}</td>
																	<td class="py-2 text-right font-mono text-muted-foreground">
																		{ticket.expected_return_score.toFixed(3)}
																	</td>
																</tr>
															{/each}
														</tbody>
													</table>
												</div>
											{:else}
												<p class="mt-3 text-xs text-muted-foreground">
													Nu există încă suficiente meciuri unice de la Cupa Mondială pentru acest nivel de dificultate.
												</p>
											{/if}
										</div>
									{/each}
								</div>
							</div>
						{/if}

						{#if displayedPipelineResult.top_candidates.length > 0}
							<div class="overflow-x-auto">
								<table class="w-full text-sm">
									<thead class="text-xs uppercase text-muted-foreground">
										<tr>
											<th class="py-2 text-left">Meci</th>
											<th class="py-2 text-left">Selecție</th>
											<th class="py-2 text-right">Probabilitate</th>
											<th class="py-2 text-right">Cote</th>
										</tr>
									</thead>
									<tbody>
										{#each displayedPipelineResult.top_candidates.slice(0, 10) as candidate (candidate.model_prediction_id)}
											<tr class="border-t border-border">
												<td class="py-2 pr-3">
													<div class="font-medium text-foreground">{candidate.match}</div>
													<div class="text-xs text-muted-foreground">{candidate.league}</div>
												</td>
												<td class="py-2 pr-3">
													<div class="font-mono text-foreground">{candidate.market} · {candidate.selection}</div>
													<div class="text-xs text-muted-foreground">{candidate.bookmaker ?? 'cea mai bună disponibilă'}</div>
												</td>
												<td class="py-2 text-right font-mono text-football-green">{formatProbability(candidate.probability)}</td>
												<td class="py-2 text-right font-mono text-foreground">{candidate.odds.toFixed(2)}</td>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						{/if}

						{#if (displayedPipelineResult.watchlist_candidates?.length ?? 0) > 0}
							<div class="overflow-x-auto">
								<div class="mb-2">
									<p class="text-sm font-semibold text-foreground">Candidați de urmărire</p>
									<p class="text-xs text-muted-foreground">
										Acești candidați apar când biletele sigure sunt blocate de istoricul insuficient sau de folosirea unui model de rezervă.
									</p>
								</div>
								<table class="w-full text-sm">
									<thead class="text-xs uppercase text-muted-foreground">
										<tr>
											<th class="py-2 text-left">Meci</th>
											<th class="py-2 text-left">Selecție</th>
											<th class="py-2 text-left">Fiabilitate</th>
											<th class="py-2 text-right">Probabilitate</th>
											<th class="py-2 text-right">Cote</th>
										</tr>
									</thead>
									<tbody>
										{#each (displayedPipelineResult.watchlist_candidates ?? []).slice(0, 10) as candidate (candidate.model_prediction_id)}
											<tr class="border-t border-border">
												<td class="py-2 pr-3">
													<div class="font-medium text-foreground">{candidate.match}</div>
													<div class="text-xs text-muted-foreground">{candidate.league}</div>
												</td>
												<td class="py-2 pr-3">
													<div class="font-mono text-foreground">{candidate.market} · {candidate.selection}</div>
													<div class="text-xs text-muted-foreground">{candidate.bookmaker ?? 'cea mai bună disponibilă'}</div>
												</td>
												<td class="py-2 pr-3">
													<Badge variant="warning">{candidate.reliability ?? 'de urmărit'}</Badge>
													<div class="max-w-72 truncate text-[10px] text-muted-foreground" title={(candidate.quality_reasons ?? []).join(', ')}>
														{(candidate.quality_reasons ?? []).join(', ')}
													</div>
												</td>
												<td class="py-2 text-right font-mono text-football-green">{formatProbability(candidate.probability)}</td>
												<td class="py-2 text-right font-mono text-foreground">{candidate.odds.toFixed(2)}</td>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						{/if}

						{#if displayedPipelineResult.errors.length > 0}
							<div class="space-y-1 text-xs text-destructive">
								{#each displayedPipelineResult.errors as error (`${error.type}-${error.id}`)}
									<p>{error.type} #{error.id}: {error.error}</p>
								{/each}
							</div>
						{/if}
					</div>
				{/if}
					</div>
				</details>
			</div>
			</details>
		</Card>

		<!-- Section 2: Data selection -->
	<Card id="selection" title="1. Alege competițiile" variant="data" class="order-2 scroll-mt-24">
		<div class="space-y-5">
			<div class="grid gap-3 lg:grid-cols-[1fr_auto] lg:items-end">
				<div>
					<p class="text-sm font-semibold text-foreground">Începe cu o presetare</p>
					<p class="mt-1 text-xs leading-5 text-muted-foreground">Un clic alege o ligă principală potrivită. Poți ajusta catalogul mai jos.</p>
					<div class="mt-3 flex flex-wrap gap-2">
						<Button variant="secondary" size="sm" onclick={() => applyScopePreset('romania')}>Romania</Button>
						<Button variant="secondary" size="sm" onclick={() => applyScopePreset('top-five')}>Top 5 Europa</Button>
						<Button variant="secondary" size="sm" onclick={() => applyScopePreset('world-cup')}>Cupa Mondială</Button>
					</div>
				</div>
				{#if selectedCountries.length > 0 || selectedLeagues.length > 0}
					<Button variant="ghost" size="sm" onclick={clearScope}>Golește selecția</Button>
				{/if}
			</div>

			{#if selectedLeagueBadges.length > 0}
				<div class="flex flex-wrap items-center gap-2 border border-football-green/30 bg-football-green/5 p-3">
					<span class="text-xs font-semibold uppercase tracking-wide text-football-green">Selectate</span>
					{#each selectedLeagueBadges as badge (badge.value)}
						<Badge variant="info">{badge.label}</Badge>
					{/each}
				</div>
			{/if}

			<details class="group border border-border bg-muted/10" open={selectedLeagues.length === 0}>
				<summary class="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-football-blue">
					<span><span class="block text-sm font-semibold text-foreground">Răsfoiește catalogul complet</span><span class="mt-1 block text-xs text-muted-foreground">Caută mai întâi țări, apoi sunt afișate doar ligile lor.</span></span>
					<span class="text-xs font-medium text-football-blue group-open:hidden">Deschide</span><span class="hidden text-xs font-medium text-football-blue group-open:inline">Închide</span>
				</summary>
				<div class="space-y-6 border-t border-border p-4">
			<!-- Țări -->
			<div>
				<div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
					<div>
						<p class="text-sm font-medium text-foreground">Țări</p>
						<p class="mt-1 text-xs text-muted-foreground">
							{countries.length} țări din catalogul {catalogSource ?? 'fotbal OddsHarvester'}.
						</p>
						{#if catalogStatusLabel || catalogRefreshLabel}
							<div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground" aria-live="polite">
								{#if catalogStatusLabel}
									<Badge variant={catalogStatus === 'validated' ? 'success' : catalogStatus === 'discovered' ? 'warning' : 'danger'}>
										{catalogStatusLabel}
									</Badge>
								{/if}
								{#if catalogRefreshLabel}
									<span>Ultima actualizare {catalogRefreshLabel}</span>
								{/if}
							</div>
						{/if}
					</div>
					<Input
						id="country-catalog-search"
						label="Caută o țară"
						bind:value={countryQuery}
						placeholder="Caută țări"
						autocomplete="off"
						class="w-full sm:max-w-xs"
					/>
				</div>
				{#if loadingCatalog}
					<div class="space-y-2">
						<Skeleton class="h-6 w-full" />
						<Skeleton class="h-6 w-3/4" />
					</div>
				{:else if catalogLoadError}
					<div class="border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">Catalog indisponibil: {catalogLoadError} <Button variant="ghost" size="sm" onclick={fetchCatalog}>Reîncearcă</Button></div>
				{:else if countries.length === 0}
					<p class="text-sm text-muted-foreground">Catalogul este disponibil, dar nu conține țări pentru acest cont.</p>
				{:else if filteredCountries.length === 0}
					<p class="text-sm text-muted-foreground" role="status">Nicio țară nu corespunde căutării.</p>
				{:else}
					<div class="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
						{#each displayedCountries as country (country.country)}
							<label class={cn(
								'flex items-center space-x-2 p-2 border cursor-pointer transition-colors duration-200',
								selectedCountries.includes(country.country)
									? 'border-football-green bg-football-green/5'
									: 'border-border hover:bg-muted'
							)}>
								<input
									type="checkbox"
									checked={selectedCountries.includes(country.country)}
									onchange={() => toggleCountry(country.country)}
									class="w-4 h-4 accent-[hsl(var(--football-green))]"
								/>
								<span class="text-sm text-foreground">{country.country}</span>
								<span class="text-xs text-muted-foreground ml-auto font-mono">{country.leagues.length}</span>
							</label>
						{/each}
					</div>
					{#if !countryQuery.trim() && (hiddenCountryCount > 0 || showAllCountries)}
						<div class="mt-3 flex justify-center">
							<Button variant="ghost" size="sm" onclick={() => (showAllCountries = !showAllCountries)}>
								{showAllCountries ? 'Arată mai puține țări' : `Arată toate țările (${hiddenCountryCount} în plus)`}
							</Button>
						</div>
					{/if}
					{#if selectedCountryBadges.length > 0}
						<div class="flex flex-wrap gap-1.5 mt-2">
							{#each selectedCountryBadges as badge (badge.value)}
								<Badge variant="info">{badge.label}</Badge>
							{/each}
						</div>
					{/if}
					{#if selectedCountries.length === 1 && catalogValidationBatchSize > 0}
						<div class="mt-3 flex flex-wrap items-center gap-2 border border-dashed border-football-blue/40 bg-football-blue/5 p-3">
							<div class="min-w-0 flex-1">
								<p class="text-xs font-semibold text-foreground">Validează paginile de ligi în așteptare</p>
								<p class="mt-0.5 text-xs text-muted-foreground">
									Verifică până la {catalogValidationBatchSize} pagini de rezultate CotePortal pentru {selectedCountries[0]}; nu colectează cote și nu activează automat ligile.
								</p>
							</div>
							<Button variant="secondary" size="sm" disabled={validatingCatalog} onclick={validatePendingCatalogCandidates}>
								{validatingCatalog ? 'Se validează…' : `Validează ${catalogValidationBatchSize} în așteptare`}
							</Button>
						</div>
					{/if}
					{#if catalogValidationMessage}
						<p class="mt-2 text-xs text-football-green" role="status">{catalogValidationMessage}</p>
					{/if}
					{#if catalogValidationError}
						<p class="mt-2 text-xs text-destructive" role="alert">{catalogValidationError}</p>
					{/if}
				{/if}
			</div>

			<Separator />

			<!-- Leagues -->
			<div>
				<div class="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
					<div>
						<p class="text-sm font-medium text-foreground">Ligi OddsHarvester</p>
						<p class="mt-1 text-xs text-muted-foreground">
							{allLeagues.length} disponibile în catalog
							{#if selectedCountries.length > 0}
								· {selectedCountries.length} filtru de țări activ
							{/if}
						</p>
					</div>
					{#if filteredLeagues.length > 0}
						<button
							type="button"
							onclick={toggleAllLeagues}
							class="self-start text-xs text-football-blue transition-colors hover:text-football-green sm:self-auto"
						>
							{filteredLeagues.filter(isLeagueScrapeSelectable).every((l) => selectedLeagues.includes(l.id))
								? 'Deselectează ligile suportate vizibile'
								: 'Selectează ligile suportate vizibile'}
						</button>
					{/if}
				</div>
				{#if loadingCatalog}
					<div class="space-y-2">
						<Skeleton class="h-6 w-full" />
						<Skeleton class="h-6 w-2/3" />
					</div>
				{:else}
					<Input
						id="league-catalog-search"
						label="Caută o ligă"
						bind:value={leagueQuery}
						placeholder="Caută după țară, ligă sau slug OddsHarvester"
						autocomplete="off"
					/>
					{#if selectedCountries.length === 0 && !leagueQuery.trim()}
						<div class="mt-3 border border-dashed border-border bg-muted/20 p-5 text-center">
							<p class="text-sm font-medium text-foreground">Alege mai întâi o țară</p>
							<p class="mt-1 text-xs text-muted-foreground">Astfel catalogul rămâne compact, fără a afișa toate ligile simultan.</p>
						</div>
					{:else if displayedLeagueGroups.length === 0}
						<p class="mt-3 text-sm text-muted-foreground" role="status">
							Nicio ligă din catalog nu corespunde filtrului de țară sau căutării.
						</p>
					{:else}
						<div class="mt-3 space-y-4" aria-label="Catalog de ligi OddsHarvester">
							{#each displayedLeagueGroups as country (country.country)}
								<section class="overflow-hidden border border-border">
									<div class="flex items-center justify-between border-b border-border bg-muted/40 px-3 py-2">
										<h3 class="text-xs font-semibold uppercase tracking-wide text-foreground">{country.country}</h3>
										<span class="font-mono text-xs text-muted-foreground">{country.leagues.length}</span>
									</div>
									<div class="grid grid-cols-1 gap-px bg-border sm:grid-cols-2 xl:grid-cols-3">
										{#each country.leagues as league (league.id)}
											{@const selectable = isLeagueScrapeSelectable(league)}
											{@const availability = getLeagueCatalogAvailability(league)}
											<label class={cn(
												'flex min-h-12 items-center gap-2 bg-background p-3 transition-colors duration-200',
												selectable ? 'cursor-pointer hover:bg-muted' : 'cursor-not-allowed opacity-60',
												selectedLeagues.includes(league.id) ? 'bg-football-green/5' : ''
											)}>
												<input
													type="checkbox"
													checked={selectedLeagues.includes(league.id)}
													disabled={!selectable}
													onchange={() => toggleLeague(league.id)}
													class="h-4 w-4 shrink-0 accent-[hsl(var(--football-green))]"
											/>
											<span class="min-w-0 text-sm text-foreground">{league.name}</span>
													{#if availability}
														<Badge variant={availability === 'validated' ? 'success' : availability === 'unavailable' ? 'danger' : 'warning'} class="shrink-0 px-1.5 py-0 text-[10px]">
															{catalogAvailabilityLabel(availability)}
												</Badge>
											{:else if !selectable}
												<span class="text-[10px] uppercase tracking-wide text-muted-foreground">Indisponibilă</span>
											{/if}
												<span class="ml-auto shrink-0 font-mono text-xs text-muted-foreground">{league.matches_count}</span>
											</label>
										{/each}
									</div>
								</section>
							{/each}
						</div>
					{/if}
				{/if}
			</div>
				</div>
			</details>
		</div>
	</Card>

	<!-- Section 3: Historic and future ranges -->
	<Card id="coverage" title="2. Stabilește acoperirea" variant="data" class="order-3 scroll-mt-24">
		<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
			<!-- Past Istoric -->
			<div class={cn('space-y-4 border p-4', pastEnabled ? 'border-football-blue/40 bg-football-blue/5' : 'border-border bg-muted/10')}>
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-semibold text-foreground">Rezultate istorice</p>
						<p class="mt-1 text-xs text-muted-foreground">Antrenează și validează modelele folosind sezoane anterioare.</p>
					</div>
					<label class="relative inline-flex items-center cursor-pointer">
						<input
							type="checkbox"
							aria-label="Include rezultatele istorice"
							checked={pastEnabled}
							onchange={() => (pastEnabled = !pastEnabled)}
							class="sr-only peer"
						/>
						<div class="w-9 h-5 bg-muted border border-border peer-checked:bg-football-green peer-checked:border-football-green transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-foreground after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full"></div>
					</label>
				</div>
				{#if pastEnabled}
					<div class="space-y-4" transition:slide={{ duration: 160 }}>
						<div>
							<p class="mb-2 text-xs font-medium text-muted-foreground">Interval rapid</p>
							<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
								{#each historyPresetOptions.slice(0, 4) as option (option.value)}
									<button
										type="button"
										class={cn('border px-3 py-2 text-xs font-semibold transition-colors', historyPresetYears === option.value ? 'border-football-blue bg-football-blue text-background' : 'border-border bg-background hover:bg-muted')}
									onclick={() => applyHistoryPreset(option.value)}
									>{option.label}</button>
								{/each}
							</div>
						</div>
						<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
							<div>
								<label for="scrape-past-from" class="mb-1 block text-xs text-muted-foreground">From</label>
								<Input id="scrape-past-from" type="date" bind:value={pastFrom} />
							</div>
							<div>
								<label for="scrape-past-to" class="mb-1 block text-xs text-muted-foreground">To</label>
								<Input id="scrape-past-to" type="date" bind:value={pastTo} />
							</div>
						</div>
						<div class="max-w-48">
							<label for="scrape-history-pages" class="mb-1 block text-xs text-muted-foreground">Pagini pe sezon</label>
							<Input id="scrape-history-pages" type="number" min="1" max="50" bind:value={historicMaxPages} />
						</div>
						<div class="border border-border bg-background/60 p-3 text-xs text-muted-foreground">
							{#if historicSeasonPreview.length > 0}
								<p>
									<span class="font-semibold text-foreground">{historicSeasonPreview.length} sezoane:</span>
									<span class="font-mono text-foreground">{historicSeasonPreview.join(', ')}</span>
								</p>
							{:else}
								<p>Alege un interval pentru previzualizarea sezoanelor.</p>
							{/if}
						</div>
						<details class="group border-t border-border pt-3">
							<summary class="cursor-pointer list-none text-xs font-semibold text-football-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-football-blue">Interval personalizat <span class="group-open:hidden">+</span><span class="hidden group-open:inline">−</span></summary>
							<div class="mt-3 space-y-3">
								<div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
									<Input label="Zile" name="scrape-historic-zile" type="number" min="0" bind:value={historicDays} />
									<Input label="Săptămâni" name="scrape-historic-weeks" type="number" min="0" bind:value={historicWeeks} />
									<Input label="Luni" name="scrape-historic-months" type="number" min="0" bind:value={historicMonths} />
									<Input label="Ani" name="scrape-historic-years" type="number" min="0" bind:value={historicYears} />
								</div>
								<Button variant="secondary" size="sm" onclick={applyHistoricInterval} disabled={historicIntervalDays <= 0}>Aplică intervalul personalizat</Button>
							</div>
						</details>
					</div>
				{/if}
			</div>

			<!-- Future Mecies -->
			<div class={cn('space-y-4 border p-4', futureEnabled ? 'border-football-green/40 bg-football-green/5' : 'border-border bg-muted/10')}>
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm font-semibold text-foreground">Meciuri viitoare</p>
						<p class="mt-1 text-xs text-muted-foreground">Colectează următoarele meciuri și cotele curente.</p>
					</div>
					<label class="relative inline-flex items-center cursor-pointer">
						<input
							type="checkbox"
							aria-label="Include meciurile viitoare"
							checked={futureEnabled}
							onchange={() => (futureEnabled = !futureEnabled)}
							class="sr-only peer"
						/>
						<div class="w-9 h-5 bg-muted border border-border peer-checked:bg-football-green peer-checked:border-football-green transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-foreground after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full"></div>
					</label>
				</div>
				{#if futureEnabled}
					<div class="space-y-4" transition:slide={{ duration: 160 }}>
						<div>
							<p class="mb-2 text-xs font-medium text-muted-foreground">Orizont rapid</p>
							<div class="grid grid-cols-3 gap-2">
								{#each [1, 7, 30] as zile (zile)}
									<button type="button" class={cn('border px-3 py-2 text-xs font-semibold transition-colors', futureIntervalDays === zile ? 'border-football-green bg-football-green text-background' : 'border-border bg-background hover:bg-muted')} onclick={() => setFuturePreset(zile)}>{zile === 1 ? 'Mâine' : `${zile} zile`}</button>
								{/each}
							</div>
						</div>
						<div class="max-w-48">
							<Input label="Viitor zile" name="scrape-future-zile" type="number" min="0" bind:value={futureDays} />
						</div>
						<div class="border border-border bg-background/60 p-3 text-xs text-muted-foreground">Colectarea va acoperi următoarele <span class="font-mono font-semibold text-foreground">{futureIntervalDays}</span> zile.</div>
						<details class="group border-t border-border pt-3">
							<summary class="cursor-pointer list-none text-xs font-semibold text-football-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-football-blue">Orizont personalizat mai lung <span class="group-open:hidden">+</span><span class="hidden group-open:inline">−</span></summary>
							<div class="mt-3 grid grid-cols-3 gap-2">
								<Input label="Săptămâni" name="scrape-future-weeks" type="number" min="0" bind:value={futureWeeks} />
								<Input label="Luni" name="scrape-future-months" type="number" min="0" bind:value={futureMonths} />
								<Input label="Ani" name="scrape-future-years" type="number" min="0" bind:value={futureYears} />
							</div>
						</details>
					</div>
				{/if}
			</div>
		</div>
	</Card>

	<!-- Section 4: Controls -->
	<Card id="controls" title="3. Verifică și pornește" variant="data" class="order-4 scroll-mt-24">
		<div class="space-y-4">
			<div class="grid gap-3 sm:grid-cols-3">
				<div class="border border-border bg-muted/20 p-3">
					<p class="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Arie</p>
					<p class="mt-1 text-sm font-semibold text-foreground">{selectedLeagues.length} {selectedLeagues.length === 1 ? 'ligă' : 'ligi'}</p>
					<p class="mt-1 truncate text-xs text-muted-foreground">{selectedCountries.join(', ') || 'Alege o presetare de mai sus'}</p>
				</div>
				<div class="border border-border bg-muted/20 p-3">
					<p class="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Istoric</p>
					<p class="mt-1 text-sm font-semibold text-foreground">{pastEnabled ? `${historicSeasonPreview.length} sezoane` : 'Dezactivat'}</p>
					<p class="mt-1 text-xs text-muted-foreground">{pastEnabled ? `${pastFrom || '—'} → ${pastTo || '—'}` : 'Fără joburi istorice'}</p>
				</div>
				<div class="border border-border bg-muted/20 p-3">
					<p class="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Viitor</p>
					<p class="mt-1 text-sm font-semibold text-foreground">{futureEnabled ? `${futureIntervalDays} zile` : 'Dezactivat'}</p>
					<p class="mt-1 text-xs text-muted-foreground">Motor: {scraperEngine === 'auto' ? 'Automat' : scraperEngine}</p>
				</div>
			</div>

			<details class="group border border-border bg-muted/10">
				<summary class="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-football-blue">
					<span><span class="block text-sm font-semibold text-foreground">Setări avansate de rulare</span><span class="mt-1 block text-xs text-muted-foreground">Programarea, motorul de colectare și gestionarea duplicatelor folosesc valori sigure.</span></span>
					<span class="text-xs font-medium text-football-blue group-open:hidden">Personalizează</span><span class="hidden text-xs font-medium text-football-blue group-open:inline">Ascunde</span>
				</summary>
				<div class="space-y-4 border-t border-border p-4">
			<!-- Colectare automată -->
			<div class="flex items-center justify-between">
				<div>
					<p class="text-sm font-medium text-foreground">Colectare automată</p>
					<p class="text-xs text-muted-foreground">Rulează automat joburile de colectare după o programare</p>
				</div>
				<label class="relative inline-flex items-center cursor-pointer">
					<input
						type="checkbox"
						aria-label="Activează programarea automată a colectării"
						checked={autoScrape}
						onchange={() => (autoScrape = !autoScrape)}
						class="sr-only peer"
					/>
					<div class="w-9 h-5 bg-muted border border-border peer-checked:bg-football-green peer-checked:border-football-green transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-foreground after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full"></div>
				</label>
			</div>
			{#if autoScrape}
				<div class="space-y-3 border-l-2 border-football-green/30 pl-4" transition:slide={{ duration: 200 }}>
					<div class="flex flex-col gap-2 sm:flex-row sm:items-end">
					<div class="flex-1">
						<label for="scrape-auto-interval" class="text-xs text-muted-foreground mb-1 block">Interval</label>
						<Input id="scrape-auto-interval" type="number" bind:value={autoIntervalNumber} placeholder="24" />
					</div>
					<div class="flex-1">
						<Select bind:value={autoIntervalUnit} options={intervalUnitOptions} />
					</div>
					</div>
					<div class="flex flex-col gap-2 rounded border border-football-green/30 bg-football-green/5 p-3 sm:flex-row sm:items-center sm:justify-between">
						<p class="text-xs leading-5 text-muted-foreground">Salvează programarea cu competițiile și acoperirea selectate mai sus. Pașii opționali de predicții și bilete rămân în Automatizare.</p>
						<Button variant="secondary" size="sm" onclick={saveAutomatScrapeAction} disabled={!interactive || savingScheduledJob}>
							{savingScheduledJob ? 'Se salvează...' : 'Salvează programarea automată'}
						</Button>
					</div>
				</div>
			{/if}

			<Separator />

			<div class="space-y-2">
				<Select
					bind:value={scraperEngine}
					label="Motor de colectare"
					name="scrape-engine"
					options={scraperEngineOptions}
				/>
				<p class="text-xs text-muted-foreground">
					Modul automat încearcă Scrapling pentru fluxurile de fotbal și piețele principale, apoi revine la Playwright când solicitarea nu este suportată. Pentru toate piețele sau istoricul cotelor folosește Playwright.
				</p>
			</div>

			<Separator />

			<!-- Dedup -->
			<div class="flex items-center justify-between">
				<div>
					<p class="text-sm font-medium text-foreground">Omite meciurile existente</p>
					<p class="text-xs text-muted-foreground">Evită recolectarea datelor deja din baza de date</p>
				</div>
				<label class="relative inline-flex items-center cursor-pointer">
					<input
						type="checkbox"
						aria-label="Omite meciurile existente"
						checked={dedupSkip}
						onchange={() => (dedupSkip = !dedupSkip)}
						class="sr-only peer"
					/>
					<div class="w-9 h-5 bg-muted border border-border peer-checked:bg-football-green peer-checked:border-football-green transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-foreground after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full"></div>
				</label>
			</div>

			{#if unsupportedControlNotes.length > 0}
				<div class="space-y-1 border border-football-gold/30 bg-football-gold/10 p-3 text-xs text-football-gold">
					{#each unsupportedControlNotes as note (note)}
						<p>{note}</p>
					{/each}
				</div>
			{/if}
				</div>
			</details>

			<div class="space-y-3">
				{#if pastEnabled && selectedScrapeLeagueSlugs.length === 0}
					<p class="rounded border border-football-gold/30 bg-football-gold/10 p-3 text-xs leading-5 text-football-gold" role="status">Colectarea istorică necesită cel puțin o ligă suportată. Alege liga la pasul 1 înainte de pornire.</p>
				{/if}
				{#if largeScopeWarning}
					<div class="space-y-3 rounded border border-football-gold/40 bg-football-gold/10 p-3" role="alert">
						<div>
							<p class="text-sm font-semibold text-foreground">Arie mare de colectare istorică</p>
							<p class="mt-1 text-xs leading-5 text-muted-foreground">{largeScopeWarning.message} Joburile rulează în fundal și pot dura mult sau pot încărca sursa. Restrânge aria dacă nu este intenționat.</p>
						</div>
						<label class="flex cursor-pointer items-start gap-2 text-xs leading-5 text-foreground">
							<input
								type="checkbox"
								checked={isLargeScopeAcknowledged}
								onchange={(event) => {
									acknowledgedLargeScopeKey = (event.currentTarget as HTMLInputElement).checked
										? largeScopeWarning?.key ?? null
										: null;
								}}
								class="mt-0.5 h-4 w-4 shrink-0 accent-[hsl(var(--football-green))]"
							/>
							<span>Înțeleg că se va pune în coadă un lot mare de colectări istorice.</span>
						</label>
					</div>
				{/if}
				{#if submitSuccess}
					<div class="p-3 text-sm bg-football-green/10 border border-football-green/30 text-football-green" transition:slide={{ duration: 200 }}>
						{submitSuccess}
					</div>
				{/if}
				{#if submitPartial}
					<div class="space-y-3 border border-football-gold/30 bg-football-gold/10 p-3 text-sm text-foreground" role="status">
						<p>{submitPartial}</p>
						{#if failedScrapeAttempts.length}
							<ul class="space-y-1 text-xs text-muted-foreground">
								{#each failedScrapeAttempts as attempt (attempt.label)}
									<li><span class="font-medium text-foreground">{attempt.label}:</span> {attempt.reason}</li>
								{/each}
							</ul>
							<Button variant="secondary" size="sm" disabled={retryingFailedScrapes} onclick={retryFailedScrapes}>
								{retryingFailedScrapes ? 'Se reia...' : 'Reîncearcă doar părțile eșuate'}
							</Button>
						{/if}
					</div>
				{/if}
				{#if submitError}
					<div class="p-3 text-sm bg-destructive/10 border border-destructive/30 text-destructive" transition:slide={{ duration: 200 }}>
						{submitError}
					</div>
				{/if}
				{#if !canStartScrape && !submitting}
					<p class="text-center text-xs text-muted-foreground">Selectează cel puțin o ligă suportată și păstrează activă o acoperire.</p>
				{/if}
				<Button
					variant="glow"
					size="lg"
					fullWidth
					disabled={!canStartScrape}
					onclick={startScrape}
				>
					{#if submitting}
						<span class="flex items-center justify-center gap-2">
							<span class="h-4 w-4 border-2 border-foreground border-t-transparent animate-spin"></span>
							Se pornește...
						</span>
					{:else}
						Pornește colectarea
					{/if}
				</Button>
			</div>

			<Separator />

			<details id="logs" class="group rounded border border-border bg-muted/10 p-3" ontoggle={handleLogsDetailsToggle}>
				<summary class="flex cursor-pointer list-none items-center justify-between gap-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-football-blue">
					<span><span class="block text-sm font-medium text-foreground">Jurnalele joburilor</span><span class="mt-1 block text-xs text-muted-foreground">Inspectează jurnalul persistent, pas cu pas, numai când un job necesită atenție.</span></span>
					<span class="shrink-0 text-xs font-medium text-football-blue group-open:hidden">Arată</span><span class="hidden shrink-0 text-xs font-medium text-football-blue group-open:inline">Ascunde</span>
				</summary>
				<div class="mt-3">
					{#if logsPanelDeschide}
						<div class="space-y-3 border border-border bg-muted/30 p-3" transition:slide={{ duration: 200 }}>
							{#if jobs.length > 0}
								<div class="flex flex-wrap gap-2">
									{#each jobs.slice(0, 12) as job (job.id)}
										<button
											type="button"
											class={cn(
												'border px-2.5 py-1 text-xs transition-colors',
												selectedLogJobId === job.id
													? 'border-football-green bg-football-green/10 text-football-green'
													: 'border-border bg-background/70 text-muted-foreground hover:text-foreground'
											)}
											onclick={() => openLogsForJob(job.id)}
										>
											#{job.id} · {jobLabel(job)}
										</button>
									{/each}
								</div>
							{/if}
							{#if loadingJobLogs}
								<p class="text-sm text-muted-foreground">Se încarcă jurnalele jobului...</p>
							{:else if jobLogsError}
								<p class="text-sm text-destructive">{jobLogsError}</p>
							{:else if jobLogs.length === 0}
								<p class="text-sm text-muted-foreground">Încă nu există jurnale pentru job.</p>
							{:else}
								<div class="max-h-64 space-y-2 overflow-y-auto pr-1">
									{#each jobLogs as log (log.id)}
										<div class="space-y-2 border border-border bg-background/70 px-3 py-2 text-xs">
											<div class="flex flex-wrap items-center gap-2">
												<Badge variant={logLevelVariant(log.level)}>#{log.id} · {log.level}</Badge>
												<span class="font-mono text-foreground">{log.action}</span>
												<span class="text-muted-foreground">Job #{log.job_id}</span>
												<span class="ml-auto text-muted-foreground">{new Date(log.created_at).toLocaleString()}</span>
											</div>
											<p class="text-foreground">{log.message}</p>
											{#if log.metadata_json && Object.keys(log.metadata_json).length > 0}
												<pre class="max-h-32 overflow-x-auto overflow-y-auto border border-border bg-muted/50 p-2 font-mono text-[11px] text-muted-foreground">{JSON.stringify(log.metadata_json, null, 2)}</pre>
											{/if}
										</div>
									{/each}
								</div>
							{/if}
					</div>
				{/if}
				</div>
			</details>
		</div>
	</Card>

	<!-- Section 4: Job Table -->
	<Card id="jobs" title="Joburi recente de colectare" variant="data" class="order-5 scroll-mt-24">
		{#if loadingJobs}
			<div class="space-y-3">
				<Skeleton class="h-12 w-full" />
				<Skeleton class="h-12 w-full" />
				<Skeleton class="h-12 w-full" />
			</div>
		{:else if jobsLoadError}
			<div class="border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive" role="alert">Istoricul joburilor nu este disponibil: {jobsLoadError} <Button variant="ghost" size="sm" onclick={fetchJobs}>Reîncearcă</Button></div>
		{:else if jobs.length === 0}
			<p class="text-sm text-muted-foreground text-center py-8">Încă nu există joburi de colectare. Acesta este un rezultat gol, nu o eroare.</p>
		{:else}
			<div class="overflow-x-auto">
				<table class="w-full text-sm">
					<thead class="text-xs uppercase bg-muted border-b border-border text-muted-foreground">
						<tr>
							<th class="px-3 py-2 text-left">Nume</th>
							<th class="px-3 py-2 text-left">Stare</th>
							<th class="px-3 py-2 text-left">Creat</th>
							<th class="px-3 py-2 text-left">Durată</th>
							<th class="px-3 py-2 text-left">Progres</th>
							<th class="px-3 py-2 w-8"></th>
						</tr>
					</thead>
					<tbody>
						{#each jobs as job (job.id)}
							<tr
								class="border-b border-border transition-colors duration-200 hover:bg-muted cursor-pointer"
								onclick={() => toggleExpandJob(job.id)}
							>
								<td class="px-3 py-2.5 text-foreground font-medium">
									{jobLabel(job)}
								</td>
								<td class="px-3 py-2.5">
									<Badge variant={statusVariant(job.status)}>{statusLabel(job.status)}</Badge>
								</td>
								<td class="px-3 py-2.5 text-muted-foreground font-mono text-xs">
									{new Date(job.created_at).toLocaleString()}
								</td>
								<td class="px-3 py-2.5 font-mono text-xs text-muted-foreground">
									{formatDuration(job.created_at, job.completed_at)}
								</td>
								<td class="px-3 py-2.5">
									<div class="flex items-center gap-2">
										<div class="flex-1 h-1.5 bg-muted">
											<div
												class="h-1.5 bg-football-green transition-all duration-500"
												style="width: {jobProgress(job)}%"
											></div>
										</div>
										<span class="text-xs font-mono text-muted-foreground w-8 text-right">{jobProgress(job)}%</span>
									</div>
								</td>
								<td class="px-3 py-2.5 text-muted-foreground">
									<span class="text-xs">{expandedJobId === job.id ? '▲' : '▼'}</span>
								</td>
							</tr>
							{#if expandedJobId === job.id}
								<tr transition:slide={{ duration: 200 }}>
									<td colspan="6" class="px-3 py-3 bg-muted/50">
										<div class="grid grid-cols-2 gap-4 text-xs">
											<div>
												<span class="text-muted-foreground">ID job:</span>
												<span class="ml-2 font-mono text-foreground">{job.id}</span>
											</div>
											<div>
												<span class="text-muted-foreground">Tip:</span>
												<span class="ml-2 font-mono text-foreground">{jobLabel(job)}</span>
											</div>
											{#if job.error}
												<div class="col-span-2">
													<span class="text-destructive">{job.error}</span>
												</div>
											{/if}
											{#if job.params && Object.keys(job.params).length > 0}
												<div class="col-span-2">
													<span class="text-muted-foreground">Parametri:</span>
													<pre class="mt-1 p-2 bg-background border border-border font-mono text-xs overflow-x-auto">{JSON.stringify(job.params, null, 2)}</pre>
												</div>
											{/if}
											<div class="col-span-2">
												<Button variant="secondary" size="sm" onclick={() => openLogsForJob(job.id)}>
													Vezi jurnalul complet
												</Button>
											</div>
										</div>
									</td>
								</tr>
							{/if}
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</Card>

</div>
