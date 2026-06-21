<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Skeleton from '$lib/components/ui/skeleton/skeleton.svelte';
	import DialogRoot from '$lib/components/ui/dialog/dialog-root.svelte';
	import DialogContent from '$lib/components/ui/dialog/dialog-content.svelte';
	import DialogHeader from '$lib/components/ui/dialog/dialog-header.svelte';
	import DialogFooter from '$lib/components/ui/dialog/dialog-footer.svelte';
	import DialogTitle from '$lib/components/ui/dialog/dialog-title.svelte';
	import { matchesApi } from '$lib/api/matches';
	import { ticketsApi } from '$lib/api/tickets';
	import { predictionsApi } from '$lib/api/predictions';
	import type { Match, Ticket, TicketLeg, PredictionRun } from '$lib/types';
	import type { BackendLoadStatus } from '$lib/types/backend';
	import Select from '$lib/components/ui/Select.svelte';

	let { data }: import('./$types').PageProps = $props();

	// Safe access with fallbacks — server load may not have all fields yet
	const serverData = $derived(data ?? {});
	const backendStatus = $derived(
		((serverData as { backendStatus?: BackendLoadStatus }).backendStatus as BackendLoadStatus | undefined) ?? {
			state: 'ready',
			message: null,
			failedEndpoints: []
		}
	);
	let matches = $state<Match[]>([]);
	let tickets = $state<Ticket[]>([]);
	let predictionRuns = $state<PredictionRun[]>([]);
	let predictionMatchMap = $state<Record<number, Match>>({});

	$effect(() => {
		matches = (serverData as any).matches ?? [];
		tickets = (serverData as any).tickets ?? [];
		predictionRuns = (serverData as any).predictionRuns ?? [];
	});

	// ── State ──────────────────────────────────────────
	let activeTab = $state('matches');
	let searchQuery = $state('');
	let dateFrom = $state('');
	let dateTo = $state('');
	let page = $state(1);
	let perPage = $state(10);

	let matchesLoading = $state(false);
	let ticketsLoading = $state(false);
	let predictionsLoading = $state(false);

	let dialogOpen = $state(false);
	let selectedRow = $state<Record<string, unknown> | null>(null);
	let selectedTabLabel = $state('');

	const tabs = [
		{ id: 'matches', label: 'Matches' },
		{ id: 'predictions', label: 'Predictions' },
		{ id: 'tickets', label: 'Tickets' }
	];

	const perPageOptions = [
		{ value: '10', label: '10' },
		{ value: '25', label: '25' },
		{ value: '50', label: '50' }
	];

	// ── Fetchers ───────────────────────────────────────
	async function fetchMatches() {
		matchesLoading = true;
		try {
			const filter: Record<string, string> = {};
			if (dateFrom) filter.date_from = dateFrom;
			if (dateTo) filter.date_to = dateTo;
			matches = await matchesApi.getMatches(
				Object.keys(filter).length > 0
					? (filter as { date_from?: string; date_to?: string; status?: 'scheduled' | 'live' | 'finished' | 'postponed' | 'cancelled' })
					: undefined
			);
		} catch {
			matches = [];
		}
		matchesLoading = false;
	}

	async function fetchTickets() {
		ticketsLoading = true;
		try {
			tickets = await ticketsApi.getTickets();
		} catch {
			tickets = [];
		}
		ticketsLoading = false;
	}

	async function fetchPredictions() {
		predictionsLoading = true;
		try {
			const runs = await predictionsApi.getRuns();
			predictionRuns = await Promise.all(
				runs.map(async (run) => {
					try {
						return await predictionsApi.getRun(run.id);
					} catch {
						return run;
					}
				})
			);
			const matchIds = Array.from(
				new Set(
					predictionRuns.flatMap((run) =>
						(run.model_predictions ?? []).map((prediction) => prediction.match_id)
					)
				)
			);
			const matchEntries = await Promise.all(
				matchIds.map(async (id) => {
					try {
						return [id, await matchesApi.getMatch(id)] as const;
					} catch {
						return null;
					}
				})
			);
			predictionMatchMap = Object.fromEntries(
				matchEntries.filter((entry): entry is readonly [number, Match] => entry !== null)
			);
		} catch {
			predictionRuns = [];
			predictionMatchMap = {};
		}
		predictionsLoading = false;
	}

	function fetchCurrent() {
		if (activeTab === 'matches') fetchMatches();
		else if (activeTab === 'tickets') fetchTickets();
		else fetchPredictions();
	}

	// ── Derived ────────────────────────────────────────
	const searchLower = $derived(searchQuery.toLowerCase());

	const filteredMatches = $derived(
		matches.filter((m) => {
			if (searchQuery) {
				const hay = `${m.home_team} ${m.away_team} ${m.league}`.toLowerCase();
				if (!hay.includes(searchLower)) return false;
			}
			return true;
		})
	);

	const filteredTickets = $derived(
		tickets.filter((t) => {
			if (searchQuery) {
				const hay = `${t.reference} ${ticketTypeLabel(t)} ${t.status} ${ticketLegsLabel(t.legs)}`.toLowerCase();
				if (!hay.includes(searchLower)) return false;
			}
			return true;
		})
	);

	const predictionRows = $derived.by(() => {
		const rows: {
			id: number;
			prediction_id?: number;
			match_id?: number;
			date: string;
			match: string;
			model: string;
			market?: string;
			selection?: string;
			status: string;
			probability?: number;
			confidence?: number;
			reliability?: string;
			ticket_eligible?: string;
			block_reasons?: string;
			results: PredictionRun['results'];
			model_prediction?: NonNullable<PredictionRun['model_predictions']>[number];
			error: string | null;
		}[] = [];
		for (const run of predictionRuns) {
			if (run.model_predictions && run.model_predictions.length > 0) {
				for (const prediction of run.model_predictions) {
					const match =
						predictionMatchMap[prediction.match_id] ??
						matches.find((m) => m.id === prediction.match_id);
					const matchKey = match
						? `${match.home_team} vs ${match.away_team}`
						: `Match #${prediction.match_id}`;
					if (searchQuery && !matchKey.toLowerCase().includes(searchLower)) continue;
					const drawProb = prediction.draw_prob ?? 0;
					const probability = Math.max(prediction.home_prob, drawProb, prediction.away_prob);
					const selection =
						probability === prediction.home_prob
							? 'home'
							: probability === drawProb
								? 'draw'
								: 'away';
					rows.push({
						id: run.id,
						prediction_id: prediction.id,
						match_id: prediction.match_id,
						date: prediction.created_at || run.created_at,
						match: matchKey,
						model: prediction.model_type || run.model_type,
						market: prediction.market,
						selection,
						status: run.status,
						probability,
						confidence: probability,
						reliability: prediction.quality_report?.reliability?.label ?? 'legacy/no-report',
						ticket_eligible:
							prediction.quality_report?.reliability?.is_ticket_eligible === undefined
								? 'unknown'
								: prediction.quality_report.reliability.is_ticket_eligible
									? 'yes'
									: 'no',
						block_reasons:
							prediction.quality_report?.reliability?.block_reasons?.join(', ') ?? '',
						results: null,
						model_prediction: prediction,
						error: null
					});
				}
			} else if (run.results && run.results.length > 0) {
				for (const r of run.results) {
					const matchKey = `${r.home_team} vs ${r.away_team}`;
					if (searchQuery && !matchKey.toLowerCase().includes(searchLower)) continue;
					rows.push({
						id: run.id,
						date: run.created_at,
						match: matchKey,
						model: run.model_type,
						status: run.status,
						results: [r],
						error: null
					});
				}
			} else {
				const matchCount = run.matches_count ?? run.matches?.length ?? 0;
				const matchKey = `Run #${run.id} (${matchCount} matches)`;
				if (searchQuery && !matchKey.toLowerCase().includes(searchLower)) continue;
				rows.push({
					id: run.id,
					date: run.created_at,
					match: matchKey,
					model: run.model_type,
					status: run.status,
					results: null,
					error: run.error
				});
			}
		}
		return rows;
	});

	const filteredPredictions = $derived(predictionRows);

	const currentRows = $derived.by(() => {
		const source =
			activeTab === 'matches'
				? filteredMatches
				: activeTab === 'tickets'
					? filteredTickets
					: filteredPredictions;
		const start = (page - 1) * perPage;
		return source.slice(start, start + perPage);
	});

	const totalPages = $derived.by(() => {
		const total =
			activeTab === 'matches'
				? filteredMatches.length
				: activeTab === 'tickets'
					? filteredTickets.length
					: filteredPredictions.length;
		return Math.max(1, Math.ceil(total / perPage));
	});

	const currentColumns = $derived.by(() => {
		if (activeTab === 'matches') {
			return [
				{ key: 'date', label: 'Date' },
				{ key: 'league', label: 'League' },
				{ key: 'home_team', label: 'Home Team' },
				{ key: 'away_team', label: 'Away Team' },
				{ key: 'score', label: 'Score' },
				{ key: 'status', label: 'Status' }
			];
		}
		if (activeTab === 'tickets') {
			return [
				{ key: 'date', label: 'Date' },
				{ key: 'reference', label: 'Reference' },
				{ key: 'type', label: 'Type' },
				{ key: 'status', label: 'Status' },
				{ key: 'legs_count', label: 'Legs' },
				{ key: 'stake', label: 'Stake' },
				{ key: 'odds', label: 'Odds' },
				{ key: 'return', label: 'Return' },
				{ key: 'pnl', label: 'P&L' }
			];
		}
		return [
			{ key: 'date', label: 'Date' },
			{ key: 'match', label: 'Match' },
			{ key: 'model', label: 'Model' },
			{ key: 'market', label: 'Market' },
			{ key: 'selection', label: 'Pick' },
			{ key: 'status', label: 'Status' },
			{ key: 'reliability', label: 'Reliability' },
			{ key: 'ticket_eligible', label: 'Ticket?' },
			{ key: 'probability', label: 'Probability %' },
			{ key: 'confidence', label: 'Confidence %' }
		];
	});

	const currentRowsFormatted = $derived.by(() => {
		return currentRows.map((row) => {
			if (activeTab === 'matches') {
				const m = row as unknown as Match;
				return {
					...m,
					date: formatDate(m.start_time),
					score:
						m.home_score !== null && m.away_score !== null
							? `${m.home_score} - ${m.away_score}`
							: '--'
				};
			}
			if (activeTab === 'tickets') {
				const t = row as unknown as Ticket;
				const pnl =
					t.actual_return !== null
						? t.actual_return - t.stake
						: t.status === 'won'
							? t.potential_return - t.stake
							: t.status === 'lost'
								? -t.stake
								: null;
				return {
					...t,
					date: formatDate(t.created_at),
					type: ticketTypeLabel(t),
					legs_count: t.legs.length,
					stake: formatCurrency(t.stake),
					odds: t.total_odds.toFixed(2),
					return:
						t.actual_return !== null
							? formatCurrency(t.actual_return)
							: formatCurrency(t.potential_return),
					pnl: pnl !== null ? formatCurrency(pnl) : '--'
				};
			}
			const p = row as (typeof filteredPredictions)[0];
			const firstResult = p.results?.[0];
			return {
				...p,
				date: formatDate(p.date),
				probability: p.probability !== undefined
					? `${(p.probability * 100).toFixed(1)}`
					: firstResult
					? `${((firstResult.home_prob + firstResult.draw_prob + firstResult.away_prob) / 3 * 100).toFixed(1)}`
					: '--',
				confidence: p.confidence !== undefined
					? `${(p.confidence * 100).toFixed(1)}`
					: firstResult ? `${(firstResult.confidence * 100).toFixed(1)}` : '--'
			};
		});
	});

	// ── Helpers ────────────────────────────────────────
	function formatCurrency(v: number): string {
		return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'EUR' }).format(v);
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleDateString('en-GB', {
			day: 'numeric',
			month: 'short',
			year: 'numeric'
		});
	}

	function ticketTypeLabel(ticket: Pick<Ticket, 'type' | 'ticket_type'>): string {
		return ticket.type ?? ticket.ticket_type ?? '--';
	}

	function ticketLegMatchLabel(leg: unknown): string {
		const ticketLeg = leg as Partial<TicketLeg> & {
			home_team?: string | null;
			away_team?: string | null;
		};
		const homeTeam = ticketLeg.match?.home_team ?? ticketLeg.home_team;
		const awayTeam = ticketLeg.match?.away_team ?? ticketLeg.away_team;

		if (homeTeam && awayTeam) return `${homeTeam} vs ${awayTeam}`;
		if (ticketLeg.match_id) return `Match #${ticketLeg.match_id}`;
		return 'Match unavailable';
	}

	function ticketLegMetaLabel(leg: unknown): string {
		const ticketLeg = leg as Partial<TicketLeg> & { bookmaker?: string | null };
		return [ticketLeg.market, ticketLeg.selection, ticketLeg.bookmaker].filter(Boolean).join(' · ');
	}

	function ticketLegOddsLabel(leg: unknown): string {
		const ticketLeg = leg as Partial<TicketLeg>;
		return typeof ticketLeg.odds === 'number' ? ticketLeg.odds.toFixed(2) : '--';
	}

	function ticketLegsLabel(legs: TicketLeg[] = []): string {
		return legs.map(ticketLegMatchLabel).join(' ');
	}

	function statusBadgeVariant(status: string): 'success' | 'danger' | 'info' | 'neutral' {
		const s = status.toLowerCase();
		if (s === 'won' || s === 'completed' || s === 'finished') return 'success';
		if (s === 'lost' || s === 'failed' || s === 'cancelled') return 'danger';
		if (s === 'live' || s === 'running' || s === 'open') return 'info';
		return 'neutral';
	}

	function reliabilityBadgeVariant(status: string): 'success' | 'warning' | 'danger' | 'neutral' {
		const s = status.toLowerCase();
		if (s === 'reliable') return 'success';
		if (s === 'moderate') return 'warning';
		if (s === 'unreliable') return 'danger';
		return 'neutral';
	}

	function openRowDetail(row: Record<string, unknown>) {
		selectedRow = row;
		selectedTabLabel = tabs.find((t) => t.id === activeTab)?.label || '';
		dialogOpen = true;
	}

	function exportCsv() {
		const headers = currentColumns.map((c) => c.label);
		const data = currentRowsFormatted;
		const csvRows = [headers.join(',')];
		for (const row of data) {
			const values = currentColumns.map((c) => {
				const val = String((row as Record<string, unknown>)[c.key] ?? '');
				return `"${val.replace(/"/g, '""')}"`;
			});
			csvRows.push(values.join(','));
		}
		const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `${activeTab}-export.csv`;
		a.click();
		URL.revokeObjectURL(url);
	}

	function resetPagination() {
		page = 1;
	}

	// ── Lifecycle ──────────────────────────────────────
	onMount(() => {
		if (matches.length === 0) fetchMatches();
		if (tickets.length === 0) fetchTickets();
		fetchPredictions();
	});

	$effect(() => {
		void activeTab;
		resetPagination();
	});

	$effect(() => {
		void searchQuery;
		resetPagination();
	});
