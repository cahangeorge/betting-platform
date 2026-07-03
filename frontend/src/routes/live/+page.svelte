<script lang="ts">
	import type { PageData } from './$types';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Loading from '$lib/components/Loading.svelte';
	import XGTimelineChart from '$lib/components/charts/xGTimelineChart.svelte';
	import { matchesApi } from '$lib/api/matches';
	import { betslip, createBetslipLeg } from '$lib/stores/betslip';
	import { matchEvents, oddsUpdates, predictionUpdates } from '$lib/stores/liveSocket';
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';

	let { data }: { data: PageData } = $props();

	function getLeagueOptions(matches: PageData['matches']): string[] {
		const leagues = ['All', ...new Set(matches.map((match) => match.league).filter(Boolean) as string[])];
		return Array.from(new Set(leagues)).sort((a, b) => {
			if (a === 'All') return -1;
			if (b === 'All') return 1;
			return a.localeCompare(b);
		});
	}

	let statusFilter = $state<'All' | 'Live' | 'Halftime' | 'Finished'>('Live');
	let selectedLeague = $state<string>('All');
	let sortBy = $state<'time' | 'momentum' | 'score'>('time');
	let minLiveEdge = $state(1);
	let allLeagues = $state<string[]>(['All']);
	let lastUpdated = $state(new Date().toISOString());
	let liveMatches = $state<PageData['matches']>([]);
	let isLoading = $state(false);
	let errorMessage = $state<string | null>(null);
	let dataAgeSeconds = $state<number | null>(null);
	let source = $state<string>('cache');
	let bridgeReady = $state(true);
	let bridgeIssues = $state<string[]>([]);
	let isDataStale = $state(true);
	let isDemo = $state(false);
	let heartbeatAt = $state<string>(new Date().toISOString());
	let jobsActive = $state(0);

	let refreshDebounce: ReturnType<typeof setTimeout> | undefined;
	let socketRefreshDebounce: ReturnType<typeof setTimeout> | undefined;
	let refreshInterval: ReturnType<typeof setInterval> | undefined;
	let didInitialize = $state(false);
	const LIVE_TRUST_MAX_AGE_SECONDS = 30;

	type LiveHeartbeatSnapshot = {
		jobs_active: number;
		bridge_ready: boolean;
		bridge_issues: string[];
		timestamp: string;
	};

	function sanitizeLeague(value: string): string {
		const normalized = value.trim();
		if (!normalized || normalized === 'All') {
			return 'All';
		}
		if (allLeagues.includes(normalized)) {
			return normalized;
		}
		return 'All';
	}

	$effect(() => {
		minLiveEdge = data.minLiveValueEdge ?? 1;
		statusFilter = (data.statusFilter as 'All' | 'Live' | 'Halftime' | 'Finished') ?? 'All';
		selectedLeague = sanitizeLeague((data.selectedLeague as string) || 'All');
		liveMatches = data.matches || [];
		lastUpdated = data.lastUpdated || new Date().toISOString();
		errorMessage = data.error ?? null;
		dataAgeSeconds = data.dataAgeSeconds ?? null;
		source = (data.source as string) || 'cache';
		bridgeReady = (data.bridgeReady as boolean) ?? true;
		bridgeIssues = (data.bridgeIssues as string[]) || [];
		isDataStale = (data.isDataStale as boolean) ?? true;
		isDemo = (data.isDemo as boolean) ?? !bridgeReady;
		heartbeatAt = (data.heartbeatAt as string) || new Date().toISOString();
		jobsActive = (data.jobsActive as number) ?? 0;

		allLeagues = getLeagueOptions(liveMatches);

		selectedLeague = sanitizeLeague(selectedLeague);
	});

	function buildLoadParams() {
		return {
			min_live_value_edge: minLiveEdge,
			include_live_value: true,
			status: statusFilter === 'All' ? 'all' : statusFilter.toLowerCase(),
			league: selectedLeague === 'All' ? undefined : selectedLeague
		};
	}

	function buildQueryParams() {
		const params = new URLSearchParams();
		if (minLiveEdge !== 1) {
			params.set('min_live_value_edge', String(minLiveEdge));
		}
		if (statusFilter !== 'All') {
			params.set('status', statusFilter.toLowerCase());
		}
		if (selectedLeague !== 'All') {
			params.set('league', selectedLeague);
		}
		return params;
	}

	function syncQueryToUrl() {
		if (!browser) {
			return;
		}

		const params = buildQueryParams();
		const query = params.toString();
		const pathname = window.location.pathname;
		window.history.replaceState({}, '', query ? `${pathname}?${query}` : pathname);
	}

	async function fetchLiveHeartbeat(): Promise<LiveHeartbeatSnapshot | null> {
		try {
			const response = await fetch('/api/v1/live/heartbeat', { credentials: 'include' });
			if (!response.ok) {
				return null;
			}

			const payload = (await response.json()) as LiveHeartbeatSnapshot;
			return payload;
		} catch {
			return null;
		}
	}

	async function refreshLiveMatches() {
		if (isLoading) {
			return;
		}

		isLoading = true;
		errorMessage = null;
		try {
			const [response, heartbeat] = await Promise.all([
				matchesApi.getLiveOverview(undefined, buildLoadParams()),
				fetchLiveHeartbeat()
			]);
			liveMatches = response.matches;
			lastUpdated = response.generated_at;
			dataAgeSeconds = response.data_age_seconds;
			source = response.source;
			isDataStale = response.is_data_stale;
			jobsActive = heartbeat?.jobs_active ?? response.jobs_active;
			bridgeReady = heartbeat?.bridge_ready ?? bridgeReady;
			bridgeIssues = heartbeat?.bridge_issues ?? bridgeIssues;
			heartbeatAt = heartbeat?.timestamp ?? response.generated_at;
			isDemo = response.is_demo || !bridgeReady;
			allLeagues = getLeagueOptions(response.matches);
			selectedLeague = sanitizeLeague(selectedLeague);
		} catch (error) {
			errorMessage = error instanceof Error ? error.message : 'Failed to refresh live matches.';
		} finally {
			isLoading = false;
		}
	}

	function scheduleSocketRefresh() {
		if (!browser) {
			return;
		}

		if (socketRefreshDebounce) {
			clearTimeout(socketRefreshDebounce);
		}

		socketRefreshDebounce = setTimeout(() => {
			socketRefreshDebounce = undefined;
			void refreshLiveMatches();
		}, 150);
	}

	const renderedMatches = $derived.by(() => (liveMatches.length > 0 ? liveMatches : (data.matches ?? [])));

	const filteredMatches = $derived.by(() => {
		const matches = [...renderedMatches];
		matches.sort((a, b) => {
			if (sortBy === 'time') return (b.minute || 0) - (a.minute || 0);
			if (sortBy === 'momentum') {
				const mA = a.momentum_intensity === 'overwhelming'
					? 4
					: a.momentum_intensity === 'strong'
						? 3
						: a.momentum_intensity === 'moderate'
							? 2
							: 1;
				const mB = b.momentum_intensity === 'overwhelming'
					? 4
					: b.momentum_intensity === 'strong'
						? 3
						: b.momentum_intensity === 'moderate'
							? 2
							: 1;
				return mB - mA;
			}
			const scoreA = (a.home_score ?? 0) + (a.away_score ?? 0);
			const scoreB = (b.home_score ?? 0) + (b.away_score ?? 0);
			return scoreB - scoreA;
		});
		return matches;
	});

	const valueMatches = $derived.by(() => {
		const list = filteredMatches.filter((match) => {
			if (!match.live_value_candidates || match.live_value_candidates.length === 0) return false;
			return match.live_value_candidates.some((candidate) => candidate.edge >= minLiveEdge);
		});
		return list.sort((a, b) => {
			const aBest = Math.max(...(a.live_value_candidates ?? []).map((c) => c.edge));
			const bBest = Math.max(...(b.live_value_candidates ?? []).map((c) => c.edge));
			return bBest - aBest;
		});
	});

	const visibleMatches = $derived.by(() => (valueMatches.length > 0 ? valueMatches : filteredMatches));

	const liveSlipLockReason = $derived.by(() => {
		if (isDemo) {
			return 'Live add-to-betslip is locked while the page is showing demo data.';
		}
		if (!bridgeReady) {
			return 'Live add-to-betslip is locked because the live bridge is not ready.';
		}
		if (source.trim().toLowerCase() === 'demo') {
			return 'Live add-to-betslip is locked because the feed source is demo.';
		}
		if (dataAgeSeconds === null) {
			return 'Live add-to-betslip is locked because feed freshness is unavailable.';
		}
		if (isDataStale || dataAgeSeconds > LIVE_TRUST_MAX_AGE_SECONDS) {
			return `Live add-to-betslip is locked because the feed is older than ${LIVE_TRUST_MAX_AGE_SECONDS}s.`;
		}
		return null;
	});

	// Auto-refresh timestamp as a lightweight indicator in this phase.
	onMount(() => {
		if (!didInitialize) {
			didInitialize = true;
		}

		void refreshLiveMatches();

		refreshInterval = setInterval(() => {
			void refreshLiveMatches();
		}, 10000);

		const unsubscribeOddsUpdates = oddsUpdates.subscribe((message) => {
			if (message) {
				scheduleSocketRefresh();
			}
		});

		const unsubscribePredictionUpdates = predictionUpdates.subscribe((message) => {
			if (message) {
				scheduleSocketRefresh();
			}
		});

		const unsubscribeMatchEvents = matchEvents.subscribe((message) => {
			if (message) {
				scheduleSocketRefresh();
			}
		});

		return () => {
			unsubscribeOddsUpdates();
			unsubscribePredictionUpdates();
			unsubscribeMatchEvents();
			if (refreshInterval) clearInterval(refreshInterval);
			if (refreshDebounce) clearTimeout(refreshDebounce);
			if (socketRefreshDebounce) clearTimeout(socketRefreshDebounce);
		};
	});

	$effect(() => {
		if (!didInitialize) {
			return;
		}

		if (refreshDebounce) {
			clearTimeout(refreshDebounce);
		}

		refreshDebounce = setTimeout(() => {
			syncQueryToUrl();
			void refreshLiveMatches();
		}, 350);
	});

	function getStatusBadge(status: string): { variant: string; label: string } {
		switch (status) {
			case 'live':
				return { variant: 'live', label: 'LIVE' };
			case 'halftime':
				return { variant: 'warning', label: 'HT' };
			case 'finished':
				return { variant: 'info', label: 'FT' };
			default:
				return { variant: 'default', label: status.toUpperCase() };
		}
	}

	function formatMinute(minute: number | undefined): string {
		if (minute === undefined) return '-';
		return `${minute}'`;
	}

	function timeAgo(iso: string): string {
		const date = new Date(iso);
		const now = new Date();
		const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
		if (seconds < 60) return `${seconds}s ago`;
		const mins = Math.floor(seconds / 60);
		return `${mins}m ago`;
	}

	function getXgTimelineData(match: PageData['matches'][number]): { minute: number; homeXg: number; awayXg: number }[] {
		if (!match.xg_home || !match.xg_away) return [];
		const minute = match.minute || 90;
		const steps = Math.min(minute, 10);
		const data = [];
		for (let i = 1; i <= steps; i++) {
			const progress = i / steps;
			data.push({
				minute: Math.round((minute * i) / steps),
				homeXg: Number((match.xg_home * progress).toFixed(2)),
				awayXg: Number((match.xg_away * progress).toFixed(2))
			});
		}
		return data;
	}

	function candidateSelectionToSide(selection: string): '1' | 'X' | '2' | string {
		const normalized = selection.trim().toLowerCase();
		if (normalized === 'home') return '1';
		if (normalized === 'draw') return 'X';
		if (normalized === 'away') return '2';
		return selection;
	}

	function candidateSelectionLabel(selection: string): string {
		const normalized = selection.trim().toLowerCase();
		if (normalized === 'home') return '1';
		if (normalized === 'draw') return 'X';
		if (normalized === 'away') return '2';
		return selection.toUpperCase();
	}

	function confidenceBandColor(band: 'low' | 'medium' | 'high'): string {
		if (band === 'high') return 'bg-football-green/20 text-football-green border-football-green/40';
		if (band === 'medium') return 'bg-football-blue/20 text-football-blue border-football-blue/40';
		return 'bg-muted text-muted-foreground border-border';
	}

	function formatPercent(value: number): string {
		return `${(value * 100).toFixed(1)}%`;
	}

	function formatEdge(edge: number): string {
		const sign = edge > 0 ? '+' : '';
		return `${sign}${edge.toFixed(1)}%`;
	}

	function formatEVValue(ev: number): string {
		const sign = ev >= 0 ? '+' : '';
		return `${sign}${(ev * 100).toFixed(1)}%`;
	}

	function formatPredictionAge(seconds: number | null | undefined): string {
		if (seconds === null || seconds === undefined) return '-';
		if (seconds < 60) return `${seconds}s`;
		const minutes = Math.floor(seconds / 60);
		if (minutes < 60) return `${minutes}m`;
		const hours = Math.floor(minutes / 60);
		return `${hours}h`;
	}

	function humanizeBlockReason(reason: string): string {
		switch (reason) {
			case 'bridge_not_ready':
				return 'the live bridge is not ready';
			case 'match_not_live':
				return 'the match is not currently in play';
			case 'odds_missing_timestamp':
				return 'odds freshness is unavailable';
			case 'prediction_missing_timestamp':
				return 'prediction freshness is unavailable';
			case 'data_age_unknown':
				return 'combined data age is unknown';
			case 'data_stale':
				return `combined data age is above ${LIVE_TRUST_MAX_AGE_SECONDS}s`;
			case 'model_drift':
				return 'the prediction appears out of sync with current odds';
			default:
				return reason.replaceAll('_', ' ');
		}
	}

	function getMatchSelectionLockReason(match: PageData['matches'][number]): string | null {
		if (liveSlipLockReason) {
			return liveSlipLockReason;
		}
		if (match.status !== 'live') {
			return 'Only in-play matches can be added from the live page.';
		}
		if (match.source_ok === false) {
			return 'This match is not currently trusted for live betslip actions.';
		}
		if (match.has_live_1x2_odds === false) {
			return 'This match does not currently have trusted 1x2 live odds.';
		}
		const oddsAgeSeconds = match.odds_freshness_seconds ?? null;
		if (oddsAgeSeconds === null) {
			return 'Odds freshness is unavailable for this match.';
		}
		if (oddsAgeSeconds > LIVE_TRUST_MAX_AGE_SECONDS) {
			return `Odds are ${oddsAgeSeconds}s old, above the ${LIVE_TRUST_MAX_AGE_SECONDS}s live trust limit.`;
		}
		return null;
	}

	function getCandidateSelectionLockReason(
		match: PageData['matches'][number],
		candidate: NonNullable<PageData['matches'][number]['live_value_candidates']>[number]
	): string | null {
		if (candidate.is_betslip_eligible === false && candidate.block_reasons?.length) {
			return `Live value candidate is locked because ${candidate.block_reasons.map(humanizeBlockReason).join(', ')}.`;
		}
		const matchReason = getMatchSelectionLockReason(match);
		if (matchReason) {
			return matchReason;
		}
		if (candidate.source_ok === false) {
			return 'This live value candidate is not from a trusted live source.';
		}
		const predictionAgeSeconds = candidate.selection_age_seconds ?? candidate.prediction_age_seconds;
		if (predictionAgeSeconds !== null && predictionAgeSeconds !== undefined && predictionAgeSeconds > LIVE_TRUST_MAX_AGE_SECONDS) {
			return `Prediction is ${formatPredictionAge(predictionAgeSeconds)} old, above the ${LIVE_TRUST_MAX_AGE_SECONDS}s live trust limit.`;
		}
		return null;
	}

	function addLiveValueSelection(
		match: PageData['matches'][number],
		candidate: NonNullable<PageData['matches'][number]['live_value_candidates']>[number]
	) {
		if (getCandidateSelectionLockReason(match, candidate)) return;
		betslip.addLeg(
			createBetslipLeg({
				matchId: match.id,
				matchName: `${match.home_team} vs ${match.away_team}`,
				market: candidate.market,
				selection: candidate.selection,
				odds: candidate.odds,
				league: match.league || 'TBD',
				kickoff: match.start_time,
				source: 'live'
			})
		);
	}

	function addLiveSelection(
		match: PageData['matches'][number],
		selection: '1' | 'X' | '2',
		odds: number | null
	) {
		if (odds === null) return;
		if (getMatchSelectionLockReason(match)) return;
		const market = '1x2';
		const normalizedSelection = selection === '1' ? 'home' : selection === 'X' ? 'draw' : 'away';
		betslip.addLeg(
			createBetslipLeg({
				matchId: match.id,
				matchName: `${match.home_team} vs ${match.away_team}`,
				market,
				selection: normalizedSelection,
				odds,
				league: match.league || 'TBD',
				kickoff: match.start_time,
				source: 'live'
			})
		);
	}
