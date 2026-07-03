<script lang="ts">
	import { onMount } from 'svelte';
	import { fade, slide } from 'svelte/transition';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Skeleton from '$lib/components/ui/skeleton/skeleton.svelte';
	import Separator from '$lib/components/ui/separator/separator.svelte';
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
		isLeagueScrapeSelectable
	} from './catalog.helpers';

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

	type WorldCupDifficultyTicket = {
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
		tickets: WorldCupDifficultyTicket[];
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

	function localDateString(date: Date): string {
		const year = date.getFullYear();
		const month = String(date.getMonth() + 1).padStart(2, '0');
		const day = String(date.getDate()).padStart(2, '0');
		return `${year}-${month}-${day}`;
	}

	function tomorrowLocalDate(): string {
		const date = new Date();
		date.setDate(date.getDate() + 1);
		return localDateString(date);
	}

	// --- State ---
	let countries = $state<Country[]>([]);
	let allLeagues = $state<LeagueInfo[]>([]);
	let selectedCountries = $state<string[]>([]);
	let selectedLeagues = $state<string[]>([]);
	let loadingCatalog = $state(true);

	// Past History
	let pastEnabled = $state(true);
	let pastFrom = $state('');
	let pastTo = $state('');
	let historyPresetYears = $state('10');
	let historicMaxPages = $state('3');
	let historicDays = $state('0');
	let historicWeeks = $state('0');
	let historicMonths = $state('0');
	let historicYears = $state('10');

	// Future Matches
	let futureEnabled = $state(true);
	let futureDays = $state('7');
	let futureWeeks = $state('0');
	let futureMonths = $state('0');
	let futureYears = $state('0');

	// Options
	let autoScrape = $state(false);
	let autoIntervalNumber = $state('24');
	let autoIntervalUnit = $state('Hours');
	let autoRunPredictions = $state(false);
	let autoPredictionStrategyIds = $state('');
	let autoPredictionMarkets = $state<string[]>(['1x2']);
	let autoCreateTickets = $state(false);
	let autoTicketCount = $state('3');
	let autoTicketDifficulty = $state('balanced');
	let autoTicketMinOdds = $state('1.20');
	let autoTicketMaxOdds = $state('5.00');
	let autoTicketStake = $state('10');
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
	let logsPanelOpen = $state(false);
	let loadingJobLogs = $state(false);
	let selectedLogJobId = $state<number | null>(null);
	let jobLogs = $state<ScrapeJobLogEntry[]>([]);
	let jobLogsError = $state('');

	// Submit
	let submitting = $state(false);
	let submitSuccess = $state('');
	let submitError = $state('');
	let pipelineRunning = $state(false);
	let pipelineError = $state('');
	let pipelineResult = $state<WorldCupPipelineResponse | null>(null);
	let pipelineStartedJobId = $state<number | null>(null);
	let pipelineTargetDate = $state(tomorrowLocalDate());
	let pipelineTicketCount = $state('5');
	let pipelineTicketStake = $state('10');
	let pipelineAllowExperimental = $state(true);

	let pollTimer: ReturnType<typeof setInterval> | null = null;

	// --- Derived ---
	const filteredLeagues = $derived(
		selectedCountries.length === 0
			? allLeagues
			: countries
					.filter((c) => selectedCountries.includes(c.country))
					.flatMap((c) => c.leagues)
	);

	const selectedCountryBadges = $derived(
		selectedCountries.map((c) => ({
			value: c,
			label: c
		}))
	);

	const selectedLeagueBadges = $derived(
		selectedLeagues.map((id) => {
			const league = allLeagues.find((l) => l.id === id);
			return { value: id, label: league?.name ?? id };
		})
	);

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

	const intervalUnitOptions = [
		{ value: 'Hours', label: 'Hours' },
		{ value: 'Days', label: 'Days' },
		{ value: 'Weeks', label: 'Weeks' }
	];

	const scraperEngineOptions = [
		{ value: 'auto', label: 'Auto: Scrapling then Playwright fallback' },
		{ value: 'playwright', label: 'Playwright only (safest compatibility)' },
		{ value: 'scrapling-http', label: 'Scrapling HTTP only (fast core markets)' },
		{ value: 'scrapling-stealth', label: 'Scrapling stealth browser only' }
	];

	const predictionMarketOptions = [
		{ value: '1x2', label: '1X2' },
		{ value: 'over_under_2.5', label: 'Over/Under 2.5' },
		{ value: 'btts', label: 'BTTS' }
	];

	const historyPresetOptions = HISTORY_PRESET_OPTIONS;

	const historicSeasonPreview = $derived(buildHistoricSeasons(pastFrom, pastTo, buildScrapeLeagueSlugs(allLeagues, selectedLeagues)));

	const historicIntervalDays = $derived(
		intervalToDays(historicDays, historicWeeks, historicMonths, historicYears)
	);

	const futureIntervalDays = $derived(
		intervalToDays(futureDays, futureWeeks, futureMonths, futureYears)
	);

	const unsupportedControlNotes = $derived.by(() => {
		const notes: string[] = [];
		if (dedupSkip) {
			notes.push('Avoid re-scraping is enforced by the backend for duplicate completed jobs with the same scrape inputs.');
		}
		if (autoScrape) {
			notes.push('Autoscrape can be saved as a persistent /api/v1/jobs action with the Save autoscrape button above.');
		}
		if (autoRunPredictions) {
			notes.push('Scrape -> predict orchestration will queue predictions automatically after each scheduled scrape.');
		}
		if (autoCreateTickets) {
			notes.push('Scheduled orchestration will also create tickets from the latest prediction pool after predictions finish.');
		}
		if (pastEnabled && (positiveInteger(historicDays) > 0 || positiveInteger(historicWeeks) > 0 || positiveInteger(historicMonths) > 0)) {
			notes.push('Historic day/week/month inputs are converted to a date range and seasons; OddsHarvester historic execution supports seasons, not exact historic day windows.');
		}
		return notes;
	});

	// --- Data Fetching ---
	async function fetchCatalog() {
		try {
			const res = await fetch(`${BASE_URL}/api/v1/catalog/countries`, { credentials: 'include' });
			if (res.ok) {
				countries = await res.json();
				allLeagues = countries.flatMap((c) => c.leagues);
			}
		} catch {
			// silently handle — catalog may not be available yet
		} finally {
			loadingCatalog = false;
		}
	}

	async function fetchJobs() {
		try {
			const res = await fetch(`${BASE_URL}/api/v1/data/scrape`, { credentials: 'include' });
			if (res.ok) {
				jobs = await res.json();
				if (selectedLogJobId === null && jobs.length > 0) {
					selectedLogJobId = jobs[0].id;
				}
			}
		} catch {
			// silently handle
		} finally {
			loadingJobs = false;
		}

		if (logsPanelOpen) {
			void fetchJobLogs(selectedLogJobId ?? jobs[0]?.id ?? null);
		}
	}

	async function fetchScheduledJobs() {
		loadingScheduledJobs = true;
		scheduledJobsError = '';
		try {
			scheduledJobs = await jobsApi.getScheduledJobs();
		} catch (err) {
			scheduledJobsError = err instanceof ApiClientError ? err.message : 'Scheduled scraping jobs are unavailable';
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
			scheduledJobsError = err instanceof ApiClientError ? err.message : 'Could not toggle scheduled scraping job';
		}
	}

	async function saveAutomaticScrapeAction() {
		savingScheduledJob = true;
		scheduledJobsError = '';
		try {
			const scrapeLeagueSlugs = buildScrapeLeagueSlugs(allLeagues, selectedLeagues);
			const strategyIds = autoPredictionStrategyIds
				.split(',')
				.map((value) => Number.parseInt(value.trim(), 10))
				.filter((value) => Number.isFinite(value) && value > 0);
			if (autoRunPredictions && strategyIds.length === 0) {
				scheduledJobsError = 'Add at least one strategy id before saving scrape → predict automation';
				return;
			}
			const orchestrationTaskType = autoRunPredictions
				? autoCreateTickets
					? 'scrape_predict_tickets'
					: 'scrape_then_predict'
				: 'scrape_odds';
			const created = await jobsApi.createScheduledJob({
				name: `${autoRunPredictions ? 'Autoscrape + predict' : 'Autoscrape'} ${selectedLeagues.length > 0 ? selectedLeagues.length : 'all'} league${selectedLeagues.length === 1 ? '' : 's'}`,
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
								min_odds: parseFloat(autoTicketMinOdds) || 1.01,
								max_odds: parseFloat(autoTicketMaxOdds) || 100,
								stake: parseFloat(autoTicketStake) || 10
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
			scheduledJobsError = err instanceof ApiClientError ? err.message : 'Could not save automatic scraping action';
		} finally {
			savingScheduledJob = false;
		}
	}

	async function fetchJobLogs(jobId = selectedLogJobId) {
		if (jobId === null) {
			jobLogs = [];
			jobLogsError = 'Select a scrape job to view its logs';
			return;
		}

		selectedLogJobId = jobId;
		loadingJobLogs = true;
		jobLogsError = '';
		try {
			const res = await fetch(`${BASE_URL}/api/v1/data/scrape/${jobId}/logs?page=1&per_page=200`, { credentials: 'include' });
			if (!res.ok) {
				const err = await res.json().catch(() => ({ detail: 'Scrape job logs are unavailable' }));
				throw new Error(err.detail || `HTTP ${res.status}`);
			}
			const payload = (await res.json()) as ScrapeJobLogPage;
			jobLogs = payload.items;
		} catch (err) {
			jobLogs = [];
			jobLogsError = err instanceof Error ? err.message : 'Scrape job logs are unavailable';
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
		const days = historicIntervalDays;
		if (days <= 0) return;
		const end = new Date();
		const start = new Date();
		start.setDate(start.getDate() - days);
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
			const unitMap: Record<string, number> = { Hours: 1, Days: 24, Weeks: 168 };
			params.auto_interval_hours = num * (unitMap[autoIntervalUnit] ?? 1);
		}

		return params;
	}

	async function createAndExecuteScrapeJob(params: Record<string, unknown>, league?: string) {
		const createRes = await fetch(`${BASE_URL}/api/v1/data/scrape`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			credentials: 'include',
			body: JSON.stringify({ job_type: 'scrape_odds', league, params })
		});

		if (!createRes.ok) {
			const err = await createRes.json().catch(() => ({ detail: 'Failed to create job' }));
			throw new Error(err.detail || `HTTP ${createRes.status}`);
		}

		const createdJob = (await createRes.json()) as { id: number };
		const executeRes = await fetch(`${BASE_URL}/api/v1/data/scrape/${createdJob.id}/execute-background`, {
			method: 'POST',
			credentials: 'include'
		});

		if (!executeRes.ok) {
			const err = await executeRes.json().catch(() => ({ detail: 'Failed to execute job' }));
			throw new Error(err.detail || `HTTP ${executeRes.status}`);
		}

		return createdJob.id;
	}

	async function startScrape() {
		submitting = true;
		submitError = '';
		submitSuccess = '';

		const scrapeLeagueSlugs = buildScrapeLeagueSlugs(allLeagues, selectedLeagues);
		if (selectedLeagues.length > 0 && scrapeLeagueSlugs.length !== selectedLeagues.length) {
			submitError = 'Some selected leagues are not supported by the scraper yet';
			submitting = false;
			return;
		}
		if (pastEnabled && scrapeLeagueSlugs.length === 0) {
			submitError = 'Select at least one supported league before scraping historical seasons';
			submitting = false;
			return;
		}
		if (
			pastEnabled &&
			scrapeLeagueSlugs.includes('world-cup') &&
			scrapeLeagueSlugs.some((slug) => slug !== 'world-cup')
		) {
			submitError = 'For historical scraping, run World Cup separately from seasonal leagues';
			submitting = false;
			return;
		}

		try {
			const baseParams = buildBaseScrapeParams(scrapeLeagueSlugs);
			const createdJobIds: number[] = [];

			if (pastEnabled && (!pastFrom || !pastTo)) {
				applyHistoricInterval();
			}

			if (pastEnabled && pastFrom && pastTo) {
				const seasons = buildHistoricSeasons(pastFrom, pastTo, scrapeLeagueSlugs);
				if (seasons.length === 0) {
					throw new Error('No historical seasons found for the selected range');
				}

				const maxPages = Number.parseInt(historicMaxPages, 10) || 3;
				const isWorldCupOnly = scrapeLeagueSlugs.length > 0 && scrapeLeagueSlugs.every((slug) => slug === 'world-cup');
				for (const season of seasons) {
					const jobId = await createAndExecuteScrapeJob(
						{
							...baseParams,
							command: 'historic',
							season,
							past_from: pastFrom,
							past_to: pastTo,
							historic_range_days: historicIntervalDays || undefined,
							history_years: Number.parseInt(historyPresetYears, 10) || undefined,
							max_pages: isWorldCupOnly ? Math.max(maxPages, 3) : maxPages,
							timeout_seconds: isWorldCupOnly ? 2400 : undefined
						},
						scrapeLeagueSlugs.length === 1 ? scrapeLeagueSlugs[0] : undefined
					);
					createdJobIds.push(jobId);
				}
			}

			if (futureEnabled && futureIntervalDays > 0) {
				const jobId = await createAndExecuteScrapeJob({
					...baseParams,
					command: 'upcoming',
					future_days: futureIntervalDays,
					future_range: {
						days: positiveInteger(futureDays),
						weeks: positiveInteger(futureWeeks),
						months: positiveInteger(futureMonths),
						years: positiveInteger(futureYears)
					}
				});
				createdJobIds.push(jobId);
			}

			if (createdJobIds.length === 0) {
				throw new Error('Enable past history or future matches before starting scrape');
			}

			submitSuccess = `Queued ${createdJobIds.length} scrape job${createdJobIds.length === 1 ? '' : 's'} successfully`;
			await fetchJobs();
			setTimeout(() => (submitSuccess = ''), 4000);
		} catch (err) {
			submitError = err instanceof Error ? err.message : 'Failed to start scrape';
		} finally {
			submitting = false;
		}
	}

	async function runWorldCupPipeline() {
		pipelineRunning = true;
		pipelineError = '';
		pipelineResult = null;

		try {
			const targetStart = new Date(`${pipelineTargetDate}T00:00:00`);
			const targetEnd = new Date(`${pipelineTargetDate}T23:59:59.999`);
			const ticketCount = Number.parseInt(pipelineTicketCount, 10) || 5;
			const ticketStake = Number.parseFloat(pipelineTicketStake) || 10;
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
					ticket_stake: ticketStake,
					create_tickets: true,
					allow_experimental_tickets: pipelineAllowExperimental,
					training_limit: 120
				})
			});

			if (!res.ok) {
				const err = await res.json().catch(() => ({ detail: 'World Cup pipeline failed' }));
				throw new Error(err.detail || `HTTP ${res.status}`);
			}

			const job = (await res.json()) as ScrapeJob;
			pipelineStartedJobId = job.id;
			jobs = [job, ...jobs.filter((entry) => entry.id !== job.id)];
			await fetchJobs();
		} catch (err) {
			pipelineError = err instanceof Error ? err.message : 'World Cup pipeline failed';
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

	function toggleLogsPanel() {
		logsPanelOpen = !logsPanelOpen;
		if (logsPanelOpen && jobLogs.length === 0) {
			void fetchJobLogs(selectedLogJobId ?? jobs[0]?.id ?? null);
		}
	}

	function openLogsForJob(jobId: number) {
		selectedLogJobId = jobId;
		logsPanelOpen = true;
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

	function logLevelVariant(level: string): 'default' | 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
		const normalized = level.toLowerCase();
		if (normalized === 'error') return 'danger';
		if (normalized === 'warning' || normalized === 'warn') return 'warning';
		if (normalized === 'debug') return 'neutral';
		return 'info';
	}

	function jobLabel(job: ScrapeJob): string {
		return job.job_type || 'unknown';
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

<div class="mx-auto max-w-4xl space-y-8 overflow-hidden" transition:fade={{ duration: 200 }}>
		<div>
			<h1 class="text-2xl font-extrabold font-sport text-foreground">SCRAPING</h1>
			<p class="mt-1 text-muted-foreground">Configure and run data scraping jobs for odds and match data</p>
		</div>

		<Card title="Automatic scraping actions" variant="prediction">
			<div class="space-y-5">
				<div class="space-y-3 border border-border bg-muted/20 p-3">
					<div class="flex flex-wrap items-center justify-between gap-2">
						<div>
							<p class="text-sm font-semibold text-foreground">Scraping-uri automate salvate</p>
							<p class="text-xs text-muted-foreground">
								Butoanele de mai jos vin din endpoint-ul persistent <span class="font-mono">/api/v1/jobs</span>.
							</p>
						</div>
						<div class="flex flex-wrap gap-2">
							<Button
								variant="secondary"
								size="sm"
								onclick={fetchScheduledJobs}
								disabled={!interactive || loadingScheduledJobs}
							>
								Refresh
							</Button>
							<Button
								variant="glow"
								size="sm"
								onclick={saveAutomaticScrapeAction}
								disabled={!interactive || savingScheduledJob}
							>
								{savingScheduledJob ? 'Saving...' : 'Save autoscrape'}
							</Button>
						</div>
					</div>

					{#if scheduledJobsError}
						<p class="text-xs text-destructive">{scheduledJobsError}</p>
					{/if}

					{#if loadingScheduledJobs}
						<p class="text-xs text-muted-foreground">Loading saved scraping actions...</p>
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
										{scheduledJob.enabled ? 'running' : 'paused'}
									</span>
								</Button>
							{/each}
						</div>
					{/if}
				</div>

				<div class="space-y-3 border border-border bg-muted/20 p-3">
					<div>
						<p class="text-sm font-semibold text-foreground">Optional scrape → predict orchestration</p>
						<p class="text-xs text-muted-foreground">
							Transforms the saved scrape job into a composite orchestration workflow.
						</p>
					</div>
					<label class="flex items-center gap-2 text-sm text-foreground">
						<input
							type="checkbox"
							class="h-4 w-4 accent-football-blue"
							bind:checked={autoRunPredictions}
						/>
						<span>Run predictions automatically after each autoscrape cycle</span>
					</label>
					<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
						<Input
							label="Strategy IDs (comma separated)"
							placeholder="e.g. 1,2,5"
							bind:value={autoPredictionStrategyIds}
							disabled={!autoRunPredictions}
						/>
						<div class="space-y-2">
							<p class="text-xs text-muted-foreground">Prediction markets</p>
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
						<span>Create tickets automatically after predictions finish</span>
					</label>
					{#if autoRunPredictions && autoCreateTickets}
						<div class="grid grid-cols-1 gap-3 md:grid-cols-3">
							<Input label="Ticket count" type="number" min="1" max="50" bind:value={autoTicketCount} />
							<Select
								label="Ticket difficulty"
								bind:value={autoTicketDifficulty}
								options={[
									{ value: 'safe', label: 'Safe' },
									{ value: 'balanced', label: 'Balanced' },
									{ value: 'aggressive', label: 'Aggressive' }
								]}
							/>
							<Input label="Stake" type="number" min="0.5" step="0.5" bind:value={autoTicketStake} />
							<Input label="Min odds" type="number" min="1.01" step="0.01" bind:value={autoTicketMinOdds} />
							<Input label="Max odds" type="number" min="1.01" step="0.01" bind:value={autoTicketMaxOdds} />
						</div>
					{/if}
					{#if orchestrationJobs.length > 0}
						<div class="flex flex-wrap gap-2">
							{#each orchestrationJobs as scheduledJob (scheduledJob.id)}
								<Badge variant={scheduledJob.enabled ? 'info' : 'default'}>
									{scheduledJob.name} · {scheduledJob.enabled ? 'running' : 'paused'}
								</Badge>
							{/each}
						</div>
					{/if}
				</div>

				<div>
					<p class="text-sm font-semibold text-foreground">World Cup ticket pipeline</p>
					<p class="text-xs text-muted-foreground">Runs the existing backend pipeline. Historical league scraping below stays separate and editable.</p>
				</div>
				<div class="grid grid-cols-2 md:grid-cols-4 gap-3">
					<div class="border border-border bg-muted/30 p-3">
						<p class="text-[10px] uppercase tracking-wide text-muted-foreground">Target date</p>
						<p class="mt-1 font-mono text-lg text-foreground">{pipelineTargetDate}</p>
					</div>
					<div class="border border-border bg-muted/30 p-3">
						<p class="text-[10px] uppercase tracking-wide text-muted-foreground">History</p>
						<p class="mt-1 font-mono text-lg text-foreground">external</p>
					</div>
					<div class="border border-border bg-muted/30 p-3">
						<p class="text-[10px] uppercase tracking-wide text-muted-foreground">Odds</p>
						<p class="mt-1 font-mono text-lg text-foreground">Core</p>
					</div>
					<div class="border border-border bg-muted/30 p-3">
						<p class="text-[10px] uppercase tracking-wide text-muted-foreground">Tickets</p>
						<p class="mt-1 font-mono text-lg text-foreground">{pipelineTicketCount} x tiers</p>
					</div>
				</div>

				<div class="grid grid-cols-1 gap-3 md:grid-cols-4">
					<div>
						<label for="world-cup-target-date" class="mb-1 block text-xs text-muted-foreground">Tomorrow / target date</label>
						<Input id="world-cup-target-date" type="date" bind:value={pipelineTargetDate} />
					</div>
					<div>
						<label for="world-cup-ticket-count" class="mb-1 block text-xs text-muted-foreground">Tickets per tier</label>
						<Input id="world-cup-ticket-count" type="number" min="1" max="50" bind:value={pipelineTicketCount} />
					</div>
					<div>
						<label for="world-cup-ticket-stake" class="mb-1 block text-xs text-muted-foreground">Stake</label>
						<Input id="world-cup-ticket-stake" type="number" min="0" step="0.5" bind:value={pipelineTicketStake} />
					</div>
					<label class="flex items-center gap-2 border border-border bg-muted/20 px-3 py-2 text-sm text-foreground">
						<input
							id="world-cup-experimental"
							type="checkbox"
							class="h-4 w-4 accent-football-blue"
							bind:checked={pipelineAllowExperimental}
						/>
						<span>Create watchlist tickets if safe tickets are blocked</span>
					</label>
				</div>

				<div class="flex flex-wrap items-center gap-3">
					<Button variant="glow" onclick={runWorldCupPipeline} disabled={pipelineRunning}>
						{pipelineRunning ? 'Generating tomorrow tickets...' : 'Generate Tomorrow World Cup Tickets'}
					</Button>
					<a href="/predict" class="text-sm text-football-blue hover:text-football-green">Open predictions</a>
					<a href="/tickets" class="text-sm text-football-blue hover:text-football-green">Open tickets</a>
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
							<span class="font-mono text-xs text-muted-foreground">Pipeline is running in background</span>
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
								<p class="text-xs text-muted-foreground">Scrape jobs</p>
								<p class="font-mono text-foreground">{displayedPipelineResult.summary.completed_scrape_jobs}/{displayedPipelineResult.summary.scrape_jobs}</p>
							</div>
							<div>
								<p class="text-xs text-muted-foreground">Target matches</p>
								<p class="font-mono text-foreground">{displayedPipelineResult.summary.target_matches}</p>
							</div>
							<div>
								<p class="text-xs text-muted-foreground">Prediction runs</p>
								<p class="font-mono text-foreground">{displayedPipelineResult.summary.completed_prediction_runs}/{displayedPipelineResult.summary.prediction_runs}</p>
							</div>
							<div>
								<p class="text-xs text-muted-foreground">Created tickets</p>
								<p class="font-mono text-foreground">
									{displayedPipelineResult.summary.created_tickets}
									{#if displayedPipelineResult.summary.created_experimental_tickets}
										<span class="text-football-gold">+{displayedPipelineResult.summary.created_experimental_tickets} watchlist</span>
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
									Created ticket IDs ({displayedPipelineResult.created_ticket_ids.length})
								</p>
								<div class="flex flex-wrap gap-1.5">
									{#each displayedPipelineResult.created_ticket_ids.slice(0, 24) as ticketId (ticketId)}
									<Badge variant="success">Ticket #{ticketId}</Badge>
									{/each}
									{#if displayedPipelineResult.created_ticket_ids.length > 24}
										<Badge variant="info">+{displayedPipelineResult.created_ticket_ids.length - 24} more</Badge>
									{/if}
								</div>
							</div>
						{/if}

						{#if (displayedPipelineResult.created_experimental_ticket_ids?.length ?? 0) > 0}
							<div class="space-y-2">
								<p class="text-xs uppercase tracking-wide text-muted-foreground">
									Watchlist ticket IDs ({displayedPipelineResult.created_experimental_ticket_ids?.length ?? 0})
								</p>
								<div class="flex flex-wrap gap-1.5">
									{#each (displayedPipelineResult.created_experimental_ticket_ids ?? []).slice(0, 24) as ticketId (ticketId)}
										<Badge variant="warning">Watchlist #{ticketId}</Badge>
									{/each}
									{#if (displayedPipelineResult.created_experimental_ticket_ids?.length ?? 0) > 24}
										<Badge variant="info">+{(displayedPipelineResult.created_experimental_ticket_ids?.length ?? 0) - 24} more</Badge>
									{/if}
								</div>
							</div>
						{/if}

						{#if displayedPipelineResult.difficulty_tiers?.length > 0}
							<div class="space-y-4">
								<div>
									<p class="text-sm font-semibold text-foreground">Difficulty ladders</p>
									<p class="text-xs text-muted-foreground">
										Top 10 per level: level 1 is safest singles, level 7 is seven-leg accumulators.
									</p>
								</div>
								<div class="space-y-3">
									{#each displayedPipelineResult.difficulty_tiers as tier (tier.level)}
										<div class="border border-border bg-background/60 p-3">
											<div class="flex flex-wrap items-center justify-between gap-2">
												<div>
													<p class="text-sm font-semibold text-foreground">
														Level {tier.level}: {tier.label}
													</p>
													<p class="text-xs text-muted-foreground">
														{tier.leg_count} legs · {tier.tickets.length} ticket candidates
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
																<th class="py-2 text-left">Rank</th>
																<th class="py-2 text-left">Ticket</th>
																<th class="py-2 text-left">Selections</th>
																<th class="py-2 text-right">Probability</th>
																<th class="py-2 text-right">Odds</th>
																<th class="py-2 text-right">EV score</th>
															</tr>
														</thead>
														<tbody>
															{#each tier.tickets as ticket (`${tier.level}-${ticket.rank}`)}
																<tr class="border-t border-border align-top">
																	<td class="py-2 pr-3 font-mono text-muted-foreground">#{ticket.rank}</td>
																	<td class="py-2 pr-3">
																		<div class="font-mono text-foreground">
																			{ticket.ticket_id ? `#${ticket.ticket_id}` : 'not created'}
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
													Not enough unique World Cup matches for this difficulty level yet.
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
											<th class="py-2 text-left">Match</th>
											<th class="py-2 text-left">Pick</th>
											<th class="py-2 text-right">Probability</th>
											<th class="py-2 text-right">Odds</th>
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
													<div class="text-xs text-muted-foreground">{candidate.bookmaker ?? 'best available'}</div>
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
									<p class="text-sm font-semibold text-foreground">Watchlist candidates</p>
									<p class="text-xs text-muted-foreground">
										These are generated when safe tickets are blocked by insufficient history or fallback model usage.
									</p>
								</div>
								<table class="w-full text-sm">
									<thead class="text-xs uppercase text-muted-foreground">
										<tr>
											<th class="py-2 text-left">Match</th>
											<th class="py-2 text-left">Pick</th>
											<th class="py-2 text-left">Reliability</th>
											<th class="py-2 text-right">Probability</th>
											<th class="py-2 text-right">Odds</th>
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
													<div class="text-xs text-muted-foreground">{candidate.bookmaker ?? 'best available'}</div>
												</td>
												<td class="py-2 pr-3">
													<Badge variant="warning">{candidate.reliability ?? 'watchlist'}</Badge>
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
		</Card>

		<!-- Section 2: Data selection -->
	<Card title="Selectie de date" variant="data">
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
				<div class="flex items-center justify-between mb-3">
					<p class="text-sm font-medium text-foreground">
						Leagues
						{#if selectedCountries.length > 0}
							<span class="text-muted-foreground font-normal">(filtered)</span>
						{/if}
					</p>
					{#if filteredLeagues.length > 0}
						<button
							type="button"
							onclick={toggleAllLeagues}
							class="text-xs text-football-blue hover:text-football-green transition-colors"
						>
							{filteredLeagues.filter(isLeagueScrapeSelectable).every((l) => selectedLeagues.includes(l.id))
								? 'Deselect supported'
								: 'Select supported'}
						</button>
					{/if}
				</div>
				{#if loadingCatalog}
					<div class="space-y-2">
						<Skeleton class="h-6 w-full" />
						<Skeleton class="h-6 w-2/3" />
					</div>
				{:else if filteredLeagues.length === 0}
					<p class="text-sm text-muted-foreground">No leagues available. Select a country above.</p>
				{:else}
					<div class="max-h-48 overflow-y-auto scroll-thin space-y-1 border border-border p-2">
						{#each filteredLeagues as league (league.id)}
							{@const selectable = isLeagueScrapeSelectable(league)}
							<label class={cn(
								'flex items-center space-x-2 p-2 transition-colors duration-200',
								selectable ? 'cursor-pointer' : 'cursor-not-allowed opacity-60',
								selectedLeagues.includes(league.id)
									? 'bg-football-green/5'
									: 'hover:bg-muted'
							)}>
								<input
									type="checkbox"
									checked={selectedLeagues.includes(league.id)}
									disabled={!selectable}
									onchange={() => toggleLeague(league.id)}
									class="w-4 h-4 accent-[hsl(var(--football-green))]"
								/>
								<span class="text-sm text-foreground">{league.name}</span>
								{#if !selectable}
									<span class="text-[10px] uppercase tracking-wide text-muted-foreground">Unavailable</span>
								{/if}
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
		</div>
	</Card>

	<!-- Section 3: Historic and future ranges -->
	<Card title="Historic/future ranges" variant="data">
		<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
			<!-- Past History -->
			<div class="space-y-3">
				<div class="flex items-center justify-between">
					<p class="text-sm font-medium text-foreground">Past History</p>
					<label class="relative inline-flex items-center cursor-pointer">
						<input
							type="checkbox"
							checked={pastEnabled}
							onchange={() => (pastEnabled = !pastEnabled)}
							class="sr-only peer"
						/>
						<div class="w-9 h-5 bg-muted border border-border peer-checked:bg-football-green peer-checked:border-football-green transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-foreground after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full"></div>
					</label>
				</div>
				{#if pastEnabled}
					<div class="space-y-3" transition:slide={{ duration: 200 }}>
						<div class="grid grid-cols-2 gap-2 md:grid-cols-4">
							<Input label="Historic days" name="scrape-historic-days" type="number" min="0" bind:value={historicDays} />
							<Input label="Historic weeks" name="scrape-historic-weeks" type="number" min="0" bind:value={historicWeeks} />
							<Input label="Historic months" name="scrape-historic-months" type="number" min="0" bind:value={historicMonths} />
							<Input label="Historic years" name="scrape-historic-years" type="number" min="0" bind:value={historicYears} />
						</div>
						<div class="flex flex-wrap items-center gap-2">
							<Button variant="secondary" size="sm" onclick={applyHistoricInterval} disabled={historicIntervalDays <= 0}>
								Apply interval ({historicIntervalDays} days)
							</Button>
							<span class="text-xs text-muted-foreground">Backend historic scraping executes seasons derived from this range.</span>
						</div>
						<div class="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto]">
							<div>
								<label for="scrape-history-preset" class="text-xs text-muted-foreground mb-1 block">History preset</label>
								<Select
									name="scrape-history-preset"
									bind:value={historyPresetYears}
									options={historyPresetOptions}
									onchange={(event: Event) => applyHistoryPreset((event.target as HTMLSelectElement).value)}
								/>
							</div>
							<div class="flex items-end">
								<Button variant="secondary" size="sm" onclick={() => applyHistoryPreset()}>
									Fill dates
								</Button>
							</div>
						</div>
						<div>
							<label for="scrape-past-from" class="text-xs text-muted-foreground mb-1 block">From</label>
							<Input id="scrape-past-from" type="date" bind:value={pastFrom} />
						</div>
						<div>
							<label for="scrape-past-to" class="text-xs text-muted-foreground mb-1 block">To</label>
							<Input id="scrape-past-to" type="date" bind:value={pastTo} />
						</div>
						<div>
							<label for="scrape-history-pages" class="text-xs text-muted-foreground mb-1 block">Max pages per season</label>
							<Input id="scrape-history-pages" type="number" min="1" max="50" bind:value={historicMaxPages} />
						</div>
						<div class="border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
							<p>
								History runs as normal <span class="font-mono text-foreground">scrape_odds / historic</span>
								jobs, not through the ticket pipeline.
							</p>
							{#if historicSeasonPreview.length > 0}
								<p class="mt-2">
									Seasons to scrape:
									<span class="font-mono text-foreground">{historicSeasonPreview.join(', ')}</span>
								</p>
							{:else}
								<p class="mt-2">Fill dates to preview the seasons that will be scraped.</p>
							{/if}
						</div>
					</div>
				{/if}
			</div>

			<!-- Future Matches -->
			<div class="space-y-3">
				<div class="flex items-center justify-between">
					<p class="text-sm font-medium text-foreground">Future Matches</p>
					<label class="relative inline-flex items-center cursor-pointer">
						<input
							type="checkbox"
							checked={futureEnabled}
							onchange={() => (futureEnabled = !futureEnabled)}
							class="sr-only peer"
						/>
						<div class="w-9 h-5 bg-muted border border-border peer-checked:bg-football-green peer-checked:border-football-green transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-foreground after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full"></div>
					</label>
				</div>
				{#if futureEnabled}
					<div class="space-y-3" transition:slide={{ duration: 200 }}>
						<div class="grid grid-cols-2 gap-2 md:grid-cols-4">
							<Input label="Future days" name="scrape-future-days" type="number" min="0" bind:value={futureDays} />
							<Input label="Future weeks" name="scrape-future-weeks" type="number" min="0" bind:value={futureWeeks} />
							<Input label="Future months" name="scrape-future-months" type="number" min="0" bind:value={futureMonths} />
							<Input label="Future years" name="scrape-future-years" type="number" min="0" bind:value={futureYears} />
						</div>
						<div class="border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
							The backend supports an upcoming scrape horizon as <span class="font-mono text-foreground">future_days</span>. This form will send <span class="font-mono text-foreground">{futureIntervalDays}</span> days.
						</div>
					</div>
				{/if}
			</div>
		</div>
	</Card>

	<!-- Section 4: Controls -->
	<Card title="Controls" variant="data">
		<div class="space-y-4">
			<!-- Auto-scrape -->
			<div class="flex items-center justify-between">
				<div>
					<p class="text-sm font-medium text-foreground">Auto-scrape</p>
					<p class="text-xs text-muted-foreground">Automatically run scrape jobs on a schedule</p>
				</div>
				<label class="relative inline-flex items-center cursor-pointer">
					<input
						type="checkbox"
						checked={autoScrape}
						onchange={() => (autoScrape = !autoScrape)}
						class="sr-only peer"
					/>
					<div class="w-9 h-5 bg-muted border border-border peer-checked:bg-football-green peer-checked:border-football-green transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-foreground after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full"></div>
				</label>
			</div>
			{#if autoScrape}
				<div class="flex items-end gap-2 pl-4 border-l-2 border-football-green/30" transition:slide={{ duration: 200 }}>
					<div class="flex-1">
						<label for="scrape-auto-interval" class="text-xs text-muted-foreground mb-1 block">Interval</label>
						<Input id="scrape-auto-interval" type="number" bind:value={autoIntervalNumber} placeholder="24" />
					</div>
					<div class="flex-1">
						<Select bind:value={autoIntervalUnit} options={intervalUnitOptions} />
					</div>
				</div>
			{/if}

			<Separator />

			<div class="space-y-2">
				<Select
					bind:value={scraperEngine}
					label="Scraper engine"
					name="scrape-engine"
					options={scraperEngineOptions}
				/>
				<p class="text-xs text-muted-foreground">
					Auto incearca Scrapling pentru flow-urile football/core-market si revine la Playwright cand cererea nu este suportata. Pentru all_markets sau odds_history foloseste Playwright.
				</p>
			</div>

			<Separator />

			<!-- Dedup -->
			<div class="flex items-center justify-between">
				<div>
					<p class="text-sm font-medium text-foreground">Skip existing matches</p>
					<p class="text-xs text-muted-foreground">Avoid re-scraping data already in the database</p>
				</div>
				<label class="relative inline-flex items-center cursor-pointer">
					<input
						type="checkbox"
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

			<Separator />

			<div class="space-y-3">
				{#if submitSuccess}
					<div class="p-3 text-sm bg-football-green/10 border border-football-green/30 text-football-green" transition:slide={{ duration: 200 }}>
						{submitSuccess}
					</div>
				{/if}
				{#if submitError}
					<div class="p-3 text-sm bg-destructive/10 border border-destructive/30 text-destructive" transition:slide={{ duration: 200 }}>
						{submitError}
					</div>
				{/if}
				<Button
					variant="glow"
					size="lg"
					fullWidth
					disabled={submitting || (selectedCountries.length === 0 && selectedLeagues.length === 0)}
					onclick={startScrape}
				>
					{#if submitting}
						<span class="flex items-center justify-center gap-2">
							<span class="h-4 w-4 border-2 border-foreground border-t-transparent animate-spin"></span>
							Starting...
						</span>
					{:else}
						Start Scraping
					{/if}
				</Button>
			</div>

			<Separator />

			<div class="space-y-3">
					<div class="flex flex-wrap items-center justify-between gap-3">
						<div>
							<p class="text-sm font-medium text-foreground">Job logs</p>
							<p class="text-xs text-muted-foreground">Persistent action-by-action logs for the selected scrape job.</p>
						</div>
						<Button variant="secondary" size="sm" onclick={toggleLogsPanel}>
							{logsPanelOpen ? 'Hide logs' : 'Show logs'}
						</Button>
					</div>
					{#if logsPanelOpen}
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
								<p class="text-sm text-muted-foreground">Loading job logs...</p>
							{:else if jobLogsError}
								<p class="text-sm text-destructive">{jobLogsError}</p>
							{:else if jobLogs.length === 0}
								<p class="text-sm text-muted-foreground">No job logs available yet.</p>
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
		</div>
	</Card>

	<!-- Section 4: Job Table -->
	<Card title="Jobs" variant="data">
		{#if loadingJobs}
			<div class="space-y-3">
				<Skeleton class="h-12 w-full" />
				<Skeleton class="h-12 w-full" />
				<Skeleton class="h-12 w-full" />
			</div>
		{:else if jobs.length === 0}
			<p class="text-sm text-muted-foreground text-center py-8">No scraping jobs yet</p>
		{:else}
			<div class="overflow-x-auto">
				<table class="w-full text-sm">
					<thead class="text-xs uppercase bg-muted border-b border-border text-muted-foreground">
						<tr>
							<th class="px-3 py-2 text-left">Name</th>
							<th class="px-3 py-2 text-left">Status</th>
							<th class="px-3 py-2 text-left">Created</th>
							<th class="px-3 py-2 text-left">Duration</th>
							<th class="px-3 py-2 text-left">Progress</th>
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
									<Badge variant={statusVariant(job.status)}>{job.status}</Badge>
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
												<span class="text-muted-foreground">Job ID:</span>
												<span class="ml-2 font-mono text-foreground">{job.id}</span>
											</div>
											<div>
												<span class="text-muted-foreground">Type:</span>
												<span class="ml-2 font-mono text-foreground">{jobLabel(job)}</span>
											</div>
											{#if job.error}
												<div class="col-span-2">
													<span class="text-destructive">{job.error}</span>
												</div>
											{/if}
											{#if job.params && Object.keys(job.params).length > 0}
												<div class="col-span-2">
													<span class="text-muted-foreground">Params:</span>
													<pre class="mt-1 p-2 bg-background border border-border font-mono text-xs overflow-x-auto">{JSON.stringify(job.params, null, 2)}</pre>
												</div>
											{/if}
											<div class="col-span-2">
												<Button variant="secondary" size="sm" onclick={() => openLogsForJob(job.id)}>
													View complete logs
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
