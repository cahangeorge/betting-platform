<script lang="ts">
	import { ApiClientError } from '$lib/api/client';
	import { bankrollApi } from '$lib/api/bankroll';
	import { jobsApi } from '$lib/api/jobs';
	import { matchesApi } from '$lib/api/matches';
	import { cronFromInterval, describeScheduledJob, scheduledJobsForArea } from '$lib/scheduled-jobs.helpers';
	import { ticketsApi } from '$lib/api/tickets';
	import { betslip, betslipCombinedOdds, betslipPotentialReturn } from '$lib/stores/betslip';
	import type {
		Bankroll,
		Match,
		PlaceBetRequest,
		ScheduledJob,
		Ticket,
		TicketBatch,
		TicketType
	} from '$lib/types';
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
		serverStats,
		serverBankrolls,
		serverBatches
	}: {
		serverTickets?: Ticket[];
		serverMatches?: Match[];
		serverStats?: { total: number; won: number; lost: number; profit_loss: number };
		serverBankrolls?: Bankroll[];
		serverBatches?: TicketBatch[];
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
	let settlementChecking = $state(false);
	let settlementMessage = $state('');
	let autoVerificationEnabled = $state(true);
	let autoVerificationIntervalNumber = $state('1');
	let autoVerificationIntervalUnit = $state('Hours');
	let scheduledJobs = $state<ScheduledJob[]>([]);
	let loadingScheduledJobs = $state(false);
	let scheduledJobsError = $state('');
	let savingScheduledJob = $state(false);
	let interactive = $state(false);

	let betMatchId = $state('');
	let betMarket = $state('1x2');
	let betSelection = $state('home');
	let betOdds = $state('2.00');
	let betStake = $state('10');
	let betType = $state<TicketType>('single');
	let betError = $state('');
	let betSubmitting = $state(false);
	let generateTicketCount = $state('5');
	let generateDifficulty = $state('balanced');
	let generateMarkets = $state<string[]>(['1x2']);
	let generateMinOdds = $state('1.20');
	let generateMaxOdds = $state('5.00');
	let autoTicketGenerationEnabled = $state(true);
	let autoTicketIntervalNumber = $state('1');
	let autoTicketIntervalUnit = $state('Hours');
	let generatedBatchId = $state<number | null>(null);
	let generatedTickets = $state<Ticket[]>([]);
	let generatingTickets = $state(false);
	let generateMessage = $state('');
	let generateError = $state('');
	let batches = $state<TicketBatch[]>([]);
	let selectedBatchId = $state('');
	let batchTickets = $state<Ticket[]>([]);
	let batchTicketsLoading = $state(false);
	let batchLoadError = $state('');
	let historySourceSwapLeg = $state('');
	let historyTargetSwapLeg = $state('');
	let historySwappingLegs = $state(false);
	let historySwapMessage = $state('');
	let sourceSwapLeg = $state('');
	let targetSwapLeg = $state('');
	let swappingLegs = $state(false);
	let swapMessage = $state('');

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
			const [t, m, s, b, fetchedBatches] = await Promise.all([
				ticketsApi.getTickets(),
				matchesApi.getMatches({ status: 'scheduled' }),
				ticketsApi.getStats(),
				bankrollApi.getBankrolls(),
				ticketsApi.getBatches()
			]);
			tickets = t;
			matches = m;
			stats = s;
			bankrolls = b;
			batches = fetchedBatches;
			if (!selectedBatchId && fetchedBatches.length > 0) {
				selectedBatchId = String(fetchedBatches[0].id);
			}
			if (!selectedBankrollId && b.length > 0) {
				selectedBankrollId = String(b[0].id);
			}
		} catch (err) {
			error = err instanceof ApiClientError ? err.message : 'Failed to load tickets';
		} finally {
			loading = false;
		}
	}

	async function fetchScheduledJobs() {
		loadingScheduledJobs = true;
		scheduledJobsError = '';
		try {
			scheduledJobs = await jobsApi.getScheduledJobs();
		} catch (err) {
			scheduledJobsError = err instanceof ApiClientError ? err.message : 'Failed to load scheduled verification jobs';
		} finally {
			loadingScheduledJobs = false;
		}
	}

	async function loadBatchTickets(batchId: number) {
		batchTicketsLoading = true;
		batchLoadError = '';
		try {
			const allBatchTickets = await ticketsApi.getBatchTickets(batchId);
			batchTickets = allBatchTickets;
		} catch (err) {
			batchLoadError = err instanceof ApiClientError ? err.message : 'Failed to load selected batch tickets';
			batchTickets = [];
		} finally {
			batchTicketsLoading = false;
		}
	}

	$effect(() => {
		const batchId = Number.parseInt(selectedBatchId, 10);
		if (!Number.isFinite(batchId) || batchId <= 0) {
			batchTickets = [];
			return;
		}
		void loadBatchTickets(batchId);
	});

	async function verifyResults() {
		settlementChecking = true;
		settlementMessage = '';
		try {
			const summary = await ticketsApi.settleDue();
			settlementMessage =
				summary.settled_tickets > 0
					? `Settled ${summary.settled_tickets} ticket${summary.settled_tickets === 1 ? '' : 's'}: ${summary.won_tickets} won, ${summary.lost_tickets} lost, ${summary.void_tickets} void.`
					: `Checked ${summary.checked_tickets} open ticket${summary.checked_tickets === 1 ? '' : 's'}; no ticket was ready to settle.`;
			await loadTickets();
		} catch (err) {
			settlementMessage = err instanceof ApiClientError ? err.message : 'Failed to verify ticket results';
		} finally {
			settlementChecking = false;
		}
	}

	async function toggleScheduledJob(jobId: number) {
		scheduledJobsError = '';
		try {
			const updated = await jobsApi.toggleJob(jobId);
			scheduledJobs = scheduledJobs.map((job) => (job.id === jobId ? updated : job));
		} catch (err) {
			scheduledJobsError =
				err instanceof ApiClientError ? err.message : 'Failed to toggle scheduled verification job';
		}
	}

	async function saveAutomaticVerificationAction() {
		savingScheduledJob = true;
		scheduledJobsError = '';
		try {
			const created = await jobsApi.createScheduledJob({
				name: `Auto verify results every ${autoVerificationIntervalNumber} ${autoVerificationIntervalUnit.toLowerCase()}`,
				task_type: 'verify_results',
				cron_expression: cronFromInterval(
					autoVerificationIntervalNumber,
					autoVerificationIntervalUnit
				),
				config: {
					source_page: 'tickets',
					area: 'verification',
					limit: 100,
					unsupported_policy: 'pending'
				}
			});
			scheduledJobs = [created, ...scheduledJobs.filter((job) => job.id !== created.id)];
		} catch (err) {
			scheduledJobsError =
				err instanceof ApiClientError ? err.message : 'Failed to save automatic verification job';
		} finally {
			savingScheduledJob = false;
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

	function toggleGenerateMarket(market: string) {
		if (generateMarkets.includes(market)) {
			generateMarkets = generateMarkets.filter((item) => item !== market);
		} else {
			generateMarkets = [...generateMarkets, market];
		}
	}

	async function generateAutomaticTickets() {
		generatingTickets = true;
		generateError = '';
		generateMessage = '';
		swapMessage = '';
		const bankrollId = selectedBankrollId ? parseInt(selectedBankrollId, 10) : NaN;

		try {
			if (!Number.isFinite(bankrollId) || bankrollId <= 0) {
				generateError = 'Create or select a bankroll before generating tickets';
				return;
			}
			if (generateMarkets.length === 0) {
				generateError = 'Select at least one market type';
				return;
			}
			const response = await ticketsApi.generate({
				bankroll_id: bankrollId,
				ticket_count: parseInt(generateTicketCount, 10) || 1,
				difficulty: generateDifficulty,
				market_types: generateMarkets,
				min_odds: parseFloat(generateMinOdds) || 1.01,
				max_odds: parseFloat(generateMaxOdds) || 100,
				stake: parseFloat(betStake || '10') || 10
			});
			generatedBatchId = response.batch_id;
			generatedTickets = response.tickets;
			tickets = [...response.tickets, ...tickets.filter((ticket) => !response.tickets.some((created) => created.id === ticket.id))];
			activeTab = 'place';
			generateMessage = `Generated ${response.tickets.length} ticket${response.tickets.length === 1 ? '' : 's'} in batch #${response.batch_id}.`;
		} catch (err) {
			generateError = err instanceof ApiClientError ? err.message : 'Failed to generate tickets';
		} finally {
			generatingTickets = false;
		}
	}

	async function saveAutomaticTicketGenerationAction() {
		savingScheduledJob = true;
		scheduledJobsError = '';
		try {
			const bankrollId = selectedBankrollId ? parseInt(selectedBankrollId, 10) : NaN;
			const created = await jobsApi.createScheduledJob({
				name: `Auto generate ${generateDifficulty} tickets`,
				task_type: 'generate_tickets',
				cron_expression: cronFromInterval(autoTicketIntervalNumber, autoTicketIntervalUnit),
				config: {
					source_page: 'tickets',
					area: 'tickets',
					bankroll_id: Number.isFinite(bankrollId) && bankrollId > 0 ? bankrollId : undefined,
					ticket_count: parseInt(generateTicketCount, 10) || 1,
					difficulty: generateDifficulty,
					market_types: generateMarkets,
					min_odds: parseFloat(generateMinOdds) || 1.01,
					max_odds: parseFloat(generateMaxOdds) || 100,
					stake: parseFloat(betStake || '10') || 10
				}
			});
			scheduledJobs = [created, ...scheduledJobs.filter((job) => job.id !== created.id)];
		} catch (err) {
			scheduledJobsError =
				err instanceof ApiClientError ? err.message : 'Failed to save automatic ticket generation job';
		} finally {
			savingScheduledJob = false;
		}
	}

	function generatedLegOptions(): { value: string; label: string }[] {
		return generatedTickets.flatMap((ticket) =>
			ticket.legs.map((leg) => ({
				value: `${ticket.id}:${leg.id}`,
				label: `Ticket #${ticket.reference ?? ticket.id} · ${leg.match?.home_team ?? 'Match'} vs ${leg.match?.away_team ?? '?'} · ${leg.market}/${leg.selection}`
			}))
		);
	}

	function batchLegOptions(usableTickets: Ticket[]): { value: string; label: string }[] {
		return usableTickets.flatMap((ticket) =>
			ticket.legs.map((leg) => ({
				value: `${ticket.id}:${leg.id}`,
				label: `Ticket #${ticket.reference ?? ticket.id} · ${leg.match?.home_team ?? 'Match'} vs ${leg.match?.away_team ?? '?'} · ${leg.market}/${leg.selection}`
			}))
		);
	}

	function parseSwapLeg(value: string): { ticketId: number; legId: number } | null {
		const [ticketId, legId] = value.split(':').map((entry) => parseInt(entry, 10));
		if (!Number.isFinite(ticketId) || !Number.isFinite(legId)) return null;
		return { ticketId, legId };
	}

	function replaceTicket(updated: Ticket) {
		generatedTickets = generatedTickets.map((ticket) => (ticket.id === updated.id ? updated : ticket));
		tickets = tickets.map((ticket) => (ticket.id === updated.id ? updated : ticket));
		batchTickets = batchTickets.map((ticket) => (ticket.id === updated.id ? updated : ticket));
	}

	function estimateWinChance(ticket: Ticket): number {
		if (!ticket.total_odds || !Number.isFinite(ticket.total_odds) || ticket.total_odds <= 1) return 0;
		return Number(((1 / ticket.total_odds) * 100).toFixed(1));
	}

	function matchStatusText(match: Partial<Match> | null | undefined): string {
		if (!match) return 'status n/a';
		const status = match.status || 'n/a';
		if (status === 'live' && match.start_time) {
			const startAt = new Date(match.start_time);
			if (!Number.isNaN(startAt.getTime())) {
				const minutes = Math.floor((Date.now() - startAt.getTime()) / 60000);
				return `Live (~${Math.max(minutes, 0)}m)`;
			}
		}
		if (status === 'finished') return 'Finished';
		if (status === 'scheduled' && match.start_time) {
			const startAt = new Date(match.start_time);
			if (!Number.isNaN(startAt.getTime())) {
				return `Scheduled ${startAt.toLocaleString()}`;
			}
		}
		if (status === 'cancelled') return 'Cancelled';
		if (status === 'postponed') return 'Postponed';
		return status;
	}

	async function swapGeneratedLegs() {
		if (generatedBatchId === null) {
			swapMessage = 'Generate a batch before swapping legs.';
			return;
		}
		const source = parseSwapLeg(sourceSwapLeg);
		const target = parseSwapLeg(targetSwapLeg);
		if (!source || !target) {
			swapMessage = 'Select a source leg and a target leg.';
			return;
		}

		swappingLegs = true;
		swapMessage = '';
		try {
			const response = await ticketsApi.swapLegs(generatedBatchId, {
				source_ticket_id: source.ticketId,
				source_leg_id: source.legId,
				target_ticket_id: target.ticketId,
				target_leg_id: target.legId
			});
			replaceTicket(response.source_ticket);
			replaceTicket(response.target_ticket);
			sourceSwapLeg = '';
			targetSwapLeg = '';
			swapMessage = 'Leg swap saved and ticket odds recalculated.';
		} catch (err) {
			swapMessage = err instanceof ApiClientError ? err.message : 'Failed to swap ticket legs';
		} finally {
			swappingLegs = false;
		}
	}

	async function swapBatchLegs() {
		const batchId = Number.parseInt(selectedBatchId, 10);
		if (!Number.isFinite(batchId) || batchId <= 0) {
			historySwapMessage = 'Select a generated job to swap legs.';
			return;
		}
		const source = parseSwapLeg(historySourceSwapLeg);
		const target = parseSwapLeg(historyTargetSwapLeg);
		if (!source || !target) {
			historySwapMessage = 'Select a source leg and a target leg.';
			return;
		}

		historySwappingLegs = true;
		historySwapMessage = '';
		try {
			const response = await ticketsApi.swapLegs(batchId, {
				source_ticket_id: source.ticketId,
				source_leg_id: source.legId,
				target_ticket_id: target.ticketId,
				target_leg_id: target.legId
			});
			replaceTicket(response.source_ticket);
			replaceTicket(response.target_ticket);
			historySourceSwapLeg = '';
			historyTargetSwapLeg = '';
			historySwapMessage = 'Leg swap saved and ticket odds recalculated.';
		} catch (err) {
			historySwapMessage = err instanceof ApiClientError ? err.message : 'Failed to swap ticket legs';
		} finally {
			historySwappingLegs = false;
		}
	}

	onMount(() => {
		interactive = true;
		tickets = serverTickets ?? [];
		matches = serverMatches ?? [];
		stats = serverStats ?? { total: 0, won: 0, lost: 0, profit_loss: 0 };
		bankrolls = serverBankrolls ?? [];
		batches = serverBatches ?? [];
		if (!selectedBankrollId && serverBankrolls?.[0]) {
			selectedBankrollId = String(serverBankrolls[0].id);
		}
		if (!selectedBatchId && serverBatches?.[0]) {
			selectedBatchId = String(serverBatches[0].id);
		}

		if (
			shouldAutoLoadTicketsData({
				serverTickets,
				serverMatches,
				serverStats,
				serverBankrolls,
				serverBatches,
				hasRequestedInitialLoad
			})
		) {
			hasRequestedInitialLoad = true;
			void loadTickets();
		}
		void fetchScheduledJobs();
			const pollInterval = setInterval(loadTickets, 30000);
			return () => {
				clearInterval(pollInterval);
			};
		});

	const selectedBatchIdNumber = $derived.by(() => {
		const parsed = Number.parseInt(selectedBatchId, 10);
		return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
	});
	const selectedBatch = $derived.by(() =>
		selectedBatchIdNumber === null
			? null
			: batches.find((batch) => batch.id === selectedBatchIdNumber) ?? null
	);
	const selectedBatchTickets = $derived.by(() => {
		if (selectedBatchIdNumber === null) return [];
		const fromBatch = batchTickets.filter((ticket) => ticket.batch_id === selectedBatchIdNumber);
		if (fromBatch.length > 0) return fromBatch;
		return tickets.filter((ticket) => ticket.batch_id === selectedBatchIdNumber);
	});
	const selectedBatchCompleted = $derived(
		selectedBatchTickets.filter((ticket) => ticket.status !== 'open').length
	);
	const selectedBatchProgress = $derived(
		selectedBatch?.tickets_count
			? `${selectedBatchCompleted}/${selectedBatch.tickets_count} finalized`
			: `${selectedBatchCompleted}/${selectedBatchTickets.length} finalized`
	);
	const batchOptions = $derived(
		batches.map((batch) => ({
			value: String(batch.id),
			label: `#${batch.id}${batch.name ? ` · ${batch.name}` : ''} (${batch.tickets_count} tickets)`
		}))
	);

	const activeTickets = $derived(tickets.filter((t) => t.status === 'open'));
	const automaticVerificationJobs = $derived(scheduledJobsForArea(scheduledJobs, 'verification'));
	const automaticTicketJobs = $derived(scheduledJobsForArea(scheduledJobs, 'tickets'));
	const tabs = $derived([
		{ id: 'active', label: 'Active', count: activeTickets.length },
		{ id: 'history', label: 'Istorice', count: batches.length },
		{ id: 'place', label: 'Place bet', count: $betslip.legs.length || undefined }
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

	<div class="flex flex-col gap-3 border border-border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
		<div>
			<h2 class="text-sm font-semibold text-foreground">Result verification</h2>
			<p class="mt-1 text-xs text-muted-foreground">
				Settle open tickets locally when their linked matches already have final scores.
			</p>
			{#if settlementMessage}
				<p class="mt-2 text-xs text-muted-foreground">{settlementMessage}</p>
			{/if}
			{#if scheduledJobsError}
				<p class="mt-2 text-xs text-destructive">{scheduledJobsError}</p>
			{/if}
		</div>
		<div class="flex flex-wrap gap-2">
			<Button variant="ghost" onclick={fetchScheduledJobs} disabled={loadingScheduledJobs}>
				{loadingScheduledJobs ? 'Refreshing jobs...' : 'Refresh jobs'}
			</Button>
			<Button variant="secondary" onclick={verifyResults} disabled={settlementChecking}>
				{settlementChecking ? 'Verifying...' : 'Verify results'}
			</Button>
		</div>
	</div>

	<div class="space-y-3 border border-border bg-muted/20 p-4">
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div>
				<h3 class="text-sm font-semibold text-foreground">Automatic verification job</h3>
				<p class="mt-1 text-xs text-muted-foreground">
					Create an hourly or daily settlement job in <span class="font-mono">/api/v1/jobs</span>.
				</p>
			</div>
			<Button
				variant="glow"
				onclick={saveAutomaticVerificationAction}
				disabled={!interactive || savingScheduledJob || !autoVerificationEnabled}
			>
				{savingScheduledJob ? 'Saving...' : 'Save auto verification'}
			</Button>
		</div>

		<label class="flex items-center gap-2 text-sm text-foreground">
			<input
				type="checkbox"
				class="h-4 w-4 accent-football-blue"
				bind:checked={autoVerificationEnabled}
			/>
			<span>Enable saved scheduled result verification</span>
		</label>

		<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
			<Input
				label="Interval number"
				name="tickets-auto-verification-interval"
				type="number"
				min="1"
				bind:value={autoVerificationIntervalNumber}
				disabled={!autoVerificationEnabled}
			/>
			<Select
				label="Interval unit"
				bind:value={autoVerificationIntervalUnit}
				options={[
					{ value: 'Hours', label: 'Hours' },
					{ value: 'Days', label: 'Days' },
					{ value: 'Weeks', label: 'Weeks' }
				]}
				disabled={!autoVerificationEnabled}
			/>
		</div>

		{#if loadingScheduledJobs}
			<p class="text-xs text-muted-foreground">Loading verification jobs...</p>
		{:else if automaticVerificationJobs.length === 0}
			<p class="text-xs text-muted-foreground">No automatic verification job saved yet.</p>
		{:else}
			<div class="flex flex-wrap gap-2">
				{#each automaticVerificationJobs as scheduledJob (scheduledJob.id)}
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
											<span>{matchStatusText(leg.match)}</span>
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
				{#if batches.length === 0}
					<p class="py-12 text-center text-muted-foreground">No ticket jobs yet</p>
				{:else}
					<div class="space-y-4">
						<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
							<Select
								label="Select generated job"
								bind:value={selectedBatchId}
								options={batchOptions}
								placeholder="Select batch..."
							/>
							<Card class="border-muted/50 bg-card p-4">
								<p class="text-xs uppercase tracking-wider text-muted-foreground">Progress</p>
								<p class="text-sm font-medium text-foreground">
									{selectedBatch?.tickets_count ?? selectedBatchTickets.length} tickets · {selectedBatchProgress}
								</p>
								<p class="mt-1 text-xs text-muted-foreground">
									Created: {selectedBatch ? new Date(selectedBatch.created_at).toLocaleString() : '—'}
								</p>
							</Card>
						</div>

						{#if batchTicketsLoading}
							<Loading message="Loading selected job tickets..." />
						{:else if batchLoadError}
							<div class="border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
								{batchLoadError}
							</div>
						{:else if selectedBatchTickets.length === 0}
							<p class="py-12 text-center text-muted-foreground">This job has no tickets yet</p>
						{:else}
							<div class="grid grid-cols-1 gap-3">
								{#each selectedBatchTickets as ticket (ticket.id)}
									<div class="border border-border bg-muted/20 p-3">
										<div class="flex flex-wrap items-start justify-between gap-3">
											<div>
												<p class="font-mono text-sm text-foreground">#{ticket.reference ?? ticket.id}</p>
												<p class="text-xs text-muted-foreground">
													{ticket.legs.length} legs · {ticket.status} · chance {estimateWinChance(ticket).toFixed(1)}%
												</p>
											</div>
											<div class="text-right">
												<p class="font-mono text-football-green">x{ticket.total_odds.toFixed(2)}</p>
												<p class="text-xs text-muted-foreground">return {ticket.potential_return.toFixed(2)}</p>
												<p class="text-xs text-muted-foreground">stake {ticket.stake.toFixed(2)}</p>
											</div>
										</div>
										<div class="mt-3 space-y-1">
											{#each ticket.legs as leg (leg.id)}
												<div class="text-xs text-muted-foreground">
													<span class="text-foreground">{leg.match?.home_team ?? 'Match'} vs {leg.match?.away_team ?? '?'}</span>
													<span class="font-mono"> · {matchStatusText(leg.match)} · {leg.market}/{leg.selection} @ {leg.odds.toFixed(2)}</span>
												</div>
											{/each}
										</div>
									</div>
								{/each}
							</div>

							<div class="space-y-3 border border-border bg-background p-3 md:grid md:grid-cols-[1fr_1fr_auto] md:items-end">
								<p class="text-sm font-medium text-foreground md:col-span-3">Swap legs between tickets in this job</p>
								<Select
									label="Source leg"
									bind:value={historySourceSwapLeg}
									options={batchLegOptions(selectedBatchTickets)}
									placeholder="Select source leg..."
								/>
								<Select
									label="Target leg"
									bind:value={historyTargetSwapLeg}
									options={batchLegOptions(selectedBatchTickets)}
									placeholder="Select target leg..."
								/>
								<Button type="button" variant="secondary" onclick={swapBatchLegs} disabled={historySwappingLegs}>
									{historySwappingLegs ? 'Swapping...' : 'Swap legs'}
								</Button>
								{#if historySwapMessage}
									<p class="text-xs text-muted-foreground md:col-span-3">{historySwapMessage}</p>
								{/if}
							</div>
						{/if}
					</div>
				{/if}
		{:else if activeTab === 'place'}
			<Card class="border-t-football-green p-4">
				<div class="mb-4 space-y-1">
					<h3 class="text-lg font-semibold text-foreground">Place bet</h3>
					<p class="text-sm text-muted-foreground">
						Generate automatic tickets from stored predictions or place a manual ticket.
					</p>
				</div>
				<div class="mb-6 space-y-4 border border-border bg-background p-4">
					<div>
						<h4 class="text-sm font-semibold text-foreground">Automatic ticket generation</h4>
						<p class="mt-1 text-xs text-muted-foreground">
							Uses existing prediction selections, requested markets, odds interval and selected bankroll.
						</p>
					</div>

					{#if generateError}
						<div class="border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{generateError}</div>
					{/if}
					{#if generateMessage}
						<div class="border border-football-green/30 bg-football-green/10 p-3 text-sm text-football-green">{generateMessage}</div>
					{/if}

					<div class="grid grid-cols-1 gap-4 md:grid-cols-4">
						<Input label="Number of tickets" type="number" min="1" max="50" bind:value={generateTicketCount} />
						<Select
							label="Difficulty / safety"
							bind:value={generateDifficulty}
							options={[
								{ value: 'safe', label: 'Safe' },
								{ value: 'balanced', label: 'Balanced' },
								{ value: 'aggressive', label: 'Aggressive' }
							]}
						/>
						<Input label="Min odds" type="number" min="1.01" step="0.01" bind:value={generateMinOdds} />
						<Input label="Max odds" type="number" min="1.01" step="0.01" bind:value={generateMaxOdds} />
					</div>

					<div class="space-y-2">
						<p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Market types</p>
						<div class="flex flex-wrap gap-2">
							{#each ['1x2', 'btts', 'ou_2_5'] as market (market)}
								<label class="flex items-center gap-2 border border-border bg-muted/20 px-3 py-2 text-sm">
									<input
										type="checkbox"
										class="h-4 w-4 accent-football-green"
										checked={generateMarkets.includes(market)}
										onchange={() => toggleGenerateMarket(market)}
									/>
									<span class="font-mono text-foreground">{market}</span>
								</label>
							{/each}
						</div>
					</div>

					<div class="space-y-3 border border-border bg-muted/10 p-3">
						<div class="flex flex-wrap items-center justify-between gap-3">
							<div>
								<p class="text-sm font-semibold text-foreground">Automatic ticket jobs</p>
								<p class="mt-1 text-xs text-muted-foreground">
									Save recurring generation jobs from the current prediction pool.
								</p>
							</div>
							<Button
								type="button"
								variant="secondary"
								onclick={saveAutomaticTicketGenerationAction}
								disabled={!interactive || savingScheduledJob || !autoTicketGenerationEnabled}
							>
								{savingScheduledJob ? 'Saving...' : 'Save auto ticket job'}
							</Button>
						</div>
						<label class="flex items-center gap-2 text-sm text-foreground">
							<input
								type="checkbox"
								class="h-4 w-4 accent-football-green"
								bind:checked={autoTicketGenerationEnabled}
							/>
							<span>Enable saved automatic ticket generation</span>
						</label>
						<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
							<Input
								label="Repeat every"
								type="number"
								min="1"
								bind:value={autoTicketIntervalNumber}
								disabled={!autoTicketGenerationEnabled}
							/>
							<Select
								label="Interval unit"
								bind:value={autoTicketIntervalUnit}
								options={[
									{ value: 'Hours', label: 'Hours' },
									{ value: 'Days', label: 'Days' },
									{ value: 'Weeks', label: 'Weeks' }
								]}
								disabled={!autoTicketGenerationEnabled}
							/>
						</div>
						{#if automaticTicketJobs.length > 0}
							<div class="flex flex-wrap gap-2">
								{#each automaticTicketJobs as scheduledJob (scheduledJob.id)}
									<Button
										type="button"
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
						{:else}
							<p class="text-xs text-muted-foreground">No recurring automatic ticket job saved yet.</p>
						{/if}
					</div>

					<Button type="button" variant="glow" onclick={generateAutomaticTickets} disabled={generatingTickets || bankrolls.length === 0}>
						{generatingTickets ? 'Generating tickets...' : 'Generate automatic tickets'}
					</Button>

					{#if generatedTickets.length > 0}
						<div class="space-y-3 border-t border-border pt-4">
							<div class="flex flex-wrap items-center justify-between gap-2">
								<h4 class="text-sm font-semibold text-foreground">Generated tickets</h4>
								<Badge variant="info">Batch #{generatedBatchId}</Badge>
							</div>
							<div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
								{#each generatedTickets as ticket (ticket.id)}
									<div class="border border-border bg-muted/20 p-3">
										<div class="flex items-center justify-between gap-3">
											<div>
												<p class="font-mono text-sm text-foreground">#{ticket.reference ?? ticket.id}</p>
												<p class="text-xs text-muted-foreground">{ticket.legs.length} legs · {ticket.status}</p>
											</div>
											<div class="text-right">
												<p class="font-mono text-football-green">x{ticket.total_odds.toFixed(2)}</p>
												<p class="text-xs text-muted-foreground">return {ticket.potential_return.toFixed(2)}</p>
											</div>
										</div>
										<div class="mt-3 space-y-1">
											{#each ticket.legs as leg (leg.id)}
												<div class="text-xs text-muted-foreground">
													<span class="text-foreground">{leg.match?.home_team ?? 'Match'} vs {leg.match?.away_team ?? '?'}</span>
													<span class="font-mono"> · {leg.market}/{leg.selection} @ {leg.odds.toFixed(2)}</span>
												</div>
											{/each}
										</div>
									</div>
								{/each}
							</div>

							<div class="grid grid-cols-1 gap-3 border border-border bg-background p-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
								<Select
									label="Source leg"
									bind:value={sourceSwapLeg}
									options={generatedLegOptions()}
									placeholder="Select source leg..."
								/>
								<Select
									label="Target leg"
									bind:value={targetSwapLeg}
									options={generatedLegOptions()}
									placeholder="Select target leg..."
								/>
								<Button type="button" variant="secondary" onclick={swapGeneratedLegs} disabled={swappingLegs}>
									{swappingLegs ? 'Swapping...' : 'Swap legs'}
								</Button>
							</div>
							{#if swapMessage}
								<p class="text-xs text-muted-foreground">{swapMessage}</p>
							{/if}
						</div>
					{/if}
				</div>
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
							disabled={matchOptions.length === 0}
						/>

						{#if matchOptions.length === 0}
							<div class="border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-200">
								No scheduled matches are available for manual placement. Scrape or import matches first.
							</div>
						{/if}

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

						<Button type="submit" disabled={betSubmitting || !betMatchId || bankrolls.length === 0}>
							{betSubmitting ? 'Placing...' : 'Place bet'}
						</Button>
					{/if}
				</form>
			</Card>
		{/if}
	</Tabs>
</div>