</script>

<svelte:head>
	<title>Live Matches | Betfront</title>
	<meta name="description" content="Real-time match scores, stats, and model-backed value picks" />
</svelte:head>

<div class="space-y-6">
	<div class="flex items-center gap-3 border-b border-border pb-4">
		<div class="relative">
			<div class="w-3 h-3 bg-football-green"></div>
			<div class="absolute inset-0 w-3 h-3 animate-ping bg-football-green opacity-50"></div>
		</div>
		<div>
			<h1 class="text-2xl font-extrabold tracking-tight font-sport text-foreground">LIVE MATCHES</h1>
			<p class="text-muted-foreground">Live odds, momentum and model value candidates</p>
		</div>
		<div class="ml-auto text-xs font-mono text-muted-foreground/60">Updated {timeAgo(lastUpdated)}</div>
	</div>

	{#if isDataStale}
		<Card>
			<div class="p-4 border-l-4 border-yellow-500 bg-yellow-500/10 text-sm">
				<span class="font-medium">Live feed may be stale</span>
				{#if dataAgeSeconds != null} · last update ~{Math.max(dataAgeSeconds, 0)}s ago.{/if}
			</div>
		</Card>
	{/if}
	{#if liveSlipLockReason}
		<Card>
			<div class="p-4 border-l-4 border-orange-500 bg-orange-500/10 text-sm">
				<div class="font-medium">Monitor-only mode for live betslip actions</div>
				<div class="mt-1 text-muted-foreground">{liveSlipLockReason}</div>
			</div>
		</Card>
	{/if}
	{#if isDemo}
		<Card>
			<div class="p-4 border-l-4 border-red-500 bg-red-500/10 text-sm">
				<span class="font-medium">Demo data mode</span> · bridge ready: {bridgeReady ? 'yes' : 'no'} · source: {source}
			</div>
		</Card>
	{/if}
	{#if !bridgeReady}
		<Card>
			<div class="p-4 border-l-4 border-red-500/80 bg-red-500/10 text-sm">
				<div class="font-medium">Bridge health</div>
				<div class="mt-1 text-xs font-mono">
					{#if bridgeIssues.length === 0}
						No bridge issues reported.
					{:else}
						{bridgeIssues.join(' | ')}
					{/if}
				</div>
			</div>
		</Card>
	{/if}
	<div class="text-xs font-mono text-muted-foreground flex items-center gap-3">
		<span>source: {source}</span>
		<span>jobs active: {jobsActive}</span>
		<span>heartbeat: {timeAgo(heartbeatAt)}</span>
		<span>data age: {dataAgeSeconds === null ? 'n/a' : `${dataAgeSeconds}s`}</span>
	</div>

	<Card>
		<div class="p-4 flex flex-wrap items-center gap-4">
			<div class="flex items-center gap-2">
				<span class="text-xs uppercase tracking-wider text-muted-foreground">Status:</span>
				{#each ['All', 'Live', 'Halftime', 'Finished'] as status (status)}
					<button
						onclick={() => (statusFilter = status as 'All' | 'Live' | 'Halftime' | 'Finished')}
						class="px-3 py-1 text-xs font-medium border transition-all duration-200 font-mono {statusFilter === status ? 'bg-football-green/10 border-football-green text-football-green' : 'bg-transparent border-border text-muted-foreground'}"
					>
						{status}
					</button>
				{/each}
			</div>
			<div class="flex items-center gap-2">
				<span class="text-xs uppercase tracking-wider text-muted-foreground">League:</span>
				<select
					bind:value={selectedLeague}
					class="px-3 py-1 text-xs font-medium border bg-card border-border text-foreground font-mono"
				>
					{#each allLeagues as league (league)}
						<option value={league}>{league}</option>
					{/each}
				</select>
			</div>
			<div class="flex items-center gap-2">
				<span class="text-xs uppercase tracking-wider text-muted-foreground">Sort:</span>
				{#each [['time', 'Time'], ['momentum', 'Momentum'], ['score', 'Score']] as [value, label] (value)}
					<button
						onclick={() => (sortBy = value as 'time' | 'momentum' | 'score')}
						class="px-3 py-1 text-xs font-medium border transition-all duration-200 font-mono {sortBy === value ? 'bg-football-green/10 border-football-green text-football-green' : 'bg-transparent border-border text-muted-foreground'}"
					>
						{label}
					</button>
				{/each}
			</div>
			<div class="ml-auto flex items-center gap-2">
				<span class="text-xs uppercase tracking-wider text-muted-foreground">Min edge:</span>
				<input
					type="number"
					min="0"
					max="20"
					step="0.5"
					bind:value={minLiveEdge}
					class="w-20 px-2 py-1 text-xs border bg-card border-border text-foreground font-mono"
				/>
				<span class="text-xs font-mono text-football-green">{minLiveEdge}%</span>
			</div>
		</div>
	</Card>

	{#if isLoading && liveMatches.length === 0}
		<div class="flex justify-center py-12">
			<Loading />
		</div>
	{:else if renderedMatches.length === 0}
		<Card>
			<div class="p-12 text-center">
				<h3 class="text-lg font-semibold mb-2 text-foreground">No matches found</h3>
				<p class="text-muted-foreground">Try adjusting your filters</p>
			</div>
		</Card>
	{:else}
		{#if errorMessage}
			<div class="text-xs font-mono text-destructive">{errorMessage}</div>
		{/if}
		{#if valueMatches.length > 0 && renderedMatches.length > 0}
			<div class="mb-2 text-xs font-mono text-muted-foreground">
				Showing matches with value candidates >= {formatEdge(minLiveEdge)} (or all matches if none qualify).
			</div>
		{/if}
		<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
			{#each visibleMatches as match (match.id)}
				<Card
					interactive
					class={match.status === 'live' ? 'card-glow-cyan-subtle' : ''}
					style={match.status === 'live'
						? 'border-color: rgba(74, 222, 128, 0.3); box-shadow: 0 0 15px rgba(74, 222, 128, 0.05);'
						: ''}
				>
					<div class="p-4 space-y-4">
						<div class="flex items-center justify-between">
							<Badge variant="info">{match.league}</Badge>
							<div class="flex items-center gap-2">
								{#if match.status === 'live'}
									<div class="relative">
										<div class="w-2 h-2 bg-football-green"></div>
										<div class="absolute inset-0 w-2 h-2 animate-ping bg-football-green opacity-50"></div>
									</div>
								{/if}
								<span class="text-xs font-mono font-bold {match.status === 'live' ? 'text-football-green' : 'text-muted-foreground'}">
									{match.status === 'live' ? `LIVE ${formatMinute(match.minute)}` : getStatusBadge(match.status).label}
								</span>
							</div>
						</div>

						<div class="flex items-center justify-between py-2">
							<div class="flex-1 text-left">
								<div class="font-semibold text-sm font-sport text-football-blue">{match.home_team}</div>
								<div class="text-xs mt-1 text-muted-foreground">Home</div>
							</div>
							<div class="text-center px-4">
								<div class="text-3xl font-bold font-mono tracking-wider text-foreground">
									{match.home_score ?? 0} - {match.away_score ?? 0}
								</div>
								{#if match.status === 'live'}
									<div class="text-xs font-mono mt-1 text-football-green">{formatMinute(match.minute)}</div>
								{/if}
							</div>
							<div class="flex-1 text-right">
								<div class="font-semibold text-sm font-sport text-football-blue">{match.away_team}</div>
								<div class="text-xs mt-1 text-muted-foreground">Away</div>
							</div>
						</div>

						<div class="space-y-2">
							<div class="flex items-center gap-2">
								<span class="text-xs font-mono w-8 text-football-green">{match.possession_home ?? 0}%</span>
								<div class="flex-1 h-1.5 flex bg-muted">
									<div
										class="h-full transition-all duration-1000 bg-football-green"
										style={`width: ${match.possession_home ?? 0}%;`}
									></div>
									<div
										class="h-full transition-all duration-1000 bg-football-blue"
										style={`width: ${match.possession_away ?? 0}%;`}
									></div>
								</div>
								<span class="text-xs font-mono w-8 text-right text-football-blue">{match.possession_away ?? 0}%</span>
							</div>

							<div class="flex justify-between text-xs font-mono">
								<div class="text-football-green">Shots: {match.shots_home ?? 0}</div>
								<div class="text-muted-foreground">xG: {(match.xg_home ?? 0).toFixed(2)} | {(match.xg_away ?? 0).toFixed(2)}</div>
								<div class="text-football-blue">Shots: {match.shots_away ?? 0}</div>
							</div>

							{#if match.status === 'live' && match.xg_home && match.xg_away}
								{@const xgData = getXgTimelineData(match)}
								{#if xgData.length > 0}
									<div class="pt-2">
										<div class="text-xs uppercase tracking-wider mb-2 text-muted-foreground">xG Timeline</div>
										<XGTimelineChart data={xgData} />
									</div>
								{/if}
								{/if}
							</div>

						{#if match.status === 'live' && match.momentum !== 'neutral'}
							<div class="flex items-center gap-2 pt-2 border-t border-border">
								<span class="text-xs uppercase tracking-wider text-muted-foreground">Momentum:</span>
								<div class="flex items-center gap-1">
									{#if match.momentum === 'home'}
										<span class="text-lg">◄</span>
										<div class="h-1" style="width: 60px; background: linear-gradient(90deg, oklch(0.72 0.19 155), transparent);"></div>
									{:else}
										<div class="h-1" style="width: 60px; background: linear-gradient(90deg, transparent, oklch(0.65 0.15 250));"></div>
										<span class="text-lg">▶</span>
									{/if}
									<span class="text-xs font-mono capitalize text-football-green">{match.momentum_intensity || 'neutral'}</span>
								</div>
							</div>
						{/if}

						{#if match.odds && match.odds.length > 0}
							{@const matchSelectionLockReason = getMatchSelectionLockReason(match)}
							{@const matchSelectionLocked = matchSelectionLockReason !== null}
							<div class="grid grid-cols-3 gap-2 pt-2 border-t border-border">
								<div class="text-center">
									<div class="text-xs text-muted-foreground">1</div>
									<div class="font-mono font-bold text-sm text-football-green">{match.odds[0].home_odds?.toFixed(2)}</div>
									<Button
										variant="secondary"
										size="sm"
										class="mt-2 w-full"
										title={matchSelectionLockReason ?? 'Add home selection to betslip'}
										disabled={matchSelectionLocked}
										onclick={() => addLiveSelection(match, '1', match.odds[0].home_odds)}
									>
										+1
									</Button>
								</div>
								<div class="text-center">
									<div class="text-xs text-muted-foreground">X</div>
									<div class="font-mono font-bold text-sm text-foreground">{match.odds[0].draw_odds?.toFixed(2) ?? '-'}</div>
									<Button
										variant="secondary"
										size="sm"
										class="mt-2 w-full"
										title={matchSelectionLockReason ?? 'Add draw selection to betslip'}
										onclick={() => addLiveSelection(match, 'X', match.odds[0].draw_odds)}
										disabled={match.odds[0].draw_odds === null || matchSelectionLocked}
									>
										+X
									</Button>
								</div>
								<div class="text-center">
									<div class="text-xs text-muted-foreground">2</div>
									<div class="font-mono font-bold text-sm text-football-blue">{match.odds[0].away_odds?.toFixed(2)}</div>
									<Button
										variant="secondary"
										size="sm"
										class="mt-2 w-full"
										title={matchSelectionLockReason ?? 'Add away selection to betslip'}
										disabled={matchSelectionLocked}
										onclick={() => addLiveSelection(match, '2', match.odds[0].away_odds)}
									>
										+2
									</Button>
								</div>
							</div>
							{#if matchSelectionLockReason}
								<div class="pt-2 text-[11px] text-orange-300">{matchSelectionLockReason}</div>
							{/if}
						{/if}

						{#if match.live_value_candidates?.length}
							<div class="pt-3 border-t border-border space-y-2">
								<div class="flex items-center justify-between gap-2">
									<div class="text-xs uppercase tracking-wider text-muted-foreground">Live Value Candidates</div>
									<div class="text-xs font-mono text-muted-foreground">Top {match.live_value_candidates.length}</div>
								</div>
									{#each match.live_value_candidates as candidate (`${candidate.market}-${candidate.selection}-${candidate.source}`)}
									{@const candidateSelectionLockReason = getCandidateSelectionLockReason(match, candidate)}
									<div class="rounded-md border border-border/70 bg-muted/40 p-2 space-y-2">
										<div class="flex items-center justify-between">
											<div>
												<div class="text-xs text-muted-foreground">Match Winner</div>
												<div class="font-mono font-bold">
													{candidateSelectionToSide(candidate.selection)} ({candidateSelectionLabel(candidate.selection)})
												</div>
												<div class="text-xs text-muted-foreground mt-1">{candidate.market} · {candidate.source}</div>
											</div>
											<div class={`text-xs font-mono rounded px-2 py-1 border ${confidenceBandColor(candidate.confidence_band)}`}>
												{candidate.confidence_band}
											</div>
										</div>
										<div class="grid grid-cols-3 gap-2 text-xs">
											<div>
												<div class="text-muted-foreground">Odds</div>
												<div class="font-mono font-bold text-foreground">{candidate.odds.toFixed(2)}</div>
											</div>
											<div>
												<div class="text-muted-foreground">Model</div>
												<div class="font-mono font-bold text-football-green">{formatPercent(candidate.model_probability)}</div>
											</div>
											<div>
												<div class="text-muted-foreground">Implied</div>
												<div class="font-mono font-bold text-football-blue">{formatPercent(candidate.implied_probability)}</div>
											</div>
										</div>
										<div class="grid grid-cols-2 gap-2 text-xs">
											<div>
												<div class="text-muted-foreground">Edge</div>
												<div class={`font-mono font-bold ${candidate.edge >= 0 ? 'text-football-green' : 'text-destructive'}`}>
													{formatEdge(candidate.edge)}
												</div>
											</div>
											<div>
												<div class="text-muted-foreground">EV</div>
												<div class={`font-mono font-bold ${candidate.expected_value >= 0 ? 'text-football-green' : 'text-destructive'}`}>
													{formatEVValue(candidate.expected_value)}
												</div>
											</div>
										</div>
										<div class="flex items-center justify-between pt-1 text-[11px] text-muted-foreground">
											<span>Prediction age: {formatPredictionAge(candidate.prediction_age_seconds)}</span>
											<Button
												variant="glow"
												size="sm"
												title={candidateSelectionLockReason ?? 'Add live value candidate to betslip'}
												disabled={candidateSelectionLockReason !== null}
												onclick={() => addLiveValueSelection(match, candidate)}
											>
												{candidateSelectionLockReason ? 'Locked' : 'Add to betslip'}
											</Button>
										</div>
										{#if candidateSelectionLockReason}
											<div class="text-[11px] text-orange-300">{candidateSelectionLockReason}</div>
										{/if}
									</div>
								{/each}
							</div>
						{/if}
					</div>
				</Card>
			{/each}
		</div>
	{/if}
</div>
