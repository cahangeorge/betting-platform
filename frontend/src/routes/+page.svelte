<script lang="ts">
	import { fade, slide } from 'svelte/transition';
	import Card from '$lib/components/ui/Card.svelte';
	import BetslipReviewCallout from '$lib/components/BetslipReviewCallout.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Skeleton from '$lib/components/ui/skeleton/skeleton.svelte';
	import { dashboardApi } from '$lib/api/dashboard';
	import { predictionsApi } from '$lib/api/predictions';
	import { betslip, createBetslipLeg } from '$lib/stores/betslip';
	import type {
		DashboardSummary,
		DashboardTicket,
		DashboardTicketOutcomeBucket,
		DashboardTicketOutcomeResponse,
		PredictionVerification,
		UpcomingMatch
	} from '$lib/types';

	type DashboardTab = 'history' | 'future';
	type HistoryRange = 'today' | '7d' | '1m' | '3m' | '6m' | '1y';
	type FuturePeriod = '1' | '7' | '30';
	type DashboardLeg = DashboardTicket['legs'][number] & {
		model_probability?: number | null;
		model_prob?: number | null;
		probability?: number | null;
		final_score?: string | null;
		result?: string | null;
	};
	type ValueBetItem = {
		id: number;
		match_id: number;
		league: string | null;
		home_team: string;
		away_team: string;
		kickoff: string | null;
		market: string;
		selection: string;
		model_prob: number;
		odds: number;
		edge: number;
		model_type: string;
		confidence: number;
		reliability?: string | null;
		source?: string;
	};

	let activeTab = $state<DashboardTab>('history');
	let historyRange = $state<HistoryRange>('7d');
	let futurePeriod = $state<FuturePeriod>('7');
	let selectedLeague = $state('all');
	let selectedMarket = $state('all');

	let summary = $state<DashboardSummary | null>(null);
	let tickets = $state<DashboardTicket[]>([]);
	let futureTickets = $state<DashboardTicket[]>([]);
	let ticketOutcomes = $state<DashboardTicketOutcomeResponse | null>(null);
	let selectedOutcomeBucketKey = $state<string | null>(null);
	let selectedOutcomeTickets = $state<DashboardTicket[]>([]);
	let expandedHistoryTicket = $state<number | null>(null);
	let expandedFutureTicket = $state<number | null>(null);

	let upcoming = $state<UpcomingMatch[]>([]);
	let valueBets = $state<ValueBetItem[]>([]);
	let verification = $state<PredictionVerification | null>(null);

	let summaryLoading = $state(true);
	let ticketsLoading = $state(true);
	let outcomesLoading = $state(true);
	let selectedOutcomeTicketsLoading = $state(false);
	let futureTicketsLoading = $state(true);
	let upcomingLoading = $state(true);
	let valueBetsLoading = $state(true);
	let verificationLoading = $state(true);

	let ticketsError = $state<string | null>(null);
	let outcomesError = $state<string | null>(null);
	let upcomingError = $state<string | null>(null);
	let valueBetsError = $state<string | null>(null);
	let verificationError = $state<string | null>(null);

	const tabs: { value: DashboardTab; label: string; description: string }[] = [
		{ value: 'history', label: 'Istoric', description: 'Rezultate, verificari si bilete decontate' },
		{ value: 'future', label: 'Viitor', description: 'Meciuri viitoare, predictii si bilete active' }
	];

	const historyRangeOptions: { value: HistoryRange; label: string }[] = [
		{ value: 'today', label: 'Azi' },
		{ value: '7d', label: '7 zile' },
		{ value: '1m', label: '1 luna' },
		{ value: '3m', label: '3 luni' },
		{ value: '6m', label: '6 luni' },
		{ value: '1y', label: '1 an' }
	];

	const futurePeriodOptions: { value: FuturePeriod; label: string }[] = [
		{ value: '1', label: 'Azi' },
		{ value: '7', label: '7 zile' },
		{ value: '30', label: '30 zile' }
	];

	const ticketOutcomeBuckets = $derived(
		ticketOutcomes?.items?.length ? ticketOutcomes.items : buildOutcomeBuckets(tickets, historyRange)
	);
	const selectedBucket = $derived(
		selectedOutcomeBucketKey
			? ticketOutcomeBuckets.find((bucket) => bucketKey(bucket) === selectedOutcomeBucketKey) ?? null
			: null
	);
	const maxOutcomeCount = $derived(
		Math.max(1, ...ticketOutcomeBuckets.map((bucket) => bucket.won + bucket.lost + bucket.void + bucket.pending))
	);
	const hasOutcomeData = $derived(
		ticketOutcomeBuckets.some((bucket) => bucket.won + bucket.lost + bucket.void + bucket.pending > 0)
	);

	const verificationItems = $derived(verification?.items ?? []);
	const verificationAccuracy = $derived(verification?.accuracy ?? null);

	const valueBetsByMatch = $derived.by(() => {
		const byMatch = new Map<number, ValueBetItem[]>();
		for (const item of valueBets) {
			const current = byMatch.get(item.match_id) ?? [];
			current.push(item);
			byMatch.set(item.match_id, current);
		}
		return byMatch;
	});

	const leagueOptions = $derived([
		{ value: 'all', label: 'Toate ligile' },
		...Array.from(new Set(upcoming.map((match) => match.league).filter(Boolean)))
			.sort((a, b) => a.localeCompare(b))
			.map((league) => ({ value: league, label: league }))
	]);
	const marketOptions = $derived([
		{ value: 'all', label: 'Toate pietele' },
		...Array.from(new Set(valueBets.map((item) => item.market).filter(Boolean)))
			.sort((a, b) => a.localeCompare(b))
			.map((market) => ({ value: market, label: market }))
	]);
	const filteredUpcoming = $derived(
		upcoming.filter((match) => {
			if (selectedLeague !== 'all' && match.league !== selectedLeague) return false;
			if (selectedMarket === 'all') return true;
			return (valueBetsByMatch.get(match.id) ?? []).some((prediction) => prediction.market === selectedMarket);
		})
	);

	async function fetchSummary() {
		summaryLoading = true;
		try {
			summary = await dashboardApi.getSummary();
		} catch {
			summary = null;
		} finally {
			summaryLoading = false;
		}
	}

	async function fetchHistoryData() {
		selectedOutcomeBucketKey = null;
		selectedOutcomeTickets = [];
		expandedHistoryTicket = null;
		await Promise.all([fetchTickets(), fetchTicketOutcomes()]);
	}

	async function fetchTickets() {
		ticketsLoading = true;
		ticketsError = null;
		try {
			tickets = await dashboardApi.getRecentTickets({ limit: 100, date_from: rangeDateFrom(historyRange) });
		} catch {
			tickets = [];
			ticketsError = 'Nu am putut incarca biletele recente din dashboard.';
		} finally {
			ticketsLoading = false;
		}
	}

	async function fetchTicketOutcomes() {
		outcomesLoading = true;
		outcomesError = null;
		try {
			ticketOutcomes = await dashboardApi.getTicketOutcomes(historyRange);
		} catch {
			ticketOutcomes = null;
			outcomesError = 'Endpoint-ul pentru agregarea biletelor nu este disponibil; folosesc lista recenta de bilete ca fallback.';
		} finally {
			outcomesLoading = false;
		}
	}

	async function fetchSelectedOutcomeTickets(bucket: DashboardTicketOutcomeBucket) {
		selectedOutcomeBucketKey = bucketKey(bucket);
		expandedHistoryTicket = null;
		selectedOutcomeTicketsLoading = true;
		try {
			const date = dateOnly(bucket.bucket_start);
			selectedOutcomeTickets = await dashboardApi.getTicketOutcomeTickets({ date_from: date, date_to: date, limit: 100 });
		} catch {
			const ids = new Set(bucket.ticket_ids);
			selectedOutcomeTickets = tickets.filter((ticket) => ids.has(ticket.id));
		} finally {
			selectedOutcomeTicketsLoading = false;
		}
	}

	async function fetchFutureTickets() {
		futureTicketsLoading = true;
		try {
			const recent = await dashboardApi.getRecentTickets({ limit: 50 });
			futureTickets = recent.filter(isFutureTicket);
		} catch {
			futureTickets = [];
		} finally {
			futureTicketsLoading = false;
		}
	}

	async function fetchUpcoming() {
		upcomingLoading = true;
		upcomingError = null;
		try {
			upcoming = await dashboardApi.getUpcoming(Number(futurePeriod));
		} catch {
			upcoming = [];
			upcomingError = 'Nu am putut incarca meciurile viitoare din dashboard.';
		} finally {
			upcomingLoading = false;
		}
	}

	async function fetchValueBets() {
		valueBetsLoading = true;
		valueBetsError = null;
		try {
			const feed = await predictionsApi.getValueBets();
			valueBets = feed.items as ValueBetItem[];
		} catch {
			valueBets = [];
			valueBetsError = 'Predictiile viitoare nu sunt disponibile din API-ul existent.';
		} finally {
			valueBetsLoading = false;
		}
	}

	async function fetchVerification() {
		verificationLoading = true;
		verificationError = null;
		try {
			verification = await predictionsApi.verify();
		} catch {
			verification = null;
			verificationError = 'Verificarea predictiilor nu este disponibila in acest moment.';
		} finally {
			verificationLoading = false;
		}
	}

	function rangeDays(range: HistoryRange): number {
		const days: Record<HistoryRange, number> = {
			today: 1,
			'7d': 7,
			'1m': 31,
			'3m': 93,
			'6m': 186,
			'1y': 366
		};
		return days[range];
	}

	function rangeDateFrom(range: HistoryRange): string {
		const start = startOfToday();
		start.setUTCDate(start.getUTCDate() - rangeDays(range) + 1);
		return dateOnly(start.toISOString());
	}

	function startOfToday(): Date {
		const now = new Date();
		return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
	}

	function buildOutcomeBuckets(sourceTickets: DashboardTicket[], range: HistoryRange): DashboardTicketOutcomeBucket[] {
		const days = rangeDays(range);
		const start = startOfToday();
		start.setUTCDate(start.getUTCDate() - days + 1);
		const buckets: DashboardTicketOutcomeBucket[] = Array.from({ length: days }, (_, index) => {
			const bucketStart = new Date(start);
			bucketStart.setUTCDate(start.getUTCDate() + index);
			const bucketEnd = new Date(bucketStart);
			bucketEnd.setUTCDate(bucketStart.getUTCDate() + 1);
			return {
				bucket_start: bucketStart.toISOString(),
				bucket_end: bucketEnd.toISOString(),
				won: 0,
				lost: 0,
				void: 0,
				pending: 0,
				ticket_ids: []
			};
		});
		const byDay = new Map(buckets.map((bucket) => [dateOnly(bucket.bucket_start), bucket]));
		for (const ticket of sourceTickets) {
			const bucket = byDay.get(dateOnly(ticket.created_at));
			if (!bucket) continue;
			const status = ticket.status.toLowerCase();
			if (status === 'won') bucket.won += 1;
			else if (status === 'lost') bucket.lost += 1;
			else if (status === 'void' || status === 'cashed_out') bucket.void += 1;
			else bucket.pending += 1;
			bucket.ticket_ids.push(ticket.id);
		}
		return buckets;
	}

	function bucketKey(bucket: DashboardTicketOutcomeBucket): string {
		return bucket.bucket_start;
	}

	function dateOnly(iso: string): string {
		return new Date(iso).toISOString().slice(0, 10);
	}

	function barHeight(count: number): string {
		return `${Math.max(6, Math.round((count / maxOutcomeCount) * 112))}px`;
	}

	function isFutureTicket(ticket: DashboardTicket): boolean {
		const status = ticket.status.toLowerCase();
		return !['won', 'lost', 'void', 'cashed_out'].includes(status) || ticket.legs.some((leg) => leg.status === 'pending');
	}

	function settledLegs(ticket: DashboardTicket): number {
		return ticket.legs.filter((leg) => ['won', 'lost', 'void'].includes(leg.status)).length;
	}

	function ticketChance(ticket: DashboardTicket): number | null {
		const probabilities = ticket.legs
			.map((leg) => legProbability(leg))
			.filter((value): value is number => value !== null);
		if (probabilities.length !== ticket.legs.length || probabilities.length === 0) return null;
		return probabilities.reduce((product, value) => product * normaliseProbability(value), 1);
	}

	function legProbability(leg: DashboardLeg): number | null {
		return leg.model_probability ?? leg.model_prob ?? leg.probability ?? null;
	}

	function normaliseProbability(value: number): number {
		return value > 1 ? value / 100 : value;
	}

	function ticketPnl(ticket: DashboardTicket): number | null {
		if (ticket.actual_return === null) return null;
		return ticket.actual_return - ticket.stake;
	}

	function statusBadgeVariant(status: string): 'success' | 'danger' | 'warning' | 'neutral' {
		const normalized = status.toLowerCase();
		if (normalized === 'won') return 'success';
		if (normalized === 'lost') return 'danger';
		if (normalized === 'pending' || normalized === 'open' || normalized === 'watchlist') return 'warning';
		return 'neutral';
	}

	function verificationStatusVariant(status: string): 'success' | 'danger' | 'warning' | 'neutral' {
		if (status === 'won') return 'success';
		if (status === 'lost') return 'danger';
		if (status === 'pending' || status === 'unsupported') return 'warning';
		return 'neutral';
	}

	function formatCurrency(v: number): string {
		return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'EUR' }).format(v);
	}

	function formatPercent(value: number | null | undefined): string {
		if (value === null || value === undefined || Number.isNaN(value)) return '--';
		return `${(normaliseProbability(value) * 100).toFixed(1)}%`;
	}

	function formatNumber(value: number | null | undefined, digits = 2): string {
		if (value === null || value === undefined || Number.isNaN(value)) return '--';
		return value.toFixed(digits);
	}

	function formatDate(iso: string | null | undefined): string {
		if (!iso) return '--';
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return '--';
		return d.toLocaleDateString('ro-RO', { day: 'numeric', month: 'short', year: 'numeric' });
	}

	function formatDateTime(iso: string | null | undefined): string {
		if (!iso) return '--';
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return '--';
		return d.toLocaleString('ro-RO', {
			day: 'numeric',
			month: 'short',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function formatBucketLabel(bucket: DashboardTicketOutcomeBucket): string {
		return new Date(bucket.bucket_start).toLocaleDateString('ro-RO', { day: '2-digit', month: 'short' });
	}

	function finalScore(leg: DashboardLeg): string {
		if (leg.home_score !== null && leg.away_score !== null) return `${leg.home_score} - ${leg.away_score}`;
		return leg.final_score ?? '--';
	}

	function predictionForMatch(match: UpcomingMatch): ValueBetItem[] {
		return valueBetsByMatch.get(match.id) ?? [];
	}

	function addMatchToBetSlip(
		match: UpcomingMatch,
		selection: { key: 'home' | 'draw' | 'away'; label: 'Home' | 'Draw' | 'Away'; odds: number | null }
	) {
		if (!selection.odds) return;
		betslip.addLeg(
			createBetslipLeg({
				matchId: match.id,
				matchName: `${match.home_team} vs ${match.away_team}`,
				market: '1X2',
				selection: selection.label,
				odds: selection.odds,
				league: match.league,
				kickoff: match.start_time,
				source: 'dashboard'
			})
		);
	}

	$effect(() => {
		void historyRange;
		void fetchHistoryData();
	});

	$effect(() => {
		void futurePeriod;
		void fetchUpcoming();
	});

	$effect(() => {
		void fetchSummary();
		void fetchFutureTickets();
		void fetchValueBets();
		void fetchVerification();
	});
</script>

<div class="min-w-0 space-y-6" transition:fade={{ duration: 200 }}>
	<BetslipReviewCallout label="Dashboard picks are ready for ticket review." />

	<section class="min-w-0 space-y-4">
		<div class="min-w-0 space-y-2">
			<p class="text-xs font-semibold uppercase tracking-[0.28em] text-muted-foreground">Dashboard</p>
			<div class="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
				<div class="min-w-0">
					<h1 class="text-2xl font-extrabold text-foreground sm:text-3xl">Rezultate si oportunitati</h1>
					<p class="mt-1 max-w-3xl text-sm text-muted-foreground">
						Istoric pentru bilete si predictii verificate, plus meciuri si bilete active pentru perioada urmatoare.
					</p>
				</div>
				{#if summaryLoading}
					<Skeleton class="h-16 w-full lg:w-72" />
				{:else if summary}
					<div class="grid min-w-0 grid-cols-3 gap-2 rounded-lg border border-border bg-card p-3 text-center lg:w-80">
						<div class="min-w-0">
							<p class="text-[10px] uppercase text-muted-foreground">Bilete</p>
							<p class="font-mono text-lg font-bold text-foreground">{summary.total_tickets}</p>
						</div>
						<div class="min-w-0">
							<p class="text-[10px] uppercase text-muted-foreground">Win rate</p>
							<p class="font-mono text-lg font-bold text-football-green">{summary.win_rate.toFixed(1)}%</p>
						</div>
						<div class="min-w-0">
							<p class="text-[10px] uppercase text-muted-foreground">P&L</p>
							<p class="truncate font-mono text-lg font-bold {summary.total_pnl >= 0 ? 'text-football-green' : 'text-football-red'}">
								{formatCurrency(summary.total_pnl)}
							</p>
						</div>
					</div>
				{/if}
			</div>
		</div>

		<div class="flex min-w-0 flex-wrap gap-2" role="tablist" aria-label="Dashboard sections">
			{#each tabs as tab (tab.value)}
				<button
					class="min-w-0 rounded-lg border px-4 py-3 text-left transition {activeTab === tab.value ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card text-foreground hover:bg-secondary'}"
					role="tab"
					aria-selected={activeTab === tab.value}
					onclick={() => (activeTab = tab.value)}
				>
					<span class="block text-sm font-bold">{tab.label}</span>
					<span class="block text-xs opacity-80">{tab.description}</span>
				</button>
			{/each}
		</div>
	</section>

	{#if activeTab === 'history'}
		<div class="min-w-0 space-y-6" role="tabpanel" aria-label="Istoric">
			<section class="min-w-0 space-y-4">
				<div class="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
					<div class="min-w-0">
						<h2 class="text-xl font-extrabold font-sport text-foreground">Bilete castigate / pierdute</h2>
						<p class="text-sm text-muted-foreground">Agregare pe zile din endpoint-ul dashboard sau fallback din biletele recente.</p>
					</div>
					<Select bind:value={historyRange} options={historyRangeOptions} name="history-range" />
				</div>

				{#if ticketsLoading || outcomesLoading}
					<Card>
						<div class="grid grid-cols-3 gap-3 sm:grid-cols-6">
							{#each Array(6) as _}
								<Skeleton class="h-40 w-full" />
							{/each}
						</div>
					</Card>
				{:else if ticketsError}
					<Card>
						<div class="py-10 text-center text-sm text-destructive">{ticketsError}</div>
					</Card>
				{:else}
					<Card>
						<div class="min-w-0 space-y-4">
							{#if outcomesError}
								<div class="rounded-md border border-yellow-500/30 bg-yellow-500/10 p-3 text-xs text-yellow-300">
									{outcomesError}
								</div>
							{/if}

							{#if !hasOutcomeData}
								<div class="py-10 text-center text-muted-foreground">
									<p class="text-sm">Nu exista bilete in intervalul selectat.</p>
									<p class="mt-1 text-xs">Nu afisez date inventate; graficul se va popula cand exista bilete reale.</p>
								</div>
							{:else}
								<div class="grid min-w-0 grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6 xl:grid-cols-8">
									{#each ticketOutcomeBuckets as bucket (bucketKey(bucket))}
										<button
											class="min-w-0 rounded-lg border p-3 text-left transition hover:bg-secondary {selectedOutcomeBucketKey === bucketKey(bucket) ? 'border-primary bg-primary/10' : 'border-border bg-card'}"
											onclick={() => fetchSelectedOutcomeTickets(bucket)}
										>
											<div class="mb-3 flex min-w-0 items-center justify-between gap-2">
												<span class="truncate text-xs font-semibold text-foreground">{formatBucketLabel(bucket)}</span>
												<span class="shrink-0 font-mono text-xs text-muted-foreground">{bucket.won + bucket.lost}</span>
											</div>
											<div class="flex h-32 items-end justify-center gap-2 rounded-md bg-muted/30 p-2" aria-label={`Won ${bucket.won}, lost ${bucket.lost}`}>
												<div class="flex min-w-0 flex-col items-center gap-1">
													<div class="w-5 rounded-t bg-football-green" style={`height: ${barHeight(bucket.won)}`}></div>
													<span class="font-mono text-[10px] text-muted-foreground">{bucket.won}</span>
												</div>
												<div class="flex min-w-0 flex-col items-center gap-1">
													<div class="w-5 rounded-t bg-football-red" style={`height: ${barHeight(bucket.lost)}`}></div>
													<span class="font-mono text-[10px] text-muted-foreground">{bucket.lost}</span>
												</div>
											</div>
											<div class="mt-2 flex flex-wrap gap-1 text-[10px] text-muted-foreground">
												<span>Pending {bucket.pending}</span>
												<span>Void {bucket.void}</span>
											</div>
										</button>
									{/each}
								</div>
							{/if}
						</div>
					</Card>
				{/if}

				<Card>
					<div class="min-w-0 space-y-4">
						<div class="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
							<div>
								<h3 class="text-base font-bold text-foreground">Detalii bucket selectat</h3>
								<p class="text-xs text-muted-foreground">
									{selectedBucket ? `Bilete create pe ${formatDate(selectedBucket.bucket_start)}` : 'Alege o bara pentru a vedea biletele din bucket.'}
								</p>
							</div>
							{#if selectedBucket}
								<Badge variant="neutral">{selectedBucket.ticket_ids.length} bilete</Badge>
							{/if}
						</div>

						{#if selectedOutcomeTicketsLoading}
							<div class="space-y-2">
								<Skeleton class="h-24 w-full" />
								<Skeleton class="h-24 w-full" />
							</div>
						{:else if !selectedBucket}
							<div class="rounded-lg border border-dashed border-border py-8 text-center text-sm text-muted-foreground">Niciun bucket selectat.</div>
						{:else if selectedOutcomeTickets.length === 0}
							<div class="rounded-lg border border-dashed border-border py-8 text-center text-sm text-muted-foreground">Nu sunt bilete de afisat pentru bucket-ul selectat.</div>
						{:else}
							<div class="min-w-0 space-y-3">
								{#each selectedOutcomeTickets as ticket (ticket.id)}
									{@const chance = ticketChance(ticket)}
									{@const pnl = ticketPnl(ticket)}
									<div class="min-w-0 rounded-lg border border-border bg-card/60 p-4">
										<button
											class="flex w-full min-w-0 flex-col gap-3 text-left md:flex-row md:items-center md:justify-between"
											onclick={() => (expandedHistoryTicket = expandedHistoryTicket === ticket.id ? null : ticket.id)}
										>
											<div class="min-w-0 space-y-1">
												<div class="flex min-w-0 flex-wrap items-center gap-2">
													<span class="font-mono text-xs text-muted-foreground">#{ticket.reference ?? ticket.id}</span>
													<Badge variant={statusBadgeVariant(ticket.status)}>{ticket.status}</Badge>
													<Badge variant="neutral">{ticket.ticket_type}</Badge>
												</div>
												<p class="text-xs text-muted-foreground">Creat {formatDateTime(ticket.created_at)}</p>
											</div>
											<div class="grid min-w-0 grid-cols-2 gap-3 text-xs sm:grid-cols-5 md:w-auto">
												<span><b class="block text-muted-foreground">Odds</b>{formatNumber(ticket.total_odds)}</span>
												<span><b class="block text-muted-foreground">Stake</b>{formatCurrency(ticket.stake)}</span>
												<span><b class="block text-muted-foreground">Prob.</b>{formatPercent(chance)}</span>
												<span><b class="block text-muted-foreground">Return</b>{ticket.actual_return !== null ? formatCurrency(ticket.actual_return) : formatCurrency(ticket.potential_return)}</span>
												<span><b class="block text-muted-foreground">P&L</b>{pnl === null ? '--' : formatCurrency(pnl)}</span>
											</div>
										</button>

										{#if expandedHistoryTicket === ticket.id}
											<div class="mt-4 min-w-0 space-y-2 border-t border-border pt-3" transition:slide={{ duration: 160 }}>
												{#each ticket.legs as leg, index (`${ticket.id}-${leg.match_id}-${index}`)}
													{@const dashboardLeg = leg as DashboardLeg}
													<div class="grid min-w-0 gap-2 rounded-md bg-muted/30 p-3 text-sm md:grid-cols-[minmax(0,2fr)_repeat(5,minmax(0,1fr))]">
														<div class="min-w-0">
															<p class="truncate font-medium text-foreground">{leg.home_team ?? 'Home'} vs {leg.away_team ?? 'Away'}</p>
															<p class="text-xs text-muted-foreground">{leg.market} — {leg.selection}</p>
														</div>
														<span><b class="block text-xs text-muted-foreground">Model</b>{formatPercent(legProbability(dashboardLeg))}</span>
														<span><b class="block text-xs text-muted-foreground">Odds</b>{formatNumber(leg.odds)}</span>
														<span><b class="block text-xs text-muted-foreground">Scor</b>{finalScore(dashboardLeg)}</span>
														<span><b class="block text-xs text-muted-foreground">Rezultat</b>{dashboardLeg.result ?? leg.status}</span>
														<span><Badge variant={statusBadgeVariant(leg.status)}>{leg.status}</Badge></span>
													</div>
												{/each}
											</div>
										{/if}
									</div>
								{/each}
							</div>
						{/if}
					</div>
				</Card>
			</section>

			<section class="min-w-0 space-y-4">
				<div class="min-w-0">
					<h2 class="text-xl font-extrabold font-sport text-foreground">Verificare predictii</h2>
					<p class="text-sm text-muted-foreground">Date din API-ul existent <code class="text-xs">predictions.verify</code>, fara rescraping.</p>
				</div>

				{#if verificationLoading}
					<Skeleton class="h-64 w-full" />
				{:else if verificationError}
					<Card>
						<div class="py-12 text-center">
							<p class="text-sm font-medium text-foreground">Verificare indisponibila</p>
							<p class="mt-1 text-xs text-muted-foreground">{verificationError}</p>
						</div>
					</Card>
				{:else if verification}
					<Card>
						<div class="min-w-0 space-y-5">
							<div class="grid min-w-0 grid-cols-2 gap-3 md:grid-cols-4">
								<div class="rounded-lg bg-muted/30 p-3"><p class="text-xs text-muted-foreground">Verificate</p><p class="font-mono text-xl font-bold">{verification.checked_predictions}</p></div>
								<div class="rounded-lg bg-muted/30 p-3"><p class="text-xs text-muted-foreground">Rezolvate</p><p class="font-mono text-xl font-bold">{verification.resolved_predictions}</p></div>
								<div class="rounded-lg bg-muted/30 p-3"><p class="text-xs text-muted-foreground">Corecte</p><p class="font-mono text-xl font-bold text-football-green">{verification.correct_predictions}</p></div>
								<div class="rounded-lg bg-muted/30 p-3"><p class="text-xs text-muted-foreground">Acuratete</p><p class="font-mono text-xl font-bold">{verificationAccuracy === null ? '--' : `${verificationAccuracy.toFixed(1)}%`}</p></div>
							</div>

							{#if verificationItems.length === 0}
								<div class="rounded-lg border border-dashed border-border py-8 text-center text-sm text-muted-foreground">Nu exista predictii istorice verificate.</div>
							{:else}
								<div class="min-w-0 space-y-2">
									{#each verificationItems as item (item.prediction_id)}
										<div class="grid min-w-0 gap-2 rounded-lg border border-border p-3 text-sm md:grid-cols-[minmax(0,2fr)_repeat(7,minmax(0,1fr))]">
											<div class="min-w-0">
												<p class="truncate font-medium text-foreground">{item.home_team} vs {item.away_team}</p>
												<p class="text-xs text-muted-foreground">
													Run #{item.run_id} · Match #{item.match_id} · {item.model_type ?? 'model'}
												</p>
											</div>
											<span><b class="block text-xs text-muted-foreground">Liga</b>{item.league ?? '--'}</span>
											<span><b class="block text-xs text-muted-foreground">Kickoff</b>{formatDateTime(item.kickoff)}</span>
											<span><b class="block text-xs text-muted-foreground">Piata</b>{item.market}</span>
											<span><b class="block text-xs text-muted-foreground">Predictie</b>{item.predicted_selection ?? '--'}</span>
											<span><b class="block text-xs text-muted-foreground">Prob.</b>{formatPercent(item.model_probability)}</span>
											<span><b class="block text-xs text-muted-foreground">Odds</b>{formatNumber(item.market_odds)}</span>
											<span><b class="block text-xs text-muted-foreground">Actual</b>{item.actual_selection ?? '--'}</span>
											<span><b class="block text-xs text-muted-foreground">Scor</b>{item.home_score ?? '--'} - {item.away_score ?? '--'}</span>
											<span><Badge variant={verificationStatusVariant(item.status)}>{item.status}</Badge></span>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					</Card>
				{/if}
			</section>
		</div>
	{:else}
		<div class="min-w-0 space-y-6" role="tabpanel" aria-label="Viitor">
			<section class="min-w-0 space-y-4">
				<div class="flex min-w-0 flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
					<div class="min-w-0">
						<h2 class="text-xl font-extrabold font-sport text-foreground">Meciuri viitoare si predictii</h2>
						<p class="text-sm text-muted-foreground">Meciuri din dashboard upcoming, imbinate cu value bets/predictii cand exista.</p>
					</div>
					<div class="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-3 xl:w-[44rem]">
						<Select bind:value={futurePeriod} options={futurePeriodOptions} name="future-period" />
						<Select bind:value={selectedLeague} options={leagueOptions} name="future-league" />
						<Select bind:value={selectedMarket} options={marketOptions} name="future-market" />
					</div>
				</div>

				{#if upcomingLoading || valueBetsLoading}
					<div class="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-2">
						{#each Array(4) as _}
							<Skeleton class="h-56 w-full" />
						{/each}
					</div>
				{:else if upcomingError}
					<Card><div class="py-12 text-center text-sm text-destructive">{upcomingError}</div></Card>
				{:else if filteredUpcoming.length === 0}
					<Card>
						<div class="py-12 text-center text-muted-foreground">
							<p class="text-sm">Nu exista meciuri viitoare pentru filtrele curente.</p>
							<p class="mt-1 text-xs">Nu afisez meciuri sau predictii false.</p>
						</div>
					</Card>
				{:else}
					{#if valueBetsError}
						<div class="rounded-md border border-yellow-500/30 bg-yellow-500/10 p-3 text-xs text-yellow-300">{valueBetsError}</div>
					{/if}
					<div class="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-2">
						{#each filteredUpcoming as match (match.id)}
							{@const predictions = predictionForMatch(match)}
							<Card interactive>
								<div class="min-w-0 space-y-4">
									<div class="flex min-w-0 flex-wrap items-start justify-between gap-2">
										<div class="min-w-0">
											<Badge variant="info">{match.league}</Badge>
											<p class="mt-2 truncate text-base font-bold text-foreground">{match.home_team} vs {match.away_team}</p>
											<p class="text-xs text-muted-foreground">{formatDateTime(match.start_time)}</p>
										</div>
										<Badge variant={predictions.length > 0 ? 'success' : 'neutral'}>
											{predictions.length > 0 ? `${predictions.length} predictii` : 'fara predictii'}
										</Badge>
									</div>

									{#if predictions.length > 0}
										<div class="min-w-0 space-y-2">
											{#each predictions as prediction (prediction.id)}
												<div class="grid min-w-0 gap-2 rounded-md bg-muted/30 p-3 text-sm sm:grid-cols-5">
													<span class="min-w-0 sm:col-span-2"><b class="block text-xs text-muted-foreground">Piata / selectie</b>{prediction.market} · {prediction.selection}</span>
													<span><b class="block text-xs text-muted-foreground">Prob.</b>{formatPercent(prediction.model_prob)}</span>
													<span><b class="block text-xs text-muted-foreground">Odds</b>{formatNumber(prediction.odds)}</span>
													<span><b class="block text-xs text-muted-foreground">Job</b>{prediction.source ?? prediction.model_type}</span>
												</div>
											{/each}
										</div>
									{:else}
										<div class="rounded-md border border-dashed border-border p-3 text-sm text-muted-foreground">
											Meciul este disponibil din dashboard, dar nu are predictii generate in API-ul curent.
										</div>
									{/if}

									<div class="grid grid-cols-3 gap-2">
										<button class="rounded-md border border-border p-2 text-center hover:bg-secondary" onclick={() => addMatchToBetSlip(match, { key: 'home', label: 'Home', odds: match.home_odds })}>
											<p class="text-[10px] text-muted-foreground">1</p><p class="font-mono text-sm font-semibold text-football-green">{match.home_odds?.toFixed(2) ?? '--'}</p>
										</button>
										<button class="rounded-md border border-border p-2 text-center hover:bg-secondary" onclick={() => addMatchToBetSlip(match, { key: 'draw', label: 'Draw', odds: match.draw_odds })}>
											<p class="text-[10px] text-muted-foreground">X</p><p class="font-mono text-sm font-semibold text-football-blue">{match.draw_odds?.toFixed(2) ?? '--'}</p>
										</button>
										<button class="rounded-md border border-border p-2 text-center hover:bg-secondary" onclick={() => addMatchToBetSlip(match, { key: 'away', label: 'Away', odds: match.away_odds })}>
											<p class="text-[10px] text-muted-foreground">2</p><p class="font-mono text-sm font-semibold text-football-gold">{match.away_odds?.toFixed(2) ?? '--'}</p>
										</button>
									</div>
								</div>
							</Card>
						{/each}
					</div>
				{/if}
			</section>

			<section class="min-w-0 space-y-4">
				<div class="min-w-0">
					<h2 class="text-xl font-extrabold font-sport text-foreground">Bilete viitoare / active</h2>
					<p class="text-sm text-muted-foreground">Bilete nesolutionate din lista recenta dashboard, cu progres pe leg-uri.</p>
				</div>

				{#if futureTicketsLoading}
					<div class="space-y-3"><Skeleton class="h-28 w-full" /><Skeleton class="h-28 w-full" /></div>
				{:else if futureTickets.length === 0}
					<Card>
						<div class="py-12 text-center text-muted-foreground">
							<p class="text-sm">Nu exista bilete active in datele dashboard recente.</p>
							<p class="mt-1 text-xs">Cand sunt create bilete nesolutionate, apar aici fara a merge la /tickets.</p>
						</div>
					</Card>
				{:else}
					<div class="min-w-0 space-y-3">
						{#each futureTickets as ticket (ticket.id)}
							{@const chance = ticketChance(ticket)}
							<div class="min-w-0 rounded-lg border border-border bg-card p-4">
								<button
									class="flex w-full min-w-0 flex-col gap-3 text-left lg:flex-row lg:items-center lg:justify-between"
									onclick={() => (expandedFutureTicket = expandedFutureTicket === ticket.id ? null : ticket.id)}
								>
									<div class="min-w-0 space-y-1">
										<div class="flex min-w-0 flex-wrap items-center gap-2">
											<span class="font-mono text-xs text-muted-foreground">#{ticket.reference ?? ticket.id}</span>
											<Badge variant={statusBadgeVariant(ticket.status)}>{ticket.status}</Badge>
											<Badge variant="neutral">{settledLegs(ticket)} / {ticket.legs.length} leg-uri solutionate</Badge>
										</div>
										<p class="text-xs text-muted-foreground">Creat {formatDateTime(ticket.created_at)}</p>
									</div>
									<div class="grid min-w-0 grid-cols-2 gap-3 text-xs sm:grid-cols-4 lg:w-auto">
										<span><b class="block text-muted-foreground">Odds</b>{formatNumber(ticket.total_odds)}</span>
										<span><b class="block text-muted-foreground">Stake</b>{formatCurrency(ticket.stake)}</span>
										<span><b class="block text-muted-foreground">Prob.</b>{formatPercent(chance)}</span>
										<span><b class="block text-muted-foreground">Potential</b>{formatCurrency(ticket.potential_return)}</span>
									</div>
								</button>

								{#if expandedFutureTicket === ticket.id}
									<div class="mt-4 min-w-0 space-y-2 border-t border-border pt-3" transition:slide={{ duration: 160 }}>
										{#each ticket.legs as leg, index (`future-${ticket.id}-${leg.match_id}-${index}`)}
											{@const dashboardLeg = leg as DashboardLeg}
											<div class="grid min-w-0 gap-2 rounded-md bg-muted/30 p-3 text-sm md:grid-cols-[minmax(0,2fr)_repeat(4,minmax(0,1fr))]">
												<div class="min-w-0"><p class="truncate font-medium text-foreground">{leg.home_team ?? 'Home'} vs {leg.away_team ?? 'Away'}</p><p class="text-xs text-muted-foreground">{leg.market} — {leg.selection}</p></div>
												<span><b class="block text-xs text-muted-foreground">Model</b>{formatPercent(legProbability(dashboardLeg))}</span>
												<span><b class="block text-xs text-muted-foreground">Odds</b>{formatNumber(leg.odds)}</span>
												<span><b class="block text-xs text-muted-foreground">Scor final</b>{finalScore(dashboardLeg)}</span>
												<span><Badge variant={statusBadgeVariant(leg.status)}>{leg.status}</Badge></span>
											</div>
										{/each}
									</div>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			</section>
		</div>
	{/if}
</div>
