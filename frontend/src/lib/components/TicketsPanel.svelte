<script lang="ts">
	import { ApiClientError } from '$lib/api/client';
	import { bankrollApi } from '$lib/api/bankroll';
	import { matchesApi } from '$lib/api/matches';
	import { ticketsApi } from '$lib/api/tickets';
	import { betslip, betslipCombinedOdds, betslipPotentialReturn } from '$lib/stores/betslip';
	import type { Bankroll, Match, PlaceBetRequest, Ticket, TicketType } from '$lib/types';
	import { onMount } from 'svelte';
	import { shouldAutoLoadTicketsData } from './tickets-panel.helpers';
	import Badge from './ui/Badge.svelte';
	import Button from './ui/Button.svelte';
	import Card from './ui/Card.svelte';
	import Input from './ui/Input.svelte';
	import Loading from './Loading.svelte';
	import Select from './ui/Select.svelte';
	import Tabs from './ui/Tabs.svelte';

	let {
		serverTickets,
		serverMatches,
		serverStats
	}: {
		serverTickets?: Ticket[];
		serverMatches?: Match[];
		serverStats?: { total: number; won: number; lost: number; profit_loss: number };
	} = $props();

	let tickets = $state<Ticket[]>([]);
	let matches = $state<Match[]>([]);
	let stats = $state({ total: 0, won: 0, lost: 0, profit_loss: 0 });
	let loading = $state(false);
	let error = $state('');
	let activeTab = $state('active');
	let bankrolls = $state<Bankroll[]>([]);
	let selectedBankrollId = $state<string>('');
	let hasRequestedInitialLoad = $state(false);

	let betMatchId = $state('');
	let betMarket = $state('1x2');
	let betSelection = $state('home');
	let betOdds = $state('2.00');
	let betStake = $state('10');
	let betType = $state<TicketType>('single');
	let betError = $state('');
	let betSubmitting = $state(false);

	$effect(() => {
		if ($betslip.legs.length > 0) {
			activeTab = 'place';
		}
	});

	const statusBadge: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'default'> = {
		won: 'success',
		open: 'info',
		lost: 'danger',
		cashed_out: 'warning',
		void: 'default'
	};

	async function loadTickets() {
		loading = true;
		try {
			const [t, m, s, b] = await Promise.all([
				ticketsApi.getTickets(),
				matchesApi.getMatches({ status: 'scheduled' }),
				ticketsApi.getStats(),
				bankrollApi.getBankrolls()
			]);
			tickets = t;
			matches = m;
			stats = s;
			bankrolls = b;
			if (!selectedBankrollId && b.length > 0) {
				selectedBankrollId = String(b[0].id);
			}
		} catch (err) {
			error = err instanceof ApiClientError ? err.message : 'Failed to load tickets';
		} finally {
			loading = false;
		}
	}

	function ticketTypeLabel(ticket: Ticket): TicketType {
		return (ticket.ticket_type ?? ticket.type ?? 'single') as TicketType;
	}

	function onTicketTypeChange(event: Event) {
		const target = event.currentTarget as HTMLSelectElement | null;
		if (!target) return;
		betslip.setTicketType(target.value as TicketType);
	}

	async function placeBet() {
		betSubmitting = true;
		betError = '';
		const bankrollId = selectedBankrollId ? parseInt(selectedBankrollId, 10) : NaN;

		try {
			if (!Number.isFinite(bankrollId) || bankrollId <= 0) {
				betError = 'Create or select a bankroll before placing a ticket';
				return;
			}

			if ($betslip.legs.length > 0) {
				const req = {
					legs: $betslip.legs.map((leg) => ({
						match_id: leg.matchId,
						model_prediction_id: leg.modelPredictionId,
						market: leg.marketKey,
						selection: leg.selectionKey,
						odds: leg.odds
					})),
					stake: $betslip.stake,
					ticket_type: $betslip.ticketType,
					bankroll_id: bankrollId
				} satisfies PlaceBetRequest;
				const ticket = await ticketsApi.placeBet(req);
				tickets = [ticket, ...tickets];
				betslip.clearLegs();
				activeTab = 'active';
				return;
			}

			if (!betMatchId || !betStake) {
				betError = 'Select a match and enter a stake';
				return;
			}

			const req = {
				legs: [
					{
						match_id: parseInt(betMatchId, 10),
						market: betMarket,
						selection: betSelection,
						odds: parseFloat(betOdds)
					}
				],
				stake: parseFloat(betStake),
				ticket_type: betType,
				bankroll_id: bankrollId
			} satisfies PlaceBetRequest;
			const ticket = await ticketsApi.placeBet(req);
			tickets = [ticket, ...tickets];
			activeTab = 'active';
		} catch (err) {
			betError = err instanceof ApiClientError ? err.message : 'Failed to place bet';
		} finally {
			betSubmitting = false;
		}
	}

	onMount(() => {
		tickets = serverTickets ?? [];
		matches = serverMatches ?? [];
		stats = serverStats ?? { total: 0, won: 0, lost: 0, profit_loss: 0 };

		if (
			shouldAutoLoadTicketsData({
				serverTickets,
				serverMatches,
				serverStats,
				hasRequestedInitialLoad
			})
		) {
			hasRequestedInitialLoad = true;
			void loadTickets();
		}
		const pollInterval = setInterval(loadTickets, 30000);
		return () => {
			clearInterval(pollInterval);
		};
	});

	const activeTickets = $derived(tickets.filter((t) => t.status === 'open'));
	const tabs = $derived([
		{ id: 'active', label: 'Active', count: activeTickets.length },
		{ id: 'history', label: 'History', count: tickets.length },
		{ id: 'place', label: 'Place Bet', count: $betslip.legs.length || undefined }
	]);
	const matchOptions = $derived(
		matches.map((m) => ({ value: String(m.id), label: `${m.home_team} vs ${m.away_team}` }))
	);
