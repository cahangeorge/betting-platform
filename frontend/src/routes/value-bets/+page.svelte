<script lang="ts">
	import type { PageData } from './$types';
	import BetslipReviewCallout from '$lib/components/BetslipReviewCallout.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Loading from '$lib/components/Loading.svelte';
	import OddsMovement from '$lib/components/OddsMovement.svelte';
	import EdgeDistributionChart from '$lib/components/charts/EdgeDistributionChart.svelte';
	import { betslip, createBetslipLeg } from '$lib/stores/betslip';
	import { fade } from 'svelte/transition';

	let { data }: { data: PageData } = $props();

	let minEdge = $state(2);
	let selectedLeagues = $state<string[]>([]);
	let selectedMarket = $state<'all' | '1x2' | 'btts' | 'ou_2_5'>('all');
	let sortBy = $state<'edge' | 'time' | 'odds'>('edge');

	const allLeagues = ['Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1'];

	const filteredBets = $derived.by(() => {
		if (!data.valueBets) return [];
		let bets = data.valueBets.filter((b) => b.edge >= minEdge);
		if (selectedLeagues.length > 0) {
			bets = bets.filter((b) => b.league && selectedLeagues.includes(b.league));
		}
		if (selectedMarket !== 'all') {
			bets = bets.filter(b => b.market === selectedMarket);
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
		const edges = bets.map(b => b.edge);
		const odds = bets.map(b => b.odds);
		return {
			total: bets.length,
			avgEdge: edges.reduce((a, b) => a + b, 0) / edges.length,
			bestEdge: Math.max(...edges),
			avgOdds: odds.reduce((a, b) => a + b, 0) / odds.length
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
				buckets[key]++;
			}
		}
		return Object.entries(buckets).map(([edge, count]) => ({ edge, count }));
	});

	function toggleLeague(league: string) {
		if (selectedLeagues.includes(league)) {
			selectedLeagues = selectedLeagues.filter(l => l !== league);
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
		const p = (edge / 100) + (1 / odds);
		const q = 1 - p;
		const fraction = (p * odds - 1) / (odds - 1);
		return Math.max(0, bankroll * fraction * 0.25); // Quarter Kelly
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

	function addToBetslip(bet: PageData['valueBets'][number]) {
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
</script>

<svelte:head>
	<title>Value Bet Feed | Betfront</title>
	<meta name="description" content="Edge opportunities detected by your predictive models" />
</svelte:head>

<div class="space-y-6" transition:fade={{ duration: 200 }}>
	<!-- Header -->
	<div class="border-b border-border pb-4">
		<div class="flex items-center gap-3 mb-2">
			<div class="w-1 h-8 bg-football-green"></div>
			<h1 class="text-2xl font-extrabold tracking-tight font-sport text-foreground">VALUE BET FEED</h1>
		</div>
		<p class="text-muted-foreground">Edge opportunities detected by your predictive models</p>
	</div>
	{#if data.isDemo}
		<Card>
			<div class="p-4 border-l-4 border-yellow-400 bg-yellow-500/10 text-sm">
				<strong>Demo mode:</strong> feed is currently running with fallback data.
			</div>
		</Card>
	{/if}

	<BetslipReviewCallout label="Value bets are ready for final ticket review." />

	<!-- Filters -->
	<Card>
		<div class="p-4 space-y-4">
			<div class="flex flex-wrap items-center gap-4">
				<!-- Min Edge -->
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
						<span class="text-sm font-mono font-bold text-football-green min-w-12">{minEdge}%</span>
					</div>
				</div>

				<!-- Leagues -->
				<div class="space-y-1">
					<div class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Leagues</div>
					<div class="flex flex-wrap gap-2">
						{#each allLeagues as league (league)}
							<button
								onclick={() => toggleLeague(league)}
								class="px-3 py-1 text-xs font-medium border transition-all duration-200  font-mono {selectedLeagues.includes(league) ? 'bg-football-green/10 border-football-green text-football-green' : 'bg-transparent border-border text-muted-foreground'}"
							>
								{league}
							</button>
						{/each}
					</div>
				</div>

				<!-- Market -->
				<div class="space-y-1">
				<div class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Market</div>
					<div class="flex gap-1">
						{#each [['all', 'All'], ['1x2', '1X2'], ['ou_2_5', 'O/U'], ['btts', 'BTTS']] as [value, label] (value)}
							<button
								onclick={() => selectedMarket = value as 'all' | '1x2' | 'btts' | 'ou_2_5'}
								class="px-3 py-1 text-xs font-medium border transition-all duration-200  font-mono {selectedMarket === value ? 'bg-football-green/10 border-football-green text-football-green' : 'bg-transparent border-border text-muted-foreground'}"
							>
								{label}
							</button>
						{/each}
					</div>
				</div>

				<!-- Sort -->
				<div class="space-y-1">
					<label for="sort-by" class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Sort</label>
					<select id="sort-by"
							bind:value={sortBy}
						class="px-3 py-1 text-xs font-medium border bg-card border-border  text-foreground font-mono"
					>
						<option value="edge">Edge %</option>
						<option value="time">Kickoff</option>
						<option value="odds">Odds</option>
					</select>
				</div>
			</div>
		</div>
	</Card>

	<!-- Stats Row -->
	<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
		<Card>
			<div class="p-4 text-center">
				<div class="text-xs uppercase tracking-wider mb-1 text-muted-foreground">Total Bets</div>
				<div class="text-2xl font-bold font-mono text-football-green">{stats.total}</div>
			</div>
		</Card>
		<Card>
			<div class="p-4 text-center">
				<div class="text-xs uppercase tracking-wider mb-1 text-muted-foreground">Avg Edge</div>
				<div class="text-2xl font-bold font-mono text-football-green">{stats.avgEdge.toFixed(1)}%</div>
			</div>
		</Card>
		<Card>
			<div class="p-4 text-center">
				<div class="text-xs uppercase tracking-wider mb-1 text-muted-foreground">Best Edge</div>
				<div class="text-2xl font-bold font-mono text-football-green">{stats.bestEdge.toFixed(1)}%</div>
			</div>
		</Card>
		<Card>
			<div class="p-4 text-center">
				<div class="text-xs uppercase tracking-wider mb-1 text-muted-foreground">Avg Odds</div>
				<div class="text-2xl font-bold font-mono text-football-blue">{stats.avgOdds.toFixed(2)}</div>
			</div>
		</Card>
	</div>

	<!-- Edge Distribution Chart -->
	{#if edgeDistributionData.length > 0}
		<Card>
			<div class="p-4">
				<h3 class="text-sm font-medium uppercase tracking-wider mb-4 text-muted-foreground">Edge Distribution</h3>
				<EdgeDistributionChart data={edgeDistributionData} />
			</div>
		</Card>
	{/if}

	<!-- Value Bet List -->
	{#if data.loading}
		<div class="flex justify-center py-12">
			<Loading />
		</div>
	{:else if data.error}
		<Card>
			<div class="p-12 text-center">
				<h3 class="mb-2 text-lg font-semibold text-foreground">Value bets unavailable</h3>
				<p class="text-muted-foreground">{data.error}</p>
			</div>
		</Card>
	{:else if filteredBets.length === 0}
		<Card>
			<div class="p-12 text-center">
				<h3 class="text-lg font-semibold mb-2 text-foreground">No value bets match your criteria</h3>
				<p class="text-muted-foreground">Try lowering the minimum edge or selecting more leagues</p>
			</div>
		</Card>
	{:else}
		<div class="space-y-3">
			{#each filteredBets as bet (bet.id)}
				<Card interactive>
					<div class="p-4">
						<div class="flex flex-wrap items-center justify-between gap-4">
								<!-- Match Info -->
								<div class="flex-1 min-w-[200px]">
									<div class="flex items-center gap-2 mb-2">
										<Badge variant="info">{bet.league || 'TBD'}</Badge>
										<span class="text-xs font-mono text-muted-foreground">{timeUntil(bet.kickoff)}</span>
									</div>
								<div class="font-semibold font-sport text-foreground">
									<span class="text-football-blue">{bet.home_team}</span>
									<span class="mx-2 text-muted-foreground">vs</span>
									<span class="text-football-blue">{bet.away_team}</span>
								</div>
							</div>

							<!-- Selection -->
							<div class="text-center min-w-[120px]">
								<div class="text-xs uppercase tracking-wider mb-1 text-muted-foreground">
									{formatMarketLabel(bet.market)}
								</div>
								<div class="font-bold font-mono text-lg text-football-green">{bet.selection}</div>
							</div>

							<!-- Probabilities -->
							<div class="text-center min-w-[100px]">
								<div class="text-xs uppercase tracking-wider mb-1 text-muted-foreground">Model</div>
								<div class="font-mono font-bold text-foreground">{(bet.model_prob * 100).toFixed(1)}%</div>
								<div class="w-full h-1 mt-1 bg-muted">
									<div
										class="h-full transition-all duration-500"
										style="width: {bet.model_prob * 100}%; background: linear-gradient(90deg, oklch(0.72 0.19 155), oklch(0.65 0.15 250));"
									></div>
								</div>
							</div>

							<!-- Odds -->
							<div class="text-center min-w-[80px]">
								<div class="text-xs uppercase tracking-wider mb-1 text-muted-foreground">Odds</div>
								<div class="font-mono font-bold text-lg text-football-blue">{bet.odds.toFixed(2)}</div>
								<div class="text-xs font-mono text-muted-foreground/60">
									Implied: {(100 / bet.odds).toFixed(1)}%
								</div>
							</div>

							<!-- Edge -->
							<div class="min-w-[100px]">
								<div class="text-xs uppercase tracking-wider mb-1 text-muted-foreground">Edge</div>
								<div
									class="font-mono font-bold text-lg {bet.edge > 0 ? 'text-football-green' : 'text-destructive'}"
								>
									{formatEdge(bet.edge)}
								</div>
								<div class="w-full h-2 mt-1 bg-muted">
									<div
										class="h-full transition-all duration-500 {bet.edge > 0 ? 'bg-football-green' : 'bg-destructive'}"
										style="width: {Math.min(Math.abs(bet.edge) * 3, 100)}%;"
									></div>
								</div>
							</div>

							<!-- EV & Kelly -->
							<div class="text-right min-w-[120px]">
								<div class="text-xs font-mono mb-1 text-football-green">
									EV {formatEV(bet.edge, bet.odds)}
								</div>
								<div class="text-xs font-mono mb-2 text-muted-foreground/60">
									Kelly: £{kellyStake(bet.edge, bet.odds).toFixed(0)}
								</div>
								<Button variant="primary" class="w-full text-xs" onclick={() => addToBetslip(bet)}>ADD TO SLIP</Button>
							</div>
						</div>
					</div>
				</Card>
			{/each}
		</div>
	{/if}
</div>
