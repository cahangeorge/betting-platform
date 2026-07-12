<script lang="ts">
	import type { ValueOpportunitiesData as PageData } from './load-value';
	import BetslipReviewCallout from '$lib/components/BetslipReviewCallout.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Loading from '$lib/components/Loading.svelte';
	import EdgeDistributionChart from '$lib/components/charts/EdgeDistributionChart.svelte';
	import { betslip, createBetslipLeg } from '$lib/stores/betslip';
	import { oddsUpdates, predictionUpdates } from '$lib/stores/liveSocket';
	import { predictionsApi } from '$lib/api/predictions';
	import { fade } from 'svelte/transition';
	import { onMount } from 'svelte';

	let { data }: { data: PageData } = $props();

	let minEdge = $state(2);
	let selectedLeagues = $state<string[]>([]);
	let selectedMarket = $state<'all' | '1x2' | 'btts' | 'ou_2_5'>('all');
	let sortBy = $state<'edge' | 'time' | 'odds'>('edge');
	let isRefreshing = $state(false);
	let errorMessage = $state<string | null>(null);
	let valueBets = $state<PageData['valueBets']>([]);
	let isDemo = $state(false);
	let source = $state('prediction');
	let lastUpdated = $state(new Date().toISOString());
	let freshnessProbe = $state(Date.now());

	let socketRefreshDebounce: ReturnType<typeof setTimeout> | undefined;
	let refreshInterval: ReturnType<typeof setInterval> | undefined;
	let freshnessInterval: ReturnType<typeof setInterval> | undefined;

	const VALUE_TRUST_MAX_AGE_SECONDS = 15 * 60;
	const allLeagues = ['Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1'];

	$effect(() => {
		valueBets = data.valueBets ?? [];
		errorMessage = data.error ?? null;
		isDemo = data.isDemo ?? false;
		source = data.source ?? 'prediction';
		lastUpdated = data.generatedAt ?? new Date().toISOString();
	});

	const renderedBets = $derived(valueBets);

	const feedAgeSeconds = $derived.by(() => {
		freshnessProbe;
		const parsed = Date.parse(lastUpdated);
		if (Number.isNaN(parsed)) {
			return null;
		}
		return Math.max(0, Math.floor((Date.now() - parsed) / 1000));
	});

	const isFeedStale = $derived.by(
		() => feedAgeSeconds === null || feedAgeSeconds > VALUE_TRUST_MAX_AGE_SECONDS
	);

	const addToSlipLockReason = $derived.by(() => {
		if (isDemo) {
			return 'Value-bet add-to-betslip is locked while the page is showing demo data.';
		}
		if (source.trim().toLowerCase() === 'demo') {
			return 'Value-bet add-to-betslip is locked because the feed source is demo.';
		}
		if (feedAgeSeconds === null) {
			return 'Value-bet add-to-betslip is locked because feed freshness is unavailable.';
		}
		if (isFeedStale) {
			return `Value-bet add-to-betslip is locked because the feed is older than ${VALUE_TRUST_MAX_AGE_SECONDS / 60}m.`;
		}
		return null;
	});

	const filteredBets = $derived.by(() => {
		let bets = renderedBets.filter((bet) => bet.edge >= minEdge);
		if (selectedLeagues.length > 0) {
			bets = bets.filter((bet) => bet.league && selectedLeagues.includes(bet.league));
		}
		if (selectedMarket !== 'all') {
			bets = bets.filter((bet) => bet.market === selectedMarket);
		}
		bets.sort((a, b) => {
			if (sortBy === 'edge') return b.edge - a.edge;
			if (sortBy === 'time') return kickoffToMillis(a.kickoff) - kickoffToMillis(b.kickoff);
			return a.odds - b.odds;
		});
		return bets;
	});

	const stats = $derived.by(() => {
		const bets = filteredBets;
		if (bets.length === 0) return { total: 0, avgEdge: 0, bestEdge: 0, avgOdds: 0 };
		const edges = bets.map((bet) => bet.edge);
		const odds = bets.map((bet) => bet.odds);
		return {
			total: bets.length,
			avgEdge: edges.reduce((sum, edge) => sum + edge, 0) / edges.length,
			bestEdge: Math.max(...edges),
			avgOdds: odds.reduce((sum, odd) => sum + odd, 0) / odds.length
		};
	});

	const edgeDistributionData = $derived.by(() => {
		const bets = filteredBets;
		if (bets.length === 0) return [];
		const buckets: Record<string, number> = {};
		for (let i = 0; i <= 20; i += 2) {
			buckets[`${i}-${i + 2}%`] = 0;
		}
		for (const bet of bets) {
			const bucket = Math.floor(bet.edge / 2) * 2;
			const key = `${bucket}-${bucket + 2}%`;
			if (buckets[key] !== undefined) {
				buckets[key] += 1;
			}
		}
		return Object.entries(buckets).map(([edge, count]) => ({ edge, count }));
	});

	function toggleLeague(league: string) {
		if (selectedLeagues.includes(league)) {
			selectedLeagues = selectedLeagues.filter((item) => item !== league);
		} else {
			selectedLeagues = [...selectedLeagues, league];
		}
	}

	function formatEdge(edge: number): string {
		const sign = edge > 0 ? '+' : '';
		return `${sign}${edge.toFixed(1)}%`;
	}

	function formatEV(edge: number, odds: number, stake = 10): string {
		const ev = stake * ((edge / 100) * odds);
		const sign = ev >= 0 ? '+' : '';
		return `${sign}£${ev.toFixed(2)}`;
	}

	function formatMarketLabel(market: string): string {
		if (market === '1x2') return '1X2';
		if (market === 'ou_2_5' || market === 'over_under') return 'O/U';
		if (market === 'btts') return 'BTTS';
		return market.toUpperCase();
	}

	function kickoffToMillis(kickoff: string | null): number {
		if (!kickoff) return Number.POSITIVE_INFINITY;
		const ts = Date.parse(kickoff);
		return Number.isNaN(ts) ? Number.POSITIVE_INFINITY : ts;
	}

	function kellyStake(edge: number, odds: number, bankroll = 10000): number {
		const p = edge / 100 + 1 / odds;
		const fraction = (p * odds - 1) / (odds - 1);
		return Math.max(0, bankroll * fraction * 0.25);
	}

	function timeUntil(kickoff: string | null): string {
		if (!kickoff) return 'TBD';
		const now = new Date();
		const kick = new Date(kickoff);
		const diff = kick.getTime() - now.getTime();
		if (diff <= 0) return 'LIVE';
		const hours = Math.floor(diff / (1000 * 60 * 60));
		const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
		if (hours > 0) return `${hours}h ${mins}m`;
		return `${mins}m`;
	}

	function timeAgo(iso: string): string {
		const date = new Date(iso);
		const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
		if (seconds < 60) return `${seconds}s ago`;
		const minutes = Math.floor(seconds / 60);
		if (minutes < 60) return `${minutes}m ago`;
		const hours = Math.floor(minutes / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		return `${days}d ago`;
	}

	function reliabilityVariant(label: string | null | undefined): 'success' | 'warning' | 'danger' | 'neutral' {
		if (label === 'reliable' || label === 'trusted') return 'success';
		if (label === 'moderate') return 'warning';
		if (label === 'unreliable') return 'danger';
		return 'neutral';
	}

	function formatTrustReason(reason: string): string {
		return reason
			.replaceAll('_', ' ')
			.replace(/\b\w/g, (letter) => letter.toUpperCase());
	}

	function getBetTrustReasons(bet: PageData['valueBets'][number]): string[] {
		return Array.from(
			new Set([...(bet.block_reasons ?? []), ...(bet.quality_reasons ?? []), ...(bet.trust?.block_reasons ?? [])])
		);
	}

	function getBetLockReason(bet: PageData['valueBets'][number]): string | null {
		if (addToSlipLockReason) {
			return addToSlipLockReason;
		}
		if (bet.is_ticket_eligible === false || bet.trust?.is_ticket_eligible === false) {
			const reasons = getBetTrustReasons(bet);
			if (reasons.length > 0) {
				return `Betslip locked: ${reasons.map(formatTrustReason).join(' · ')}.`;
			}
			return 'This value bet is currently marked as not eligible for the betslip.';
		}
		const trustReasons = getBetTrustReasons(bet);
		if (trustReasons.length > 0) {
			return `Betslip locked: ${trustReasons.map(formatTrustReason).join(' · ')}.`;
		}
		if (bet.source_ok === false || bet.trust?.source_ok === false) {
			return 'This value bet is locked because its backing source checks are not green.';
		}
		if (bet.model_drift_flag || bet.trust?.model_drift_flag) {
			return 'This value bet is locked because the model drift guardrail is active.';
		}
		if (bet.reliability === 'unreliable') {
			return 'This value bet is flagged as unreliable by the prediction quality report.';
		}
		return null;
	}

	const trustReadyCount = $derived.by(() => filteredBets.filter((bet) => getBetLockReason(bet) === null).length);
	const monitorOnlyCount = $derived.by(() => filteredBets.length - trustReadyCount);
	const betslipReviewLabel = $derived.by(() => {
		if (addToSlipLockReason) {
			return 'Value bets are in monitor-only mode until feed trust checks recover.';
		}
		if (monitorOnlyCount > 0) {
			return `${trustReadyCount} value bet${trustReadyCount === 1 ? '' : 's'} can be added now; ${monitorOnlyCount} require review.`;
		}
		return 'All listed value bets currently pass the available betslip trust checks.';
	});

	async function refreshValueBets() {
		if (isRefreshing) {
			return;
		}

		isRefreshing = true;
		errorMessage = null;
		try {
			const response = await predictionsApi.getValueBets();
			valueBets = response.items ?? [];
			isDemo = response.is_demo;
			source = response.source;
			lastUpdated = response.generated_at;
			if ((response.items ?? []).length === 0) {
				errorMessage = 'No value bets are currently available.';
			}
		} catch (error) {
			errorMessage = error instanceof Error ? error.message : 'Failed to refresh value bets.';
		} finally {
			freshnessProbe = Date.now();
			isRefreshing = false;
		}
	}

	function scheduleSocketRefresh() {
		if (socketRefreshDebounce) {
			clearTimeout(socketRefreshDebounce);
		}
		socketRefreshDebounce = setTimeout(() => {
			socketRefreshDebounce = undefined;
			void refreshValueBets();
		}, 200);
	}

	function addToBetslip(bet: PageData['valueBets'][number]) {
		if (getBetLockReason(bet)) {
			return;
		}
		betslip.addLeg(
			createBetslipLeg({
				matchId: bet.match_id,
				modelPredictionId: bet.id,
				matchName: `${bet.home_team} vs ${bet.away_team}`,
				market: bet.market,
				selection: bet.selection,
				odds: bet.odds,
				league: bet.league || 'TBD',
				kickoff: bet.kickoff || undefined,
				source: 'value-bet'
			})
		);
	}

	onMount(() => {
		freshnessInterval = setInterval(() => {
			freshnessProbe = Date.now();
		}, 15000);

		refreshInterval = setInterval(() => {
			void refreshValueBets();
		}, 30000);

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

		return () => {
			unsubscribeOddsUpdates();
			unsubscribePredictionUpdates();
			if (refreshInterval) clearInterval(refreshInterval);
			if (freshnessInterval) clearInterval(freshnessInterval);
			if (socketRefreshDebounce) clearTimeout(socketRefreshDebounce);
		};
	});
</script>

<svelte:head>
	<title>Value Bet Feed | Betfront</title>
	<meta name="description" content="Edge opportunities detected by your predictive models" />
</svelte:head>

<div class="space-y-6" transition:fade={{ duration: 200 }}>
	<div class="border-b border-border pb-4">
		<div class="mb-2 flex items-center gap-3">
			<div class="h-8 w-1 bg-football-green"></div>
			<h1 class="font-sport text-2xl font-extrabold tracking-tight text-foreground">VALUE BET FEED</h1>
			<div class="ml-auto text-xs font-mono text-muted-foreground/60">
				{isRefreshing ? 'Refreshing…' : `Updated ${timeAgo(lastUpdated)}`}
			</div>
		</div>
		<p class="text-muted-foreground">Edge opportunities detected by your predictive models</p>
	</div>

	{#if isFeedStale}
		<Card>
			<div class="border-l-4 border-yellow-500 bg-yellow-500/10 p-4 text-sm">
				<span class="font-medium">Value feed may be stale</span>
				{#if feedAgeSeconds !== null}
					· generated ~{feedAgeSeconds < 60 ? `${feedAgeSeconds}s` : `${Math.floor(feedAgeSeconds / 60)}m`} ago.
				{/if}
			</div>
		</Card>
	{/if}

	{#if addToSlipLockReason}
		<Card>
			<div class="border-l-4 border-orange-500 bg-orange-500/10 p-4 text-sm">
				<div class="font-medium">Monitor-only mode for value-bet betslip actions</div>
				<div class="mt-1 text-muted-foreground">{addToSlipLockReason}</div>
			</div>
		</Card>
	{/if}

	{#if isDemo}
		<Card>
			<div class="border-l-4 border-red-500 bg-red-500/10 p-4 text-sm">
				<span class="font-medium">Demo data mode</span> · source: {source}
			</div>
		</Card>
	{/if}

	<Card>
		<div class="flex flex-wrap items-center gap-3 p-4 text-xs text-muted-foreground">
			<Badge variant="info">Source: {source}</Badge>
			<Badge variant={isFeedStale ? 'warning' : 'success'}>
				Feed age: {feedAgeSeconds === null ? 'unknown' : timeAgo(lastUpdated)}
			</Badge>
			<Badge variant={monitorOnlyCount > 0 || addToSlipLockReason ? 'warning' : 'success'}>
				Betslip ready: {trustReadyCount}/{filteredBets.length}
			</Badge>
			<span>Auto-refreshes on prediction and odds websocket updates.</span>
		</div>
	</Card>

	<BetslipReviewCallout label={betslipReviewLabel} />

	<Card>
		<div class="space-y-4 p-4">
			<div class="flex flex-wrap items-center gap-4">
				<div class="space-y-1">
					<label for="min-edge" class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Min Edge</label>
					<div class="flex items-center gap-2">
						<input
							id="min-edge"
							type="range"
							min="0"
							max="20"
							step="0.5"
							bind:value={minEdge}
							class="w-32 accent-football-green"
						/>
						<span class="min-w-12 text-sm font-bold font-mono text-football-green">{minEdge}%</span>
					</div>
				</div>

				<div class="space-y-1">
					<div class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Leagues</div>
					<div class="flex flex-wrap gap-2">
						{#each allLeagues as league (league)}
							<button
								onclick={() => toggleLeague(league)}
								class="px-3 py-1 text-xs font-medium border transition-all duration-200 font-mono {selectedLeagues.includes(league) ? 'bg-football-green/10 border-football-green text-football-green' : 'bg-transparent border-border text-muted-foreground'}"
							>
								{league}
							</button>
						{/each}
					</div>
				</div>

				<div class="space-y-1">
					<div class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Market</div>
					<div class="flex gap-1">
						{#each [['all', 'All'], ['1x2', '1X2'], ['ou_2_5', 'O/U'], ['btts', 'BTTS']] as [value, label] (value)}
							<button
								onclick={() => (selectedMarket = value as 'all' | '1x2' | 'btts' | 'ou_2_5')}
								class="font-mono text-xs font-medium transition-all duration-200 px-3 py-1 border {selectedMarket === value ? 'border-football-green bg-football-green/10 text-football-green' : 'border-border bg-transparent text-muted-foreground'}"
							>
								{label}
							</button>
						{/each}
					</div>
				</div>

				<div class="space-y-1">
					<label for="sort-by" class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Sort</label>
					<select
						id="sort-by"
						bind:value={sortBy}
						class="border-border bg-card px-3 py-1 font-mono text-xs font-medium text-foreground"
					>
						<option value="edge">Edge %</option>
						<option value="time">Kickoff</option>
						<option value="odds">Odds</option>
					</select>
				</div>
			</div>
		</div>
	</Card>

	<div class="grid grid-cols-2 gap-4 md:grid-cols-4">
		<Card>
			<div class="p-4 text-center">
				<div class="mb-1 text-xs uppercase tracking-wider text-muted-foreground">Total Bets</div>
				<div class="font-mono text-2xl font-bold text-football-green">{stats.total}</div>
			</div>
		</Card>
		<Card>
			<div class="p-4 text-center">
				<div class="mb-1 text-xs uppercase tracking-wider text-muted-foreground">Avg Edge</div>
				<div class="font-mono text-2xl font-bold text-football-green">{stats.avgEdge.toFixed(1)}%</div>
			</div>
		</Card>
		<Card>
			<div class="p-4 text-center">
				<div class="mb-1 text-xs uppercase tracking-wider text-muted-foreground">Best Edge</div>
				<div class="font-mono text-2xl font-bold text-football-green">{stats.bestEdge.toFixed(1)}%</div>
			</div>
		</Card>
		<Card>
			<div class="p-4 text-center">
				<div class="mb-1 text-xs uppercase tracking-wider text-muted-foreground">Avg Odds</div>
				<div class="text-2xl font-bold font-mono text-football-blue">{stats.avgOdds.toFixed(2)}</div>
			</div>
		</Card>
	</div>

	{#if edgeDistributionData.length > 0}
		<Card>
			<div class="p-4">
				<h3 class="mb-4 text-sm font-medium uppercase tracking-wider text-muted-foreground">Edge Distribution</h3>
				<EdgeDistributionChart data={edgeDistributionData} />
			</div>
		</Card>
	{/if}

	{#if data.loading || isRefreshing && renderedBets.length === 0}
		<div class="flex justify-center py-12">
			<Loading />
		</div>
	{:else if errorMessage}
		<Card>
			<div class="p-12 text-center">
				<h3 class="mb-2 text-lg font-semibold text-foreground">Value bets unavailable</h3>
				<p class="text-muted-foreground">{errorMessage}</p>
			</div>
		</Card>
	{:else if filteredBets.length === 0}
		<Card>
			<div class="p-12 text-center">
				<h3 class="mb-2 text-lg font-semibold text-foreground">No value bets match your criteria</h3>
				<p class="text-muted-foreground">Try lowering the minimum edge or selecting more leagues</p>
			</div>
		</Card>
	{:else}
		<div class="space-y-3">
			{#each filteredBets as bet (bet.id)}
				{@const betLockReason = getBetLockReason(bet)}
				<Card interactive>
					<div class="p-4">
						<div class="flex flex-wrap items-center justify-between gap-4">
							<div class="min-w-[220px] flex-1">
								<div class="mb-2 flex flex-wrap items-center gap-2">
									<Badge variant="info">{bet.league || 'TBD'}</Badge>
									<span class="text-xs font-mono text-muted-foreground">{timeUntil(bet.kickoff)}</span>
									{#if bet.reliability}
										<Badge variant={reliabilityVariant(bet.reliability)}>{bet.reliability}</Badge>
									{/if}
								</div>
								<div class="font-sport font-semibold text-foreground">
									<span class="text-football-blue">{bet.home_team}</span>
									<span class="mx-2 text-muted-foreground">vs</span>
									<span class="text-football-blue">{bet.away_team}</span>
								</div>
								<div class="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
									<span>{bet.model_type}</span>
									<span>· source: {bet.source}</span>
									<span>· confidence: {bet.confidence.toFixed(0)}%</span>
									{#if bet.reliability_score !== null && bet.reliability_score !== undefined}
										<span>· trust score: {bet.reliability_score}</span>
									{/if}
								</div>
							</div>

							<div class="min-w-[120px] text-center">
								<div class="mb-1 text-xs uppercase tracking-wider text-muted-foreground">
									{formatMarketLabel(bet.market)}
								</div>
								<div class="font-mono text-lg font-bold text-football-green">{bet.selection}</div>
							</div>

							<div class="min-w-[100px] text-center">
								<div class="mb-1 text-xs uppercase tracking-wider text-muted-foreground">Model</div>
								<div class="font-mono font-bold text-foreground">{(bet.model_prob * 100).toFixed(1)}%</div>
								<div class="mt-1 h-1 w-full bg-muted">
									<div
										class="h-full transition-all duration-500"
										style="width: {bet.model_prob * 100}%; background: linear-gradient(90deg, oklch(0.72 0.19 155), oklch(0.65 0.15 250));"
									></div>
								</div>
							</div>

							<div class="min-w-[80px] text-center">
								<div class="mb-1 text-xs uppercase tracking-wider text-muted-foreground">Odds</div>
								<div class="font-mono text-lg font-bold text-football-blue">{bet.odds.toFixed(2)}</div>
								<div class="text-xs font-mono text-muted-foreground/60">
									Implied: {(100 / bet.odds).toFixed(1)}%
								</div>
							</div>

							<div class="min-w-[100px]">
								<div class="mb-1 text-xs uppercase tracking-wider text-muted-foreground">Edge</div>
								<div class="font-mono text-lg font-bold {bet.edge > 0 ? 'text-football-green' : 'text-destructive'}">
									{formatEdge(bet.edge)}
								</div>
								<div class="mt-1 h-2 w-full bg-muted">
									<div
										class="h-full transition-all duration-500 {bet.edge > 0 ? 'bg-football-green' : 'bg-destructive'}"
										style="width: {Math.min(Math.abs(bet.edge) * 3, 100)}%;"
									></div>
								</div>
							</div>

							<div class="min-w-[140px] text-right">
								<div class="mb-1 text-xs font-mono text-football-green">EV {formatEV(bet.edge, bet.odds)}</div>
								<div class="mb-2 text-xs font-mono text-muted-foreground/60">
									Kelly: £{kellyStake(bet.edge, bet.odds).toFixed(0)}
								</div>
								<Button
									variant="primary"
									class="w-full text-xs"
									title={betLockReason ?? 'Add value bet to betslip'}
									disabled={betLockReason !== null}
									onclick={() => addToBetslip(bet)}
								>
									{betLockReason ? 'Locked' : 'ADD TO SLIP'}
								</Button>
							</div>
						</div>

						{#if bet.quality_reasons?.length}
							<div class="mt-3 rounded-md border border-border/70 bg-muted/30 p-2 text-[11px] text-muted-foreground">
								<div class="font-medium text-foreground">Quality notes</div>
								<div class="mt-1">{bet.quality_reasons.map(formatTrustReason).join(' · ')}</div>
							</div>
						{/if}

						{#if betLockReason}
							<div class="pt-2 text-[11px] text-orange-300">{betLockReason}</div>
						{/if}
					</div>
				</Card>
			{/each}
		</div>
	{/if}
</div>