</script>

<div class="space-y-6">
	{#if loading && tickets.length === 0}
		<Loading message="Loading tickets..." />
	{:else if error}
		<div class="border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">{error}</div>
		<Button onclick={loadTickets}>Retry</Button>
	{/if}

	<div class="grid grid-cols-2 gap-4 md:grid-cols-4">
		<Card><p class="text-xs uppercase tracking-wider text-muted-foreground">Total Bets</p><p class="text-2xl font-bold font-mono text-foreground">{stats.total}</p></Card>
		<Card><p class="text-xs uppercase tracking-wider text-muted-foreground">Won</p><p class="text-2xl font-bold font-mono text-football-green">{stats.won}</p></Card>
		<Card><p class="text-xs uppercase tracking-wider text-muted-foreground">Lost</p><p class="text-2xl font-bold font-mono text-destructive">{stats.lost}</p></Card>
		<Card><p class="text-xs uppercase tracking-wider text-muted-foreground">P/L</p><p class="text-2xl font-bold font-mono {stats.profit_loss >= 0 ? 'text-football-green' : 'text-destructive'}">{stats.profit_loss > 0 ? '+' : ''}{stats.profit_loss.toFixed(2)}</p></Card>
	</div>

	<Tabs bind:activeTab {tabs}>
		{#if activeTab === 'active'}
			{#if activeTickets.length === 0}
				<div class="py-12 text-center text-muted-foreground">
					<p>No active tickets</p>
					<Button variant="secondary" class="mt-4" onclick={() => (activeTab = 'place')}>Place a Bet</Button>
				</div>
			{:else}
				<div class="space-y-4">
					{#each activeTickets as ticket (ticket.id)}
						<Card class="border-l-3 border-l-football-green p-4">
							<div class="mb-3 flex items-center justify-between">
								<div class="flex items-center space-x-3">
									<span class="text-sm font-mono text-muted-foreground">#{ticket.reference}</span>
									<Badge variant="info">{ticketTypeLabel(ticket)}</Badge>
									<Badge variant="warning">open</Badge>
								</div>
								<span class="text-xs text-muted-foreground">{new Date(ticket.created_at).toLocaleString()}</span>
							</div>

							<div class="mb-3 grid grid-cols-3 gap-4">
								<div><p class="text-xs text-muted-foreground">Stake</p><p class="text-sm font-medium font-mono text-foreground">{ticket.stake.toFixed(2)}</p></div>
								<div><p class="text-xs text-muted-foreground">Odds</p><p class="text-sm font-medium font-mono text-football-green">x{ticket.total_odds.toFixed(2)}</p></div>
								<div><p class="text-xs text-muted-foreground">Potential Return</p><p class="text-sm font-medium font-mono text-foreground">{ticket.potential_return.toFixed(2)}</p></div>
							</div>

							<div class="space-y-1">
								{#each ticket.legs as leg (leg.id)}
									<div class="flex items-center space-x-2 text-xs text-muted-foreground">
										<span>{leg.match?.home_team ?? 'Match'} vs {leg.match?.away_team ?? '?'}</span>
										<span class="text-border">|</span>
										<span>{leg.market}</span>
										<span class="text-border">|</span>
										<span>{leg.selection} @ {leg.odds.toFixed(2)}</span>
									</div>
								{/each}
							</div>
						</Card>
					{/each}
				</div>
			{/if}
		{:else if activeTab === 'history'}
			{#if tickets.length === 0}
				<p class="py-12 text-center text-muted-foreground">No ticket history</p>
			{:else}
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="border-b border-border bg-muted font-sans text-xs uppercase text-muted-foreground">
							<tr>
								<th class="px-4 py-3 text-left">Reference</th>
								<th class="px-4 py-3 text-left">Type</th>
								<th class="px-4 py-3 text-left">Status</th>
								<th class="px-4 py-3 text-right">Stake</th>
								<th class="px-4 py-3 text-right">Odds</th>
								<th class="px-4 py-3 text-right">Return</th>
								<th class="px-4 py-3 text-left">Date</th>
							</tr>
						</thead>
						<tbody>
							{#each tickets as ticket (ticket.id)}
								<tr class="border-b border-border transition-colors duration-200 hover:bg-muted">
									<td class="px-4 py-3 font-mono text-muted-foreground">#{ticket.reference}</td>
									<td class="px-4 py-3"><Badge>{ticketTypeLabel(ticket)}</Badge></td>
									<td class="px-4 py-3"><Badge variant={statusBadge[ticket.status] || 'default'}>{ticket.status}</Badge></td>
									<td class="px-4 py-3 text-right font-mono">{ticket.stake.toFixed(2)}</td>
									<td class="px-4 py-3 text-right font-mono text-football-green">x{ticket.total_odds.toFixed(2)}</td>
									<td class="px-4 py-3 text-right font-mono {ticket.actual_return !== null && ticket.actual_return > 0 ? 'text-football-green' : ticket.actual_return !== null ? 'text-destructive' : 'text-muted-foreground'}">{ticket.actual_return !== null ? ticket.actual_return.toFixed(2) : '-'}</td>
									<td class="px-4 py-3 text-xs text-muted-foreground">{new Date(ticket.created_at).toLocaleDateString()}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		{:else if activeTab === 'place'}
			<Card class="border-t-football-green p-4">
				<h3 class="mb-4 text-lg font-semibold text-foreground">Place Bet</h3>
				<form onsubmit={(e) => { e.preventDefault(); placeBet(); }} class="space-y-4">
					{#if betError}
						<div class="border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{betError}</div>
					{/if}

					{#if $betslip.legs.length > 0}
						<Select
							label="Bankroll"
							bind:value={selectedBankrollId}
							options={bankrolls.map((bankroll) => ({
								value: String(bankroll.id),
								label: `${bankroll.name} · ${bankroll.currency} ${bankroll.balance.toFixed(2)}`
							}))}
							placeholder="Select bankroll..."
						/>

						{#if bankrolls.length === 0}
							<div class="border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
								No bankroll available. Create one in Account before placing a ticket.
							</div>
						{/if}

						<div class="space-y-2">
							{#each $betslip.legs as leg (leg.id)}
								<div class="flex items-center justify-between border border-border bg-background px-3 py-2 text-sm">
									<div>
										<div class="font-medium text-foreground">{leg.matchName}</div>
										<div class="text-xs text-muted-foreground">
											{leg.market} · {leg.selection}
											{#if leg.source}
												<span class="ml-1 uppercase tracking-wide">· {leg.source}</span>
											{/if}
										</div>
									</div>
									<div class="font-mono text-football-green">{leg.odds.toFixed(2)}</div>
								</div>
							{/each}
						</div>

						<div class="grid grid-cols-2 gap-4">
							<Input
								label="Stake"
								type="number"
								step="0.50"
								value={$betslip.stake.toString()}
								oninput={(e) => betslip.setStake(parseFloat(e.currentTarget.value) || 0)}
							/>
							<Select
								label="Ticket Type"
								value={$betslip.ticketType}
								options={[
									{ value: 'single', label: 'Single' },
									{ value: 'accumulator', label: 'Accumulator' }
								]}
								onchange={onTicketTypeChange}
							/>
						</div>

						<div class="border border-border bg-background p-3">
							<div class="flex justify-between text-sm">
								<span class="text-muted-foreground">Combined Odds:</span>
								<span class="font-mono font-medium text-foreground">x{$betslipCombinedOdds.toFixed(2)}</span>
							</div>
							<div class="mt-1 flex justify-between text-sm">
								<span class="text-muted-foreground">Potential Return:</span>
								<span class="font-mono text-football-green">£{$betslipPotentialReturn.toFixed(2)}</span>
							</div>
						</div>

						<div class="flex gap-2">
							<Button type="button" variant="secondary" onclick={() => betslip.clearLegs()}>
								Clear Slip
							</Button>
							<Button type="submit" disabled={betSubmitting || $betslip.stake <= 0} class="flex-1">
								{betSubmitting ? 'Placing...' : 'Place Ticket'}
							</Button>
						</div>
					{:else}
						<Select
							label="Bankroll"
							bind:value={selectedBankrollId}
							options={bankrolls.map((bankroll) => ({
								value: String(bankroll.id),
								label: `${bankroll.name} · ${bankroll.currency} ${bankroll.balance.toFixed(2)}`
							}))}
							placeholder="Select bankroll..."
						/>

						{#if bankrolls.length === 0}
							<div class="border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
								No bankroll available. Create one in Account before placing a ticket.
							</div>
						{/if}

						<Select
							label="Match"
							bind:value={betMatchId}
							options={matchOptions}
							placeholder="Select a match..."
						/>

						<div class="grid grid-cols-2 gap-4">
							<Select
								label="Market"
								bind:value={betMarket}
								options={[
									{ value: '1x2', label: '1X2 (Match Result)' },
									{ value: 'over_under', label: 'Over/Under' },
									{ value: 'both_score', label: 'Both to Score' }
								]}
							/>
							<Select
								label="Selection"
								bind:value={betSelection}
								options={[
									{ value: 'home', label: 'Home' },
									{ value: 'draw', label: 'Draw' },
									{ value: 'away', label: 'Away' }
								]}
							/>
						</div>

						<div class="grid grid-cols-2 gap-4">
							<Input label="Odds" type="number" step="0.01" bind:value={betOdds} />
							<Input label="Stake" type="number" step="0.50" bind:value={betStake} />
						</div>

						<div class="border border-border bg-background p-3">
							<div class="flex justify-between text-sm">
								<span class="text-muted-foreground">Potential Return:</span>
								<span class="font-mono font-medium text-football-green">
									{(parseFloat(betStake || '0') * parseFloat(betOdds || '1')).toFixed(2)}
								</span>
							</div>
							<div class="mt-1 flex justify-between text-sm">
								<span class="text-muted-foreground">Profit:</span>
								<span class="font-mono text-football-green">
									{(parseFloat(betStake || '0') * parseFloat(betOdds || '1') - parseFloat(betStake || '0')).toFixed(2)}
								</span>
							</div>
						</div>

						<Button type="submit" disabled={betSubmitting || !betMatchId}>
							{betSubmitting ? 'Placing...' : 'Place Bet'}
						</Button>
					{/if}
				</form>
			</Card>
		{/if}
	</Tabs>
</div>