</script>

<div class="space-y-6" transition:fade={{ duration: 200 }}>
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-extrabold font-sport text-foreground">Data Hub</h1>
			<p class="mt-1 text-muted-foreground">Browse matches, predictions, and tickets</p>
		</div>
		<Button variant="secondary" size="sm" onclick={exportCsv}>
			<svg class="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
			</svg>
			Export CSV
		</Button>
	</div>

	{#if backendStatus.state === 'degraded' && backendStatus.message}
		<Card>
			<div class="border-l-4 border-yellow-500 bg-yellow-500/10 p-4 text-sm">
				<span class="font-medium">Partial backend data.</span> {backendStatus.message}
			</div>
		</Card>
	{/if}

	<!-- Filters -->
	<div class="flex items-end gap-3">
		<div class="flex-1 max-w-xs">
			<Input
				bind:value={searchQuery}
				placeholder="Search..."
				class="h-9"
			/>
		</div>
		<div>
			<label for="data-filter-from" class="text-xs text-muted-foreground block mb-1">From</label>
			<input
				id="data-filter-from"
				type="date"
				bind:value={dateFrom}
				class="h-9 px-3 border border-border bg-background text-foreground text-sm"
			/>
		</div>
		<div>
			<label for="data-filter-to" class="text-xs text-muted-foreground block mb-1">To</label>
			<input
				id="data-filter-to"
				type="date"
				bind:value={dateTo}
				class="h-9 px-3 border border-border bg-background text-foreground text-sm"
			/>
		</div>
		<Button variant="secondary" size="sm" onclick={() => { searchQuery = ''; dateFrom = ''; dateTo = ''; fetchCurrent(); }}>
			Clear
		</Button>
	</div>

	<Tabs bind:activeTab {tabs}>
		<!-- Data Table -->
		<div class="mt-4">
				{#if (activeTab === 'matches' && matchesLoading) || (activeTab === 'tickets' && ticketsLoading) || (activeTab === 'predictions' && predictionsLoading)}
					<div class="space-y-2">
						{#each Array.from({ length: 5 }, (_, index) => index) as skeletonIndex (skeletonIndex)}
							<Skeleton class="h-12 w-full" />
						{/each}
					</div>
			{:else if currentRowsFormatted.length === 0}
				<Card>
					<div class="py-16 text-center text-muted-foreground">
						<p class="text-sm">No {activeTab} found.</p>
					</div>
				</Card>
			{:else}
				<div class="border border-border overflow-x-auto">
					<table class="w-full text-sm">
						<thead>
							<tr class="border-b border-border bg-muted/50">
								{#each currentColumns as col (col.key)}
									<th class="px-3 py-2.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
										{col.label}
									</th>
								{/each}
							</tr>
						</thead>
						<tbody>
								{#each currentRowsFormatted as row, i ((((row as Record<string, unknown>).prediction_id as string | number | undefined) ?? row.id ?? `${activeTab}-${page}-${i}`) as string | number)}
									<tr
										class="border-b border-border last:border-0 hover:bg-muted/30 transition-colors cursor-pointer"
										onclick={() => openRowDetail(row)}
								>
									{#each currentColumns as col (col.key)}
										{@const cellValue = (row as Record<string, unknown>)[col.key]}
										<td class="px-3 py-2.5 font-mono text-sm">
											{#if col.key === 'status'}
												<Badge variant={statusBadgeVariant(String(row[col.key] ?? ''))}>
													{row[col.key]}
												</Badge>
											{:else if col.key === 'reliability'}
												<Badge variant={reliabilityBadgeVariant(String(cellValue ?? ''))}>
													{cellValue}
												</Badge>
											{:else if col.key === 'ticket_eligible'}
												<Badge variant={String(cellValue ?? '') === 'yes' ? 'success' : 'neutral'}>
													{cellValue}
												</Badge>
											{:else if col.key === 'league'}
												<Badge variant="info">{row[col.key as keyof typeof row]}</Badge>
											{:else}
												{row[col.key as keyof typeof row] ?? '--'}
											{/if}
										</td>
									{/each}
								</tr>
							{/each}
						</tbody>
					</table>
				</div>

				<!-- Pagination -->
				<div class="flex items-center justify-between mt-4">
					<div class="flex items-center gap-2">
						<span class="text-xs text-muted-foreground">Rows per page:</span>
						<Select
							value={String(perPage)}
							options={perPageOptions}
							onchange={(e: Event) => {
								perPage = Number((e.target as HTMLSelectElement).value);
								resetPagination();
							}}
						/>
					</div>
					<div class="flex items-center gap-2">
						<span class="text-xs text-muted-foreground">
							Page {page} of {totalPages}
						</span>
						<Button
							variant="secondary"
							size="sm"
							disabled={page <= 1}
							onclick={() => (page = Math.max(1, page - 1))}
						>
							Prev
						</Button>
						<Button
							variant="secondary"
							size="sm"
							disabled={page >= totalPages}
							onclick={() => (page = Math.min(totalPages, page + 1))}
						>
							Next
						</Button>
					</div>
				</div>
			{/if}
		</div>
	</Tabs>
</div>

<!-- Detail Dialog -->
<DialogRoot bind:open={dialogOpen}>
	<DialogContent class="max-w-2xl">
		<DialogHeader>
			<DialogTitle>{selectedTabLabel} Detail</DialogTitle>
		</DialogHeader>
		{#if selectedRow}
			<div class="space-y-3 max-h-[60vh] overflow-y-auto">
					{#each Object.entries(selectedRow) as [key, value] (key)}
						{#if key !== 'legs' && key !== 'results' && key !== 'odds' && key !== 'parameters' && key !== 'model_prediction'}
							<div class="flex justify-between py-1.5 border-b border-border last:border-0">
								<span class="text-xs text-muted-foreground uppercase tracking-wider">{key.replace(/_/g, ' ')}</span>
							<span class="text-sm font-mono text-foreground text-right max-w-[60%] break-words">
								{value === null || value === undefined ? '--' : String(value)}
							</span>
						</div>
					{/if}
				{/each}

				<!-- Ticket legs if present -->
				{#if selectedRow.legs && Array.isArray(selectedRow.legs) && selectedRow.legs.length > 0}
					<div class="mt-4">
						<h4 class="text-sm font-semibold text-foreground mb-2">Legs</h4>
							{#each selectedRow.legs as leg ((leg.id ?? `${leg.match_id ?? 'match'}-${leg.selection ?? 'selection'}-${leg.odds ?? 'odds'}`) as string | number)}
								<div class="p-2 bg-muted/30 border border-border mb-2 text-sm">
									<div class="flex items-start justify-between gap-3">
										<div>
											<p class="font-medium text-foreground">{ticketLegMatchLabel(leg)}</p>
											<p class="mt-1 text-xs text-muted-foreground">{ticketLegMetaLabel(leg)}</p>
										</div>
									<span class="font-mono">{ticketLegOddsLabel(leg)}</span>
								</div>
							</div>
						{/each}
					</div>
				{/if}

				{#if selectedRow.model_prediction}
					{@const prediction = selectedRow.model_prediction as NonNullable<PredictionRun['model_predictions']>[number]}
					<div class="mt-4">
						<h4 class="mb-2 text-sm font-semibold text-foreground">Model probabilities</h4>
						<div class="grid grid-cols-3 gap-2 text-center">
							<div class="border border-border bg-muted/30 p-2">
								<p class="text-[10px] uppercase text-muted-foreground">Home</p>
								<p class="font-mono text-sm">{(prediction.home_prob * 100).toFixed(2)}%</p>
							</div>
							<div class="border border-border bg-muted/30 p-2">
								<p class="text-[10px] uppercase text-muted-foreground">Draw</p>
								<p class="font-mono text-sm">
									{prediction.draw_prob === null ? '--' : `${(prediction.draw_prob * 100).toFixed(2)}%`}
								</p>
							</div>
							<div class="border border-border bg-muted/30 p-2">
								<p class="text-[10px] uppercase text-muted-foreground">Away</p>
								<p class="font-mono text-sm">{(prediction.away_prob * 100).toFixed(2)}%</p>
							</div>
						</div>
					</div>
					{#if prediction.quality_report}
						<div class="mt-4 space-y-3">
							<h4 class="text-sm font-semibold text-foreground">Prediction quality</h4>
							<div class="grid grid-cols-2 gap-2 text-sm">
								<div class="border border-border bg-muted/30 p-2">
									<p class="text-[10px] uppercase text-muted-foreground">Reliability</p>
									<Badge variant={reliabilityBadgeVariant(prediction.quality_report.reliability?.label ?? '')}>
										{prediction.quality_report.reliability?.label ?? 'unknown'}
									</Badge>
								</div>
								<div class="border border-border bg-muted/30 p-2">
									<p class="text-[10px] uppercase text-muted-foreground">Ticket eligible</p>
									<p class="font-mono text-sm">
										{prediction.quality_report.reliability?.is_ticket_eligible ? 'yes' : 'no'}
									</p>
								</div>
								<div class="border border-border bg-muted/30 p-2">
									<p class="text-[10px] uppercase text-muted-foreground">Market pick</p>
									<p class="font-mono text-sm">{prediction.quality_report.market?.pick ?? '--'}</p>
								</div>
								<div class="border border-border bg-muted/30 p-2">
									<p class="text-[10px] uppercase text-muted-foreground">Training matches</p>
									<p class="font-mono text-sm">{prediction.quality_report.training?.total_matches ?? '--'}</p>
								</div>
							</div>
							{#if prediction.quality_report.reliability?.block_reasons?.length}
								<div class="border border-border bg-muted/30 p-2 text-xs text-muted-foreground">
									<span class="font-medium text-foreground">Blocked reasons:</span>
									{prediction.quality_report.reliability.block_reasons.join(', ')}
								</div>
							{/if}
						</div>
					{/if}
				{/if}
			</div>
		{/if}
	</DialogContent>
</DialogRoot>
