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
	import { hasStrategyAvgEdge, normalizeStrategies } from './strategy.helpers';
	import { cn } from '$lib/utils';
	import type {
		Country,
		Strategy,
		StrategyCreateRequest,
		StrategyRunResult
	} from '$lib/types';

	// Use same-origin /api requests so the frontend auth cookie is sent through the proxy.
	const BASE_URL = '';

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
		const marketOptions = [
			{ id: '1x2', label: '1X2' },
			{ id: 'over_under_2.5', label: 'Over/Under 2.5' },
			{ id: 'btts', label: 'BTTS' }
		];
		let selectedMarkets = $state<string[]>(['1x2']);

	// --- Run State ---
	let running = $state(false);
	let runProgress = $state(0);
	let runError = $state('');
	let runSuccess = $state('');
	let runWarning = $state('');
	let autoPredict = $state(false);
	let autoInterval = $state('24');
	let autoIntervalUnit = $state('Hours');
	let pollTimer: ReturnType<typeof setInterval> | null = null;

	// --- Results State ---
	let results = $state<StrategyRunResult[]>([]);
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

	async function fetchResults() {
		try {
			const res = await fetch(`${BASE_URL}/api/v1/strategies/runs?limit=100`, { credentials: 'include' });
			if (res.ok) {
				const data = await res.json();
				results = Array.isArray(data) ? data : [];
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
						}
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
			}

			clearInterval(progressInterval);
			runProgress = 100;
			runSuccess = warnings.length > 0 ? 'Predictions completed with warnings' : 'Predictions completed successfully';
			runWarning = warnings.join(' ');
			await fetchResults();
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

	onMount(() => {
		fetchCatalog();
		fetchStrategies();
		fetchResults();
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

	<!-- Section 1: Data Selectors -->
	<Card title="Data Selection" variant="prediction">
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
		</div>
	</Card>

	<!-- Section 2: Strategy Selection -->
	<div class="space-y-4">
		<div class="flex items-center justify-between">
			<h2 class="text-lg font-semibold text-foreground">Strategies</h2>
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

		<!-- Section 3: Market Selection -->
		<Card title="Markets" variant="prediction">
			<div class="space-y-3">
				<p class="text-sm text-muted-foreground">
					Select at least one market to predict. This route currently returns 1X2, Over/Under 2.5, and BTTS from the penaltyblog goal models.
				</p>
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

	<!-- Section 4: Run -->
	<div class="space-y-4">
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

		<div class="flex items-center gap-4">
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

			<div class="flex items-center gap-2 ml-4">
				<label class="relative inline-flex items-center cursor-pointer">
					<input
						type="checkbox"
						checked={autoPredict}
						onchange={() => (autoPredict = !autoPredict)}
						class="sr-only peer"
					/>
					<div class="w-9 h-5 bg-muted border border-border peer-checked:bg-football-green peer-checked:border-football-green transition-colors after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-foreground after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full"></div>
				</label>
				<span class="text-sm text-muted-foreground">Auto</span>
				{#if autoPredict}
					<div class="flex items-center gap-1" transition:slide={{ duration: 200 }}>
						<Input type="number" bind:value={autoInterval} class="w-20" />
						<Select bind:value={autoIntervalUnit} options={unitOptions} />
					</div>
				{/if}
			</div>
		</div>
	</div>

	<!-- Section 5: Results -->
	{#if results.length > 0}
		<div class="space-y-4">
			<div class="flex items-center justify-between">
				<h2 class="text-lg font-semibold text-foreground">Results</h2>
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
				No prediction results yet. Select strategies and run predictions to see results.
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
