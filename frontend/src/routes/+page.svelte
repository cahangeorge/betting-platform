<script lang="ts">
	import { fade, slide } from 'svelte/transition';
	import Card from '$lib/components/ui/Card.svelte';
	import BetslipReviewCallout from '$lib/components/BetslipReviewCallout.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Skeleton from '$lib/components/ui/skeleton/skeleton.svelte';
	import { dashboardApi } from '$lib/api/dashboard';
	import { analyticsApi } from '$lib/api/analytics';
	import { betslip, createBetslipLeg } from '$lib/stores/betslip';
	import type {
		DashboardSummary,
		DashboardTicket,
		UpcomingMatch,
		JobLog,
		PnlPoint
	} from '$lib/types';

	// ── State ──────────────────────────────────────────
	let summary = $state<DashboardSummary | null>(null);
	let tickets = $state<DashboardTicket[]>([]);
	let upcoming = $state<UpcomingMatch[]>([]);
	let jobLogs = $state<JobLog[]>([]);
	let pnlData = $state<PnlPoint[]>([]);

	let loading = $state(true);
	let ticketsLoading = $state(true);
	let upcomingLoading = $state(true);
	let jobLogsLoading = $state(true);
	let pnlLoading = $state(true);

	let ticketDateFilter = $state('week');
	let pnlPeriod = $state('30d');
	let expandedTicket = $state<number | null>(null);
	let expandedJob = $state<number | null>(null);

	// ── Fetchers ───────────────────────────────────────
	async function fetchSummary() {
		try {
			summary = await dashboardApi.getSummary();
		} catch {
			summary = null;
		}
		loading = false;
	}

	async function fetchTickets() {
		ticketsLoading = true;
		try {
			const now = new Date();
			let date_from: string | undefined;
			if (ticketDateFilter === 'today') {
				date_from = now.toISOString().slice(0, 10);
			} else if (ticketDateFilter === 'week') {
				const weekAgo = new Date(now);
				weekAgo.setDate(weekAgo.getDate() - 7);
				date_from = weekAgo.toISOString().slice(0, 10);
			} else if (ticketDateFilter === 'month') {
				const monthAgo = new Date(now);
				monthAgo.setMonth(monthAgo.getMonth() - 1);
				date_from = monthAgo.toISOString().slice(0, 10);
			}
			tickets = await dashboardApi.getRecentTickets({ limit: 20, date_from });
		} catch {
			tickets = [];
		}
		ticketsLoading = false;
	}

	async function fetchUpcoming() {
		upcomingLoading = true;
		try {
			upcoming = await dashboardApi.getUpcoming(7);
		} catch {
			upcoming = [];
		}
		upcomingLoading = false;
	}

	async function fetchJobLogs() {
		jobLogsLoading = true;
		try {
			jobLogs = await dashboardApi.getJobLogs(15);
		} catch {
			jobLogs = [];
		}
		jobLogsLoading = false;
	}

	async function fetchPnl() {
		pnlLoading = true;
		try {
			pnlData = await analyticsApi.getPnl(pnlPeriod, 'day');
		} catch {
			pnlData = [];
		}
		pnlLoading = false;
	}

	// ── Derived ────────────────────────────────────────
	const pnlStats = $derived.by(() => {
		if (pnlData.length === 0) {
			return { totalPnl: 0, roi: 0, wins: 0, total: 0 };
		}
		const last = pnlData[pnlData.length - 1];
		const totalBets = pnlData.reduce((s, p) => s + p.bets_count, 0);
		const totalWins = pnlData.reduce((s, p) => s + p.wins, 0);
		const roi = totalBets > 0 ? ((last.cumulative_pnl / totalBets) * 100) : 0;
		return {
			totalPnl: last.cumulative_pnl,
			roi,
			wins: totalWins,
			total: totalBets
		};
	});

	const chartMax = $derived(pnlData.length > 0 ? Math.max(...pnlData.map((p) => p.cumulative_pnl)) : 0);
	const chartMin = $derived(pnlData.length > 0 ? Math.min(...pnlData.map((p) => p.cumulative_pnl)) : 0);
	const chartRange = $derived(chartMax - chartMin || 1);

	function chartPath(): string {
		if (pnlData.length === 0) return '';
		const w = 600;
		const h = 160;
		const pad = 10;
		const points = pnlData.map((p, i) => {
			const x = pad + (i / (pnlData.length - 1 || 1)) * (w - 2 * pad);
			const y = h - pad - ((p.cumulative_pnl - chartMin) / chartRange) * (h - 2 * pad);
			return `${x},${y}`;
		});
		return `M${points.join(' L')}`;
	}

	function chartAreaPath(): string {
		if (pnlData.length === 0) return '';
		const w = 600;
		const h = 160;
		const pad = 10;
		const points = pnlData.map((p, i) => {
			const x = pad + (i / (pnlData.length - 1 || 1)) * (w - 2 * pad);
			const y = h - pad - ((p.cumulative_pnl - chartMin) / chartRange) * (h - 2 * pad);
			return `${x},${y}`;
		});
		const first = `${pad},${h - pad}`;
		const last = `${pad + ((pnlData.length - 1) / (pnlData.length - 1 || 1)) * (w - 2 * pad)},${h - pad}`;
		return `M${first} L${points.join(' L')} L${last} Z`;
	}

	// ── Helpers ────────────────────────────────────────
	const ticketDateOptions = [
		{ value: 'today', label: 'Today' },
		{ value: 'week', label: 'This Week' },
		{ value: 'month', label: 'This Month' },
		{ value: 'all', label: 'All' }
	];

	const pnlPeriodOptions = [
		{ value: '7d', label: '7d' },
		{ value: '30d', label: '30d' },
		{ value: '90d', label: '90d' },
		{ value: '1y', label: '1y' }
	];

	function typeBadgeVariant(type: string): 'info' | 'warning' | 'premium' {
		if (type === 'single') return 'info';
		if (type === 'accumulator') return 'warning';
		return 'premium';
	}

	function statusBadgeVariant(status: string): 'success' | 'danger' | 'neutral' {
		if (status === 'won') return 'success';
		if (status === 'lost') return 'danger';
		return 'neutral';
	}

	function jobStatusVariant(status: string): 'success' | 'danger' | 'info' | 'warning' {
		if (status === 'completed') return 'success';
		if (status === 'failed') return 'danger';
		if (status === 'running') return 'info';
		return 'warning';
	}

	function formatCurrency(v: number): string {
		return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'EUR' }).format(v);
	}

	function formatDuration(secs: number | null | undefined): string {
		if (secs == null || isNaN(secs)) return '--';
		if (secs < 60) return `${Math.round(secs)}s`;
		const m = Math.floor(secs / 60);
		const s = Math.round(secs % 60);
		return `${m}m ${s}s`;
	}

	function formatDate(iso: string | null | undefined): string {
		if (!iso) return '--';
		const d = new Date(iso);
		if (isNaN(d.getTime())) return '--';
		return d.toLocaleDateString('en-GB', {
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}

	function formatDateTime(iso: string | null | undefined): string {
		if (!iso) return '--';
		const d = new Date(iso);
		if (isNaN(d.getTime())) return '--';
		return d.toLocaleString('en-GB', {
			day: 'numeric',
			month: 'short',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function formatTime(iso: string | null | undefined): string {
		if (!iso) return '--';
		const d = new Date(iso);
		if (isNaN(d.getTime())) return '--';
		return d.toLocaleTimeString('en-GB', {
			hour: '2-digit',
			minute: '2-digit'
		});
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

	// ── Lifecycle ──────────────────────────────────────
	let interval: ReturnType<typeof setInterval>;

	async function fetchAll() {
		await Promise.all([fetchSummary(), fetchTickets(), fetchUpcoming(), fetchJobLogs(), fetchPnl()]);
	}

	$effect(() => {
		fetchAll();
		interval = setInterval(fetchAll, 30000);
		return () => clearInterval(interval);
	});

	$effect(() => {
		void ticketDateFilter;
		fetchTickets();
	});

	$effect(() => {
		void pnlPeriod;
		fetchPnl();
	});
</script>

<div class="space-y-8" transition:fade={{ duration: 200 }}>
	<BetslipReviewCallout label="Dashboard picks are ready for ticket review." />

	<!-- Section A: Recent Tickets -->
	<section>
		<div class="flex items-center justify-between mb-4">
			<h2 class="text-xl font-extrabold font-sport text-foreground">Recent Tickets</h2>
			<div class="flex items-center gap-3">
				<Select
					bind:value={ticketDateFilter}
					options={ticketDateOptions}
				/>
				<a href="/data" class="text-sm text-primary hover:underline">View All</a>
			</div>
		</div>

		{#if ticketsLoading}
			<div class="flex gap-4 overflow-hidden">
				{#each Array(4) as _}
					<Skeleton class="h-44 w-72 flex-shrink-0" />
				{/each}
			</div>
		{:else if tickets.length === 0}
			<Card>
				<div class="py-12 text-center text-muted-foreground">
					<p class="text-sm">No tickets found for this period.</p>
					<p class="text-xs mt-1">Place a bet to see it appear here.</p>
				</div>
			</Card>
		{:else}
			<div class="flex gap-4 overflow-x-auto scroll-thin pb-2">
				{#each tickets as ticket (ticket.id)}
					<button
						class="flex-shrink-0 w-72 text-left"
						onclick={() => (expandedTicket = expandedTicket === ticket.id ? null : ticket.id)}
					>
						<Card
							variant={ticket.status === 'won' ? 'active' : ticket.status === 'lost' ? 'default' : 'data'}
							interactive
						>
							<div class="space-y-3">
								<div class="flex items-center justify-between">
									<span class="text-xs font-mono text-muted-foreground">#{ticket.id}</span>
									<div class="flex gap-1.5">
										<Badge variant={typeBadgeVariant(ticket.ticket_type)}>{ticket.ticket_type}</Badge>
										<Badge variant={statusBadgeVariant(ticket.status)}>{ticket.status}</Badge>
									</div>
								</div>
								<div class="flex items-end justify-between">
									<div>
										<p class="text-xs text-muted-foreground">Stake</p>
										<p class="text-sm font-mono font-semibold">{formatCurrency(ticket.stake)}</p>
									</div>
									<div class="text-right">
										<p class="text-xs text-muted-foreground">Odds</p>
										<p class="text-sm font-mono font-semibold">{ticket.total_odds.toFixed(2)}</p>
									</div>
									<div class="text-right">
										<p class="text-xs text-muted-foreground">Return</p>
										<p class="text-sm font-mono font-semibold">
											{ticket.actual_return !== null
												? formatCurrency(ticket.actual_return)
												: formatCurrency(ticket.potential_return)}
										</p>
									</div>
								</div>
								<p class="text-[10px] text-muted-foreground">{formatDate(ticket.created_at)}</p>
							</div>
						</Card>
					</button>
				{/each}
			</div>

			<!-- Expanded ticket detail -->
			{#if expandedTicket !== null}
				{@const ticket = tickets.find((t) => t.id === expandedTicket)}
				{#if ticket}
					<div transition:slide={{ duration: 200 }}>
						<Card class="mt-3">
							<div class="space-y-2">
								<h4 class="text-sm font-semibold text-foreground mb-3">Ticket Legs</h4>
								{#each ticket.legs as leg}
									<div class="flex items-center justify-between py-2 border-b border-border last:border-0">
										<div class="flex-1">
											<p class="text-sm font-medium">
												{leg.home_team} vs {leg.away_team}
											</p>
											<p class="text-xs text-muted-foreground">
												{leg.market} — {leg.selection}
											</p>
										</div>
										{#if leg.home_score !== null && leg.away_score !== null}
											<span class="text-sm font-mono font-semibold mx-3">
												{leg.home_score} - {leg.away_score}
											</span>
										{/if}
										<div class="flex items-center gap-2">
											<span class="text-sm font-mono">{leg.odds.toFixed(2)}</span>
											<Badge
												variant={
													leg.status === 'won'
														? 'success'
														: leg.status === 'lost'
															? 'danger'
															: 'neutral'
												}
											>
												{leg.status}
											</Badge>
										</div>
									</div>
								{/each}
							</div>
						</Card>
					</div>
				{/if}
			{/if}
		{/if}
	</section>

	<!-- Section B: Upcoming Matches -->
	<section>
		<div class="flex items-center justify-between mb-4">
			<h2 class="text-xl font-extrabold font-sport text-foreground">Upcoming Matches</h2>
			<span class="text-xs text-muted-foreground">Next 7 days</span>
		</div>

		{#if upcomingLoading}
			<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
				{#each Array(4) as _}
					<Skeleton class="h-40 w-full" />
				{/each}
			</div>
		{:else if upcoming.length === 0}
			<Card>
				<div class="py-12 text-center text-muted-foreground">
					<p class="text-sm">No upcoming matches found.</p>
				</div>
			</Card>
		{:else}
			<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
				{#each upcoming as match (match.id)}
					<Card interactive>
						<div class="space-y-3">
							<div class="flex items-center justify-between">
								<Badge variant="info">{match.league}</Badge>
								<span class="text-xs font-mono text-muted-foreground">
									{formatDate(match.start_time)} {formatTime(match.start_time)}
								</span>
							</div>
							<div class="flex items-center justify-between">
								<span class="text-sm font-medium text-foreground">{match.home_team}</span>
								<span class="text-xs text-muted-foreground">vs</span>
								<span class="text-sm font-medium text-foreground">{match.away_team}</span>
							</div>
							<div class="grid grid-cols-3 gap-2 py-1">
								<button class="text-center" onclick={() => addMatchToBetSlip(match, { key: 'home', label: 'Home', odds: match.home_odds })}>
									<p class="text-[10px] text-muted-foreground">1</p>
									<p class="text-sm font-mono font-semibold text-football-green">
										{match.home_odds?.toFixed(2) ?? '--'}
									</p>
								</button>
								<button class="text-center" onclick={() => addMatchToBetSlip(match, { key: 'draw', label: 'Draw', odds: match.draw_odds })}>
									<p class="text-[10px] text-muted-foreground">X</p>
									<p class="text-sm font-mono font-semibold text-football-blue">
										{match.draw_odds?.toFixed(2) ?? '--'}
									</p>
								</button>
								<button class="text-center" onclick={() => addMatchToBetSlip(match, { key: 'away', label: 'Away', odds: match.away_odds })}>
									<p class="text-[10px] text-muted-foreground">2</p>
									<p class="text-sm font-mono font-semibold text-football-gold">
										{match.away_odds?.toFixed(2) ?? '--'}
									</p>
								</button>
							</div>
							<div class="flex gap-2">
								<a href={`/predict?match=${match.id}`} class="flex-1">
									<Button variant="secondary" size="sm" fullWidth>Predict</Button>
								</a>
								<a href="/tickets" class="flex-1">
									<Button variant="glow" size="sm" fullWidth>Review Slip</Button>
								</a>
							</div>
						</div>
					</Card>
				{/each}
			</div>
		{/if}
	</section>

	<!-- Section C: Account P&L -->
	<section>
		<div class="flex items-center justify-between mb-4">
			<h2 class="text-xl font-extrabold font-sport text-foreground">Account P&L</h2>
			<div class="flex gap-1">
				{#each pnlPeriodOptions as opt}
					<Button
						variant={pnlPeriod === opt.value ? 'primary' : 'ghost'}
						size="sm"
						onclick={() => (pnlPeriod = opt.value)}
					>
						{opt.label}
					</Button>
				{/each}
			</div>
		</div>

		{#if pnlLoading}
			<Skeleton class="h-52 w-full mb-4" />
			<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
				{#each Array(4) as _}
					<Skeleton class="h-24 w-full" />
				{/each}
			</div>
		{:else}
			<!-- SVG Area Chart -->
			<Card class="mb-4">
				{#if pnlData.length === 0}
					<div class="py-12 text-center text-muted-foreground text-sm">No P&L data for this period.</div>
				{:else}
					<div class="overflow-hidden">
						<svg viewBox="0 0 600 160" class="w-full h-40" preserveAspectRatio="none">
							<!-- Area fill -->
							<path d={chartAreaPath()} class="fill-football-green/10" />
							<!-- Line -->
							<path
								d={chartPath()}
								fill="none"
								class="stroke-football-green"
								stroke-width="2"
							/>
							<!-- Zero line -->
							{#if chartMin < 0 && chartMax > 0}
								{@const zeroY =
									10 - ((0 - chartMin) / chartRange) * 140}
								<line
									x1="10"
									y1={zeroY}
									x2="590"
									y2={zeroY}
									class="stroke-border"
									stroke-dasharray="4 4"
									stroke-width="0.5"
								/>
							{/if}
						</svg>
					</div>
					<div class="flex justify-between text-[10px] text-muted-foreground px-2 mt-1">
						<span>{pnlData[0]?.date}</span>
						<span>{pnlData[pnlData.length - 1]?.date}</span>
					</div>
				{/if}
			</Card>

			<!-- Stat Cards -->
			<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
				{#if summary}
					<Card variant="active">
						<div class="py-3 text-center">
							<p class="text-xs text-muted-foreground mb-1">Balance</p>
							<p class="text-xl font-mono font-bold text-foreground">
								{formatCurrency(summary.active_bankroll)}
							</p>
						</div>
					</Card>
				{:else}
					<Skeleton class="h-24" />
				{/if}
				<Card>
					<div class="py-3 text-center">
						<p class="text-xs text-muted-foreground mb-1">Total P&L</p>
						<p
							class="text-xl font-mono font-bold {pnlStats.totalPnl >= 0
								? 'text-football-green'
								: 'text-football-red'}"
						>
							{pnlStats.totalPnl >= 0 ? '+' : ''}{formatCurrency(pnlStats.totalPnl)}
						</p>
					</div>
				</Card>
				<Card>
					<div class="py-3 text-center">
						<p class="text-xs text-muted-foreground mb-1">ROI</p>
						<p
							class="text-xl font-mono font-bold {pnlStats.roi >= 0
								? 'text-football-green'
								: 'text-football-red'}"
						>
							{pnlStats.roi >= 0 ? '+' : ''}{pnlStats.roi.toFixed(1)}%
						</p>
					</div>
				</Card>
				{#if summary}
					<Card>
						<div class="py-3 text-center">
							<p class="text-xs text-muted-foreground mb-1">Pending Bets</p>
							<p class="text-xl font-mono font-bold text-football-gold">
								{summary.pending_bets}
							</p>
						</div>
					</Card>
				{:else}
					<Skeleton class="h-24" />
				{/if}
			</div>
		{/if}
	</section>

	<!-- Section D: Job Logs -->
	<section>
		<div class="flex items-center justify-between mb-4">
			<h2 class="text-xl font-extrabold font-sport text-foreground">Job Logs</h2>
		</div>

		{#if jobLogsLoading}
			<div class="space-y-2">
				{#each Array(5) as _}
					<Skeleton class="h-14 w-full" />
				{/each}
			</div>
		{:else if jobLogs.length === 0}
			<Card>
				<div class="py-12 text-center text-muted-foreground">
					<p class="text-sm">No job logs found.</p>
				</div>
			</Card>
		{:else}
			<div class="space-y-2">
				{#each jobLogs as job (job.id)}
					<button
						class="w-full text-left"
						onclick={() => (expandedJob = expandedJob === job.id ? null : job.id)}
					>
						<Card interactive>
							<div class="flex items-center justify-between py-1">
								<div class="flex items-center gap-3">
									<span class="text-sm font-medium text-foreground">{job.job_type}</span>
									<Badge variant="neutral">{job.job_type}</Badge>
									<Badge variant={jobStatusVariant(job.status)}>{job.status}</Badge>
								</div>
								<div class="flex items-center gap-4 text-xs text-muted-foreground">
									<span class="font-mono">{formatDuration(job.completed_at && job.started_at ? (new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()) / 1000 : null)}</span>
									<span>{formatDateTime(job.created_at)}</span>
									<svg
										class="w-4 h-4 transition-transform {expandedJob === job.id ? 'rotate-180' : ''}"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										stroke-width="2"
									>
										<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
									</svg>
								</div>
							</div>
						</Card>
					</button>
					{#if expandedJob === job.id}
						<div transition:slide={{ duration: 200 }}>
							<Card class="ml-4 border-l-2 border-l-border">
								<div class="space-y-2 text-sm">
									<div class="grid grid-cols-2 gap-2">
										<div>
											<span class="text-muted-foreground">Type:</span>
											<span class="ml-2 font-mono">{job.job_type}</span>
										</div>
										<div>
											<span class="text-muted-foreground">Progress:</span>
											<span class="ml-2 font-mono">{job.job_type}</span>
										</div>
										<div>
											<span class="text-muted-foreground">Started:</span>
											<span class="ml-2 font-mono">{formatDateTime(job.created_at)}</span>
										</div>
										{#if job.completed_at}
											<div>
												<span class="text-muted-foreground">Completed:</span>
												<span class="ml-2 font-mono">{formatDateTime(job.completed_at)}</span>
											</div>
										{/if}
									</div>
									{#if job.error}
										<div class="mt-2 p-3 bg-destructive/10 border border-destructive/20 text-destructive text-xs font-mono">
											{job.error}
										</div>
									{/if}
								</div>
							</Card>
						</div>
					{/if}
				{/each}
			</div>
		{/if}
	</section>
</div>
