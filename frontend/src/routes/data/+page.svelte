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
	import type { Match, Ticket, PredictionRun } from '$lib/types';
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
			predictionRuns = await predictionsApi.getRuns();
		} catch {
			predictionRuns = [];
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
				const hay = `${t.reference} ${t.type} ${t.status}`.toLowerCase();
				if (!hay.includes(searchLower)) return false;
			}
			return true;
		})
	);

	const predictionRows = $derived.by(() => {
		const rows: {
			id: number;
			date: string;
			match: string;
			model: string;
			status: string;
			results: PredictionRun['results'];
			error: string | null;
		}[] = [];
		for (const run of predictionRuns) {
			if (run.results && run.results.length > 0) {
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
				const matchKey = run.matches.join(', ');
				if (searchQuery && !matchKey.toLowerCase().includes(searchLower)) continue;
				rows.push({
					id: run.id,
					date: run.created_at,
					match: `Run #${run.id} (${run.matches.length} matches)`,
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
			{ key: 'status', label: 'Status' },
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
				probability: firstResult
					? `${((firstResult.home_prob + firstResult.draw_prob + firstResult.away_prob) / 3 * 100).toFixed(1)}`
					: '--',
				confidence: firstResult ? `${(firstResult.confidence * 100).toFixed(1)}` : '--'
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

	function statusBadgeVariant(status: string): 'success' | 'danger' | 'info' | 'neutral' {
		const s = status.toLowerCase();
		if (s === 'won' || s === 'completed' || s === 'finished') return 'success';
		if (s === 'lost' || s === 'failed' || s === 'cancelled') return 'danger';
		if (s === 'live' || s === 'running' || s === 'open') return 'info';
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
		if (predictionRuns.length === 0) fetchPredictions();
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
								{#each currentRowsFormatted as row, i ((row.id ?? `${activeTab}-${page}-${i}`) as string | number)}
									<tr
										class="border-b border-border last:border-0 hover:bg-muted/30 transition-colors cursor-pointer"
										onclick={() => openRowDetail(row)}
								>
									{#each currentColumns as col (col.key)}
										<td class="px-3 py-2.5 font-mono text-sm">
											{#if col.key === 'status'}
												<Badge variant={statusBadgeVariant(String(row[col.key] ?? ''))}>
													{row[col.key]}
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
						{#if key !== 'legs' && key !== 'results' && key !== 'odds' && key !== 'parameters'}
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
									<div class="flex justify-between">
										<span>{leg.home_team} vs {leg.away_team}</span>
									<span class="font-mono">{leg.odds}</span>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{/if}
	</DialogContent>
</DialogRoot>
