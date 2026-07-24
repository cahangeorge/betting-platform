<script lang="ts">
	import { ApiClientError } from '$lib/api/client';
	import { bankrollApi } from '$lib/api/bankroll';
	import { dataApi } from '$lib/api/data';
	import { jobsApi } from '$lib/api/jobs';
	import { matchesApi } from '$lib/api/matches';
	import { cronFromInterval, describeScheduledJob, scheduledJobsForArea } from '$lib/scheduled-jobs.helpers';
	import { ticketsApi } from '$lib/api/tickets';
	import { tradingApi } from '$lib/api/trading';
	import { betslip, betslipCombinedOdds, betslipPotentialReturn } from '$lib/stores/betslip';
	import type {
		Bankroll,
		Match,
		PlaceBetRequest,
		ScheduledJob,
		Ticket,
		TicketBatch,
		TicketBatchLineage,
		TicketGenerationReport,
		TicketLineageLeg,
		TicketPreflightResponse,
		TicketRiskAssessment,
		TicketType,
		TradingAccount,
		TradingExecution
	} from '$lib/types';
	import { onMount } from 'svelte';
	import { AlertDialog } from 'bits-ui';
	import { countFinalScoreConflicts, finalScoreConflictPolicyMessage } from '$lib/result-refresh.helpers';
	import {
		analyzeReturnHref,
		generatedBatchLoadState,
		selectionCountLabel,
		shouldAutoLoadTicketsData,
		ticketCountLabel,
		ticketGenerationPreflight,
		ticketRunIdsFromReport,
		ticketStatusLabel,
		ticketTypeLabel as localizedTicketTypeLabel,
		type TicketHandoff,
		verificationActionState
	} from './tickets-panel.helpers';
	import Badge from './ui/Badge.svelte';
	import Button from './ui/Button.svelte';
	import Card from './ui/Card.svelte';
	import { DialogFooter, DialogHeader } from './ui/dialog';
	import Input from './ui/Input.svelte';
	import Loading from './Loading.svelte';
	import Select from './ui/Select.svelte';
	import Tabs from './ui/Tabs.svelte';
	import RiskLadder from './RiskLadder.svelte';
	import TicketDecisionEvidence from './TicketDecisionEvidence.svelte';

	let {
		serverTickets,
		serverMatches,
		serverStats,
		serverBankrolls,
		serverBatches,
		serverTradingAccounts,
		paperTradingEnabled = false,
		handoff
	}: {
		serverTickets?: Ticket[];
		serverMatches?: Match[];
		serverStats?: { total: number; won: number; lost: number; profit_loss: number };
		serverBankrolls?: Bankroll[];
		serverBatches?: TicketBatch[];
		serverTradingAccounts?: TradingAccount[];
		paperTradingEnabled?: boolean;
		handoff: TicketHandoff;
	} = $props();

	let tickets = $state<Ticket[]>([]);
	let matches = $state<Match[]>([]);
	let stats = $state({ total: 0, won: 0, lost: 0, profit_loss: 0 });
	let loading = $state(false);
	let error = $state('');
	let activeTab = $state('generate');
	let manualPlacementOpen = $state(false);
	let automationOpen = $state(false);
	let verificationAutomationOpen = $state(false);
	let bankrolls = $state<Bankroll[]>([]);
	let selectedBankrollId = $state<string>('');
	let hasRequestedInitialLoad = $state(false);
	let settlementChecking = $state(false);
	let settlementMessage = $state('');
	let resultsRefreshing = $state(false);
	let resultsRefreshMessage = $state('');
	let resultsRefreshConflictPolicy = $state('');
	let resultsRefreshPoll: ReturnType<typeof setInterval> | undefined;
	let resultsRefreshWatchJobId = $state<number | null>(null);
	let resultsRefreshPolicyJobId = $state<number | null>(null);
	let autoVerificationEnabled = $state(true);
	let autoVerificationIntervalNumber = $state('1');
	let autoVerificationIntervalUnit = $state('Hours');
	let scheduledJobs = $state<ScheduledJob[]>([]);
	let loadingScheduledJobs = $state(false);
	let scheduledJobsError = $state('');
	let savingScheduledJob = $state(false);
	let interactive = $state(false);
	let tradingAccounts = $state<TradingAccount[]>([]);
	let paperExecutions = $state<Record<number, TradingExecution>>({});
	let paperExecutionMessages = $state<Record<number, string>>({});
	let paperExecutingTicketId = $state<number | null>(null);
	let generatedDraftTotal = $state(0);
	let activeTicketTotal = $state(0);

	let betMatchId = $state('');
	let betMarket = $state('1x2');
	let betSelection = $state('home');
	let betOdds = $state('2.00');
	let betStake = $state('10');
	let betType = $state<TicketType>('single');
	let betError = $state('');
	let betSubmitting = $state(false);
	let generateTicketCount = $state('5');
	let generatePredictionRunId = $state('');
	let generateDifficulty = $state<'safe' | 'balanced' | 'aggressive'>('safe');
	let generateMarkets = $state<string[]>(['1x2']);
	let generateMinOdds = $state('1.20');
	let generateMaxOdds = $state('5.00');
	let accumulatorRiskAcknowledged = $state(false);
	let autoTicketGenerationEnabled = $state(true);
	let autoTicketIntervalNumber = $state('1');
	let autoTicketIntervalUnit = $state('Hours');
	let generatedBatchId = $state<number | null>(null);
	let generatedBatchRevision = $state(1);
	let generatedRiskPolicyVersion = $state<number | null>(null);
	let generatedRiskAssessment = $state<TicketRiskAssessment | null>(null);
	let generatedStakingSnapshot = $state<Record<string, unknown> | null>(null);
	let generatedSourceRunId = $state<number | null>(null);
	let generatedSourceRunIds = $state<number[]>([]);
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
	let swapPreviewOpen = $state(false);
	let historySwapPreviewOpen = $state(false);
	let generatedReviewAcknowledged = $state(false);
	let activatingGeneratedBatch = $state(false);
	let activationError = $state('');
	let discardConfirmOpen = $state(false);
	let discardingGeneratedBatch = $state(false);
	let discardCancelButton = $state<HTMLButtonElement | null>(null);
	let discardError = $state('');
	let generatedBatchLoading = $state(false);
	let generatedBatchLoadError = $state('');
	let generationReport = $state<TicketGenerationReport | null>(null);
	let ticketPreflight = $state<TicketPreflightResponse | null>(null);
	let ticketPreflightLoading = $state(false);
	let ticketPreflightError = $state('');
	let ticketPreflightSignature = $state('');
	let generatedLineage = $state<TicketBatchLineage | null>(null);
	let generatedLineageLoading = $state(false);
	let generatedLineageError = $state('');

	const statusBadge: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'default'> = {
		generated: 'warning',
		won: 'success',
		open: 'info',
		lost: 'danger',
		cashed_out: 'warning',
		void: 'default'
	};

	function restoreGeneratedDrafts(ticketSnapshot: Ticket[], batchSnapshot: TicketBatch[]): number | null {
		const draftTickets = ticketSnapshot.filter((ticket) => ticket.status === 'generated');
		const draftBatchIds = new Set(
			draftTickets
				.map((ticket) => ticket.batch_id)
				.filter((batchId): batchId is number => typeof batchId === 'number')
		);
		const currentBatchStillDraft =
			generatedBatchId !== null && draftBatchIds.has(generatedBatchId);
		const restoredBatchId = currentBatchStillDraft
			? generatedBatchId
			: [...batchSnapshot]
					.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
					.find((batch) => draftBatchIds.has(batch.id))?.id ?? null;

		if (restoredBatchId === null) {
			generatedBatchId = null;
			generatedBatchRevision = 1;
			generatedRiskPolicyVersion = null;
			generatedRiskAssessment = null;
			generatedStakingSnapshot = null;
			generatedSourceRunId = null;
			generatedSourceRunIds = [];
			generatedTickets = [];
			generationReport = null;
			generatedLineage = null;
			generatedLineageError = '';
			generatedBatchLoadError = '';
			discardConfirmOpen = false;
			discardError = '';
			return null;
		}

		const restoredBatch = batchSnapshot.find((batch) => batch.id === restoredBatchId) ?? null;
		generatedBatchId = restoredBatchId;
		generatedBatchRevision = restoredBatch?.revision ?? 1;
		generatedRiskPolicyVersion = restoredBatch?.risk_policy_version ?? null;
		generatedRiskAssessment = restoredBatch?.risk_assessment ?? null;
		generatedStakingSnapshot = restoredBatch?.staking_snapshot ?? null;
		generatedSourceRunId = restoredBatch?.source_prediction_run_id ?? null;
		generatedSourceRunIds =
			restoredBatch?.source_prediction_run_ids ??
			restoredBatch?.generation_report?.prediction_run_ids ??
			(generatedSourceRunId ? [generatedSourceRunId] : []);
		generatedTickets = draftTickets.filter((ticket) => ticket.batch_id === restoredBatchId);
		generationReport = restoredBatch?.generation_report ?? null;
		return restoredBatchId;
	}

	async function loadFullGeneratedBatch(batchId: number, options: { preserveReview?: boolean } = {}) {
		generatedBatchLoading = true;
		generatedBatchLoadError = '';
		activationError = '';
		try {
			const loadedTickets = await ticketsApi.getBatchTickets(batchId);
			const loadedIds = new Set(loadedTickets.map((ticket) => ticket.id));
			tickets = [...loadedTickets, ...tickets.filter((ticket) => !loadedIds.has(ticket.id))];
			const batch = batches.find((candidate) => candidate.id === batchId) ?? null;
			generatedBatchId = batchId;
			generatedBatchRevision = batch?.revision ?? 1;
			generatedRiskPolicyVersion = batch?.risk_policy_version ?? null;
			generatedRiskAssessment = batch?.risk_assessment ?? null;
			generatedStakingSnapshot = batch?.staking_snapshot ?? null;
			generatedSourceRunId = batch?.source_prediction_run_id ?? null;
			generatedSourceRunIds =
				batch?.source_prediction_run_ids ??
				batch?.generation_report?.prediction_run_ids ??
				(generatedSourceRunId ? [generatedSourceRunId] : []);
			generationReport = batch?.generation_report ?? null;
			generatedTickets = loadedTickets.filter((ticket) => ticket.status === 'generated');
			await loadGeneratedLineage(batchId);
			if (!options.preserveReview) generatedReviewAcknowledged = false;
			if (loadedTickets.length !== (batch?.tickets_count ?? 0)) {
				generatedBatchLoadError = `Lot incomplet: API-ul a returnat ${loadedTickets.length} din ${batch?.tickets_count ?? 0} bilete.`;
			} else if (generatedTickets.length !== loadedTickets.length) {
				generatedBatchLoadError = 'Lotul nu mai conține exclusiv bilete generate și nu poate fi aprobat la revizuire.';
			}
		} catch (err) {
			generatedTickets = [];
			generatedBatchLoadError =
				err instanceof ApiClientError ? err.message : 'Lotul complet nu a putut fi încărcat pentru revizuire.';
		} finally {
			generatedBatchLoading = false;
		}
	}

	async function loadGeneratedLineage(batchId: number) {
		generatedLineageLoading = true;
		generatedLineageError = '';
		try {
			generatedLineage = await ticketsApi.getBatchLineage(batchId);
		} catch (error) {
			generatedLineage = null;
			generatedLineageError = error instanceof ApiClientError
				? `Proveniența detaliată nu este disponibilă: ${error.message}`
				: 'Proveniența detaliată nu este disponibilă momentan.';
		} finally {
			generatedLineageLoading = false;
		}
	}

	function retryFullGeneratedBatch() {
		if (generatedBatchId !== null) void loadFullGeneratedBatch(generatedBatchId);
	}

	async function loadTickets(options: { preserveReview?: boolean } = {}) {
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
			const restoredBatchId = restoreGeneratedDrafts(t, fetchedBatches);
			if (restoredBatchId !== null) {
				await loadFullGeneratedBatch(restoredBatchId, {
					preserveReview: options.preserveReview
				});
			}
			if (!selectedBatchId && fetchedBatches.length > 0) {
				selectedBatchId = String(fetchedBatches[0].id);
			}
			if (!selectedBankrollId && b.length > 0) {
				selectedBankrollId = String(b[0].id);
			}
			error = '';
		} catch (err) {
			error = err instanceof ApiClientError ? err.message : 'Biletele nu au putut fi încărcate.';
		} finally {
			loading = false;
		}
	}

	async function refreshTicketTotals() {
		const [generatedPage, openPage, watchlistPage] = await Promise.all([
			ticketsApi.getTicketsPage({ status: 'generated', page: 1, per_page: 1 }),
			ticketsApi.getTicketsPage({ status: 'open', page: 1, per_page: 1 }),
			ticketsApi.getTicketsPage({ status: 'watchlist', page: 1, per_page: 1 })
		]);
		generatedDraftTotal = generatedPage.total;
		activeTicketTotal = openPage.total + watchlistPage.total;
	}

	async function pollVisibleTicketContext() {
		if (document.hidden) return;
		const focused = document.activeElement;
		if (focused?.matches('input, select, textarea, button, [contenteditable="true"]')) return;

		try {
			await refreshTicketTotals();
			if (activeTab === 'active') {
				const [openPage, watchlistPage, refreshedStats] = await Promise.all([
					ticketsApi.getTicketsPage({ status: 'open', page: 1, per_page: 100 }),
					ticketsApi.getTicketsPage({ status: 'watchlist', page: 1, per_page: 100 }),
					ticketsApi.getStats()
				]);
				const activeIds = new Set([...openPage.items, ...watchlistPage.items].map((ticket) => ticket.id));
				tickets = [
					...openPage.items,
					...watchlistPage.items,
					...tickets.filter(
						(ticket) => !activeIds.has(ticket.id) && !['open', 'watchlist'].includes(ticket.status)
					)
				];
				stats = refreshedStats;
			} else if (activeTab === 'history') {
				batches = await ticketsApi.getBatches();
				if (selectedBatchIdNumber !== null) await loadBatchTickets(selectedBatchIdNumber);
			} else if (activeTab === 'review' && generatedBatchId !== null) {
				batches = await ticketsApi.getBatches();
				await loadFullGeneratedBatch(generatedBatchId, { preserveReview: true });
			}
		} catch {
			// Background refresh is best-effort. Current SSR/client state remains visible.
		}
	}

	async function executePaperTicket(ticket: Ticket) {
		if (!paperTradingEnabled) return;
		const account = tradingAccounts.find((candidate) => candidate.enabled && candidate.mode === 'paper');
		if (!account) {
			paperExecutionMessages = { ...paperExecutionMessages, [ticket.id]: 'Creează mai întâi un cont de simulare activ în pagina Cont.' };
			return;
		}
		paperExecutingTicketId = ticket.id;
		paperExecutionMessages = { ...paperExecutionMessages, [ticket.id]: '' };
		try {
			const execution = await tradingApi.executePaperTicket(account.id, ticket.id, `ticket-${ticket.id}-paper-v1`);
			paperExecutions = { ...paperExecutions, [ticket.id]: execution };
			paperExecutionMessages = {
				...paperExecutionMessages,
				[ticket.id]: `${execution.status}: simulare BACK LIMIT ${execution.stake.toFixed(2)} @ ${execution.limit_price.toFixed(2)} (cotă persistată)`
			};
		} catch (err) {
			paperExecutionMessages = {
				...paperExecutionMessages,
				[ticket.id]: err instanceof ApiClientError ? err.message : 'Execuția simulată a eșuat.'
			};
		} finally {
			paperExecutingTicketId = null;
		}
	}

	async function fetchScheduledJobs() {
		loadingScheduledJobs = true;
		scheduledJobsError = '';
		try {
			scheduledJobs = await jobsApi.getScheduledJobs();
		} catch (err) {
			scheduledJobsError = err instanceof ApiClientError ? err.message : 'Automatizările de verificare nu au putut fi încărcate.';
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
			batchLoadError = err instanceof ApiClientError ? err.message : 'Biletele lotului selectat nu au putut fi încărcate.';
			batchTickets = [];
		} finally {
			batchTicketsLoading = false;
		}
	}

	async function onGeneratedBatchChange(event: Event) {
		const target = event.currentTarget as HTMLSelectElement | null;
		const batchId = Number.parseInt(target?.value ?? '', 10);
		if (!Number.isFinite(batchId) || batchId <= 0) return;
		activationError = '';
		generatedReviewAcknowledged = false;
		generatedBatchId = batchId;
		await loadFullGeneratedBatch(batchId);
	}

	function onBatchChange(event: Event) {
		const target = event.currentTarget as HTMLSelectElement | null;
		const batchId = Number.parseInt(target?.value ?? selectedBatchId, 10);
		if (!Number.isFinite(batchId) || batchId <= 0) {
			batchTickets = [];
			return;
		}
		void loadBatchTickets(batchId);
	}

	async function verifyResults() {
		settlementChecking = true;
		settlementMessage = '';
		try {
			const summary = await ticketsApi.settleDue();
			settlementMessage =
				summary.settled_tickets > 0
					? `${ticketCountLabel(summary.settled_tickets)} finalizate: ${summary.won_tickets} câștigate, ${summary.lost_tickets} pierdute, ${summary.void_tickets} anulate.`
					: `${ticketCountLabel(summary.checked_tickets)} active verificate; niciun bilet nu este încă pregătit pentru finalizare.`;
			await loadTickets();
		} catch (err) {
			settlementMessage = err instanceof ApiClientError ? err.message : 'Rezultatele biletelor nu au putut fi verificate.';
		} finally {
			settlementChecking = false;
		}
	}

	async function refreshFinalResults() {
		const matchIds = [...new Set(activeTickets.flatMap((ticket) => ticket.legs.map((leg) => leg.match_id)))];
		if (matchIds.length === 0) {
			resultsRefreshMessage = 'Nu există meciuri din bilete active care să necesite actualizare.';
			return;
		}

		resultsRefreshing = true;
		resultsRefreshMessage = '';
		resultsRefreshConflictPolicy = '';
		try {
			const job = await dataApi.refreshFinalResults(matchIds);
			resultsRefreshMessage = `Actualizarea rezultatelor a fost pusă în coadă ca job #${job.id}${job.queued_run_id ? ` (run #${job.queued_run_id})` : ''} pentru ${matchIds.length === 1 ? '1 meci' : `${matchIds.length} meciuri`}. Scorurile și biletele nu au fost modificate încă.`;
			resultsRefreshPolicyJobId = job.id;
			resultsRefreshConflictPolicy = finalScoreConflictPolicyMessage({ status: job.status });
			watchFinalResultsRefresh(job.id);
		} catch (err) {
			resultsRefreshMessage = err instanceof ApiClientError
				? `Actualizarea rezultatelor finale a eșuat: ${err.message}`
				: 'Actualizarea rezultatelor finale a eșuat. Niciun bilet nu a fost finalizat.';
		} finally {
			resultsRefreshing = false;
		}
	}

	async function refreshFinalResultsJobStatus(jobId: number) {
		try {
			const job = await dataApi.getJob(jobId);
			if (resultsRefreshWatchJobId !== jobId) return;
			if (job.status === 'completed') {
				resultsRefreshMessage = `Jobul de rezultate finale #${jobId} s-a încheiat. Verifică rezultatul înainte de finalizare; niciun bilet nu a fost finalizat automat.`;
				void loadFinalScoreConflictPolicy(jobId, job.status);
				stopFinalResultsRefreshWatch();
			} else if (job.status === 'failed' || job.status === 'cancelled') {
				resultsRefreshMessage = `Jobul de rezultate finale #${jobId} are status ${job.status}${job.error ? `: ${job.error}` : ''}. Niciun bilet nu a fost finalizat.`;
				resultsRefreshConflictPolicy = finalScoreConflictPolicyMessage({ status: job.status });
				stopFinalResultsRefreshWatch();
			}
		} catch {
			if (resultsRefreshWatchJobId !== jobId) return;
			resultsRefreshMessage = `Statusul jobului de rezultate finale #${jobId} nu a putut fi actualizat. Verifică istoricul joburilor înainte de finalizarea biletelor.`;
			stopFinalResultsRefreshWatch();
		}
	}

	async function loadFinalScoreConflictPolicy(jobId: number, status: string) {
		try {
			const logs = await dataApi.getJobLogs(jobId);
			if (resultsRefreshPolicyJobId !== jobId) return;
			resultsRefreshConflictPolicy = finalScoreConflictPolicyMessage({
				status,
				conflictCount: countFinalScoreConflicts(logs.items),
				logsAvailable: true
			});
		} catch {
			if (resultsRefreshPolicyJobId !== jobId) return;
			resultsRefreshConflictPolicy = finalScoreConflictPolicyMessage({ status, logsAvailable: false });
		}
	}

	function stopFinalResultsRefreshWatch() {
		if (resultsRefreshPoll) clearInterval(resultsRefreshPoll);
		resultsRefreshPoll = undefined;
		resultsRefreshWatchJobId = null;
	}

	function watchFinalResultsRefresh(jobId: number) {
		stopFinalResultsRefreshWatch();
		resultsRefreshWatchJobId = jobId;
		resultsRefreshPoll = setInterval(() => void refreshFinalResultsJobStatus(jobId), 3000);
		void refreshFinalResultsJobStatus(jobId);
	}

	async function toggleScheduledJob(jobId: number) {
		scheduledJobsError = '';
		try {
			const updated = await jobsApi.toggleJob(jobId);
			scheduledJobs = scheduledJobs.map((job) => (job.id === jobId ? updated : job));
		} catch (err) {
			scheduledJobsError =
				err instanceof ApiClientError ? err.message : 'Automatizarea de verificare nu a putut fi schimbată.';
		}
	}

	async function saveAutomaticVerificationAction() {
		savingScheduledJob = true;
		scheduledJobsError = '';
		try {
			const created = await jobsApi.createScheduledJob({
				name: `Verificare automată la fiecare ${autoVerificationIntervalNumber} ${autoVerificationIntervalUnit.toLowerCase()}`,
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
				err instanceof ApiClientError ? err.message : 'Automatizarea de verificare nu a putut fi salvată.';
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
				betError = 'Creează sau selectează un bankroll înainte de înregistrarea biletului.';
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
				activeTicketTotal += 1;
				betslip.clearLegs();
				activeTab = 'active';
				return;
			}

			if (!betMatchId || !betStake) {
				betError = 'Selectează un meci și introdu o miză.';
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
			activeTicketTotal += 1;
			activeTab = 'active';
		} catch (err) {
			betError = err instanceof ApiClientError ? err.message : 'Biletul manual nu a putut fi înregistrat.';
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

	function ticketFormatForDifficulty(): 'single' | 'double' | 'treble' {
		if (generateDifficulty === 'balanced') return 'double';
		if (generateDifficulty === 'aggressive') return 'treble';
		return 'single';
	}

	function selectedTicketMarkets(): Array<'1x2' | 'btts' | 'ou_2_5'> {
		return generateMarkets.filter(
			(market): market is '1x2' | 'btts' | 'ou_2_5' =>
				market === '1x2' || market === 'btts' || market === 'ou_2_5'
		);
	}

	function riskWarningCodes(assessment: TicketRiskAssessment | null): string[] {
		if (!assessment) return [];
		const direct = Array.isArray(assessment.warnings) ? assessment.warnings : [];
		const ticketAssessments = Array.isArray(assessment.tickets) ? assessment.tickets : [];
		const nested = ticketAssessments.flatMap((item) => {
			if (!item || typeof item !== 'object') return [];
			const warnings = (item as TicketRiskAssessment).warnings;
			return Array.isArray(warnings) ? warnings : [];
		});
		return [...new Set([...direct, ...nested].map((warning) => warning.code).filter(Boolean))];
	}

	function selectedPredictionRunId(): number | null | undefined {
		const value = generatePredictionRunId.trim();
		if (!value) return undefined;
		const runId = Number(value);
		return Number.isSafeInteger(runId) && runId > 0 ? runId : null;
	}

	function currentPreflightSignature(): string {
		return JSON.stringify({
			runIds: generationRunIds,
			predictionIds: handoff.candidateIds,
			bankrollId: selectedBankrollId,
			ticketFormat: ticketFormatForDifficulty(),
			accumulatorRiskAcknowledged,
			markets: [...generateMarkets].sort(),
			minOdds: generateMinOdds,
			maxOdds: generateMaxOdds
		});
	}

	async function checkTicketAvailability(): Promise<boolean> {
		if (ticketFormatForDifficulty() !== 'single' && !accumulatorRiskAcknowledged) {
			ticketPreflightError = 'Confirmă explicit riscul acumulatorului înainte de verificare.';
			return false;
		}
		const localValidation = ticketGenerationPreflight({
			runId: generatePredictionRunId,
			runIds: handoff.runIds,
			bankrollId: selectedBankrollId,
			ticketCount: generateTicketCount,
			markets: generateMarkets,
			minOdds: generateMinOdds,
			maxOdds: generateMaxOdds
		});
		if (!localValidation.valid || generationRunIds.length === 0) {
			ticketPreflightError = 'Completează configurația validă și sursa de predicții înainte de verificare.';
			return false;
		}

		ticketPreflightLoading = true;
		ticketPreflightError = '';
		try {
			const response = await ticketsApi.preflight({
				bankroll_id: Number(selectedBankrollId),
				run_ids: generationRunIds,
				prediction_ids: handoff.candidateIds.length > 0 ? handoff.candidateIds : undefined,
				market_types: selectedTicketMarkets(),
				min_odds: Number(generateMinOdds),
				max_odds: Number(generateMaxOdds),
				ticket_format: ticketFormatForDifficulty(),
				accumulator_risk_acknowledged: accumulatorRiskAcknowledged
			});
			ticketPreflight = response;
			ticketPreflightSignature = currentPreflightSignature();
			if (response.risk_assessment?.allowed === false) {
				ticketPreflightError = 'Politica de risc blochează configurația curentă. Verifică limitele și expunerea bankroll-ului.';
				return false;
			}
			const selectedRisk = response.risks.find((risk) => risk.difficulty === generateDifficulty);
			if (!selectedRisk?.can_generate) {
				ticketPreflightError = `Nivelul ${riskLabel(generateDifficulty)} nu poate fi generat cu selecția curentă. Verifică meciurile eligibile și excluderile.`;
				return false;
			}
			return true;
		} catch (error) {
			ticketPreflight = null;
			ticketPreflightError = error instanceof ApiClientError
				? error.message
				: 'Disponibilitatea nu a putut fi verificată.';
			return false;
		} finally {
			ticketPreflightLoading = false;
		}
	}

	function riskLabel(difficulty: string): string {
		return difficulty === 'safe' || difficulty === 'low'
			? 'Prudent'
			: difficulty === 'balanced' || difficulty === 'medium'
				? 'Echilibrat'
				: 'Agresiv';
	}

	function exclusionLabel(reason: string): string {
		return ({
			insufficient_unique_matches: 'meciuri unice insuficiente',
			no_eligible_candidates: 'niciun candidat eligibil',
			quality_ineligible: 'calitate/fiabilitate insuficientă',
			odds_outside_interval: 'cotă în afara intervalului',
			market_not_requested: 'piață nealeasă',
			match_started_or_finished: 'meci început sau finalizat',
			match_status_not_eligible: 'stare meci neeligibilă'
		} as Record<string, string>)[reason] ?? reason.replaceAll('_', ' ');
	}

	async function generateAutomaticTickets() {
		generatingTickets = true;
		generateError = '';
		generateMessage = '';
		swapMessage = '';
		const bankrollId = selectedBankrollId ? parseInt(selectedBankrollId, 10) : NaN;

		try {
			const preflight = ticketGenerationPreflight({
				runId: generatePredictionRunId,
				runIds: handoff.runIds,
				bankrollId: selectedBankrollId,
				ticketCount: generateTicketCount,
				markets: generateMarkets,
				minOdds: generateMinOdds,
				maxOdds: generateMaxOdds
			});
			if (!preflight.valid) {
				generateError = 'Verifică datele marcate înainte de generare.';
				return;
			}
			if (!(await checkTicketAvailability())) return;
			const runId = selectedPredictionRunId();
			if (runId === null) {
				generateError = 'Introdu un ID pozitiv și întreg pentru run-ul de predicție.';
				return;
			}
			if (!Number.isFinite(bankrollId) || bankrollId <= 0) {
				generateError = 'Creează sau selectează un bankroll înainte de generare.';
				return;
			}
			if (generateMarkets.length === 0) {
				generateError = 'Selectează cel puțin o piață.';
				return;
			}
			const response = await ticketsApi.generate({
				bankroll_id: bankrollId,
				run_ids: generationRunIds,
				prediction_ids: handoff.candidateIds.length > 0 ? handoff.candidateIds : undefined,
				ticket_count: parseInt(generateTicketCount, 10) || 1,
				difficulty: generateDifficulty,
				ticket_format: ticketFormatForDifficulty(),
				accumulator_risk_acknowledged: accumulatorRiskAcknowledged,
				market_types: selectedTicketMarkets(),
				min_odds: parseFloat(generateMinOdds) || 1.01,
				max_odds: parseFloat(generateMaxOdds) || 100
			});
			generatedBatchId = response.batch_id;
			generatedBatchRevision = response.revision;
			generatedRiskPolicyVersion = response.risk_policy_version;
			generatedRiskAssessment = response.risk_assessment;
			generatedStakingSnapshot = response.staking_snapshot;
			generatedSourceRunId = response.source_prediction_run_id ?? runId ?? null;
			generatedSourceRunIds = response.source_prediction_run_ids ?? generationRunIds;
			generatedTickets = response.tickets;
			generationReport = response.generation_report ?? null;
			generatedLineage = null;
			generatedLineageError = '';
			generatedReviewAcknowledged = false;
			activationError = '';
			tickets = [...response.tickets, ...tickets.filter((ticket) => !response.tickets.some((created) => created.id === ticket.id))];
			activeTab = 'review';
			generateMessage = `Lotul #${response.batch_id} a fost generat cu ${response.tickets.length} bilet${response.tickets.length === 1 ? '' : 'e'}. Revizuiește-l înainte de orice execuție.`;
			await loadTickets({ preserveReview: true });
		} catch (err) {
			generateError = err instanceof ApiClientError && err.statusCode === 428
				? 'Configurează mai întâi politica explicită de risc în Cont → Risk & limits.'
				: err instanceof ApiClientError ? err.message : 'Lotul de bilete nu a putut fi generat.';
		} finally {
			generatingTickets = false;
		}
	}

	async function saveAutomaticTicketGenerationAction() {
		savingScheduledJob = true;
		scheduledJobsError = '';
		try {
			const bankrollId = selectedBankrollId ? parseInt(selectedBankrollId, 10) : NaN;
			const runId = selectedPredictionRunId();
			if (runId === null) {
				scheduledJobsError = 'Introdu un ID pozitiv și întreg pentru run-ul de predicție.';
				return;
			}
			const created = await jobsApi.createScheduledJob({
				name: `Generare automată · ${generateDifficulty}`,
				task_type: 'generate_tickets',
				cron_expression: cronFromInterval(autoTicketIntervalNumber, autoTicketIntervalUnit),
				config: {
					source_page: 'tickets',
					area: 'tickets',
					bankroll_id: Number.isFinite(bankrollId) && bankrollId > 0 ? bankrollId : undefined,
					run_ids: generationRunIds,
					ticket_count: parseInt(generateTicketCount, 10) || 1,
					difficulty: generateDifficulty,
					ticket_format: ticketFormatForDifficulty(),
					accumulator_risk_acknowledged: accumulatorRiskAcknowledged,
					market_types: selectedTicketMarkets(),
					min_odds: parseFloat(generateMinOdds) || 1.01,
					max_odds: parseFloat(generateMaxOdds) || 100,
					prediction_ids: handoff.candidateIds.length > 0 ? handoff.candidateIds : undefined
				}
			});
			scheduledJobs = [created, ...scheduledJobs.filter((job) => job.id !== created.id)];
		} catch (err) {
			scheduledJobsError =
				err instanceof ApiClientError ? err.message : 'Automatizarea de generare nu a putut fi salvată.';
		} finally {
			savingScheduledJob = false;
		}
	}

	async function activateGeneratedTickets() {
		if (!generatedReviewAcknowledged || generatedBatchId === null || !generatedBatchState.complete) {
			activationError = 'Încarcă și verifică toate biletele din lot înainte de activare.';
			return;
		}
		activatingGeneratedBatch = true;
		activationError = '';
		try {
			const activation = await ticketsApi.activateBatch(generatedBatchId, {
				expected_revision: generatedBatchRevision,
				review_acknowledged: generatedReviewAcknowledged,
				accepted_warning_codes: riskWarningCodes(generatedRiskAssessment)
			});
			const activatedTickets = activation.tickets;
			const activatedById = new Map(activatedTickets.map((ticket) => [ticket.id, ticket]));
			tickets = tickets.map((ticket) => activatedById.get(ticket.id) ?? ticket);
			generatedTickets = [];
			generatedBatchId = null;
			generatedBatchRevision = 1;
			generatedRiskPolicyVersion = null;
			generatedRiskAssessment = null;
			generatedStakingSnapshot = null;
			generatedSourceRunId = null;
			generatedSourceRunIds = [];
			generationReport = null;
			generatedLineage = null;
			generatedLineageError = '';
			generatedReviewAcknowledged = false;
			activeTab = 'active';
			settlementMessage = `${activatedTickets.length} bilet${activatedTickets.length === 1 ? '' : 'e'} activate după revizuire; miză debitată ${activation.debited_amount.toFixed(2)}.`;
			await Promise.all([loadTickets(), refreshTicketTotals()]);
		} catch (err) {
			if (err instanceof ApiClientError && err.statusCode === 409 && generatedBatchId !== null) {
				try {
					const refreshed = await ticketsApi.refreshBatch(generatedBatchId, generatedBatchRevision);
					generatedBatchRevision = refreshed.revision;
					generatedTickets = refreshed.tickets;
					generationReport = refreshed.generation_report;
					generatedRiskAssessment = refreshed.risk_assessment;
					generatedStakingSnapshot = refreshed.staking_snapshot;
					generatedReviewAcknowledged = false;
					const refreshedById = new Map(refreshed.tickets.map((ticket) => [ticket.id, ticket]));
					tickets = tickets.map((ticket) => refreshedById.get(ticket.id) ?? ticket);
					activationError = 'Draftul s-a schimbat între revizuire și activare. Cotele și riscul au fost revalidate; verifică din nou revizia actualizată.';
				} catch (refreshError) {
					activationError = refreshError instanceof ApiClientError
						? refreshError.message
						: 'Draftul nu a putut fi revalidat după conflict.';
				}
			} else {
				activationError =
					err instanceof ApiClientError ? err.message : 'Lotul nu a putut fi activat după revizuire.';
			}
		} finally {
			activatingGeneratedBatch = false;
		}
	}

	async function discardGeneratedDraft() {
		if (generatedBatchId === null || discardingGeneratedBatch) return;

		const discardedBatchId = generatedBatchId;
		discardingGeneratedBatch = true;
		discardError = '';
		activationError = '';
		try {
			const result = await ticketsApi.discardDraftBatch(discardedBatchId);
			tickets = tickets.filter((ticket) => ticket.batch_id !== discardedBatchId);
			batches = batches.filter((batch) => batch.id !== discardedBatchId);
			generatedBatchId = null;
			generatedBatchRevision = 1;
			generatedRiskPolicyVersion = null;
			generatedRiskAssessment = null;
			generatedStakingSnapshot = null;
			generatedSourceRunId = null;
			generatedSourceRunIds = [];
			generatedTickets = [];
			generationReport = null;
			generatedLineage = null;
			generatedLineageError = '';
			generatedReviewAcknowledged = false;
			discardConfirmOpen = false;
			activeTab = 'generate';
			generateMessage = `Lotul draft #${result.batch_id} a fost eliminat (${ticketCountLabel(result.discarded_tickets)}). Nu a fost activat și nu a debitat miza.`;
			await loadTickets();
		} catch (err) {
			discardError =
				err instanceof ApiClientError ? err.message : 'Lotul draft nu a putut fi eliminat în siguranță.';
		} finally {
			discardingGeneratedBatch = false;
		}
	}

	function generatedLegOptions(): { value: string; label: string }[] {
		return generatedTickets.flatMap((ticket) =>
			ticket.legs.map((leg) => ({
				value: `${ticket.id}:${leg.id}`,
				label: `Bilet #${ticket.reference ?? ticket.id} · ${leg.match?.home_team ?? 'Meci'} vs ${leg.match?.away_team ?? '?'} · ${leg.market}/${leg.selection}`
			}))
		);
	}

	function batchLegOptions(usableTickets: Ticket[]): { value: string; label: string }[] {
		return usableTickets.flatMap((ticket) =>
			ticket.legs.map((leg) => ({
				value: `${ticket.id}:${leg.id}`,
				label: `Bilet #${ticket.reference ?? ticket.id} · ${leg.match?.home_team ?? 'Meci'} vs ${leg.match?.away_team ?? '?'} · ${leg.market}/${leg.selection}`
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

	function lineageModelProbability(leg: TicketLineageLeg): number | null {
		const model = leg.prediction?.quality_report?.model;
		const pick = model?.pick;
		const probability = pick ? model?.probabilities?.[pick] : undefined;
		return typeof probability === 'number' && Number.isFinite(probability) ? probability * 100 : null;
	}

	function ticketProfitLoss(ticket: Ticket): number | null {
		if (!['won', 'lost', 'cashed_out', 'void'].includes(ticket.status)) return null;
		return (ticket.actual_return ?? 0) - ticket.stake;
	}

	function runLineageLabel(runIds: number[]): string {
		return runIds.length > 0 ? runIds.map((runId) => `run #${runId}`).join(', ') : 'sursă indisponibilă';
	}

	function matchStatusText(match: Partial<Match> | null | undefined): string {
		if (!match) return 'status indisponibil';
		const status = match.status || 'indisponibil';
		if (status === 'live' && match.start_time) {
			const startAt = new Date(match.start_time);
			if (!Number.isNaN(startAt.getTime())) {
				const minutes = Math.floor((Date.now() - startAt.getTime()) / 60000);
				return `În direct (~${Math.max(minutes, 0)} min)`;
			}
		}
		if (status === 'finished') return 'Finalizat';
		if (status === 'scheduled' && match.start_time) {
			const startAt = new Date(match.start_time);
			if (!Number.isNaN(startAt.getTime())) {
				return `Programat ${startAt.toLocaleString('ro-RO')}`;
			}
		}
		if (status === 'cancelled') return 'Anulat';
		if (status === 'postponed') return 'Amânat';
		return status;
	}

	async function swapGeneratedLegs() {
		if (generatedBatchId === null) {
			swapMessage = 'Generează un lot înainte de schimbarea selecțiilor.';
			return;
		}
		const source = parseSwapLeg(sourceSwapLeg);
		const target = parseSwapLeg(targetSwapLeg);
		if (!source || !target) {
			swapMessage = 'Selectează o selecție sursă și una destinație.';
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
			swapPreviewOpen = false;
			generatedReviewAcknowledged = false;
			swapMessage = 'Schimbul a fost salvat, iar cotele biletelor au fost recalculate.';
		} catch (err) {
			swapMessage = err instanceof ApiClientError ? err.message : 'Selecțiile nu au putut fi schimbate.';
		} finally {
			swappingLegs = false;
		}
	}

	async function swapBatchLegs() {
		const batchId = Number.parseInt(selectedBatchId, 10);
		if (!Number.isFinite(batchId) || batchId <= 0) {
			historySwapMessage = 'Selectează un lot generat pentru schimbarea selecțiilor.';
			return;
		}
		const source = parseSwapLeg(historySourceSwapLeg);
		const target = parseSwapLeg(historyTargetSwapLeg);
		if (!source || !target) {
			historySwapMessage = 'Selectează o selecție sursă și una destinație.';
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
			historySwapPreviewOpen = false;
			historySwapMessage = 'Schimbul a fost salvat, iar cotele biletelor au fost recalculate.';
		} catch (err) {
			historySwapMessage = err instanceof ApiClientError ? err.message : 'Selecțiile nu au putut fi schimbate.';
		} finally {
			historySwappingLegs = false;
		}
	}

	onMount(() => {
		interactive = true;
		if ($betslip.legs.length > 0) {
			activeTab = 'generate';
			manualPlacementOpen = true;
		}
		tickets = serverTickets ?? [];
		generatedDraftTotal = tickets.filter((ticket) => ticket.status === 'generated').length;
		activeTicketTotal = tickets.filter((ticket) => ['open', 'watchlist'].includes(ticket.status)).length;
		matches = serverMatches ?? [];
		stats = serverStats ?? { total: 0, won: 0, lost: 0, profit_loss: 0 };
		bankrolls = serverBankrolls ?? [];
		batches = serverBatches ?? [];
		tradingAccounts = paperTradingEnabled ? (serverTradingAccounts ?? []) : [];
		const restoredBatchId = restoreGeneratedDrafts(tickets, batches);
		if (restoredBatchId !== null) void loadFullGeneratedBatch(restoredBatchId);
		if (handoff.runIds[0]) {
			generatePredictionRunId = String(handoff.runIds[0]);
		} else if (!generatePredictionRunId && generatedSourceRunId) {
			generatePredictionRunId = String(generatedSourceRunId);
		}
		if (!selectedBankrollId && serverBankrolls?.[0]) {
			selectedBankrollId = String(serverBankrolls[0].id);
		}
		if (!selectedBatchId && serverBatches?.[0]) {
			selectedBatchId = String(serverBatches[0].id);
		}
		if (selectedBatchId) {
			void loadBatchTickets(Number.parseInt(selectedBatchId, 10));
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
		void refreshTicketTotals().catch(() => undefined);
		const pollInterval = setInterval(() => void pollVisibleTicketContext(), 30000);
		return () => {
			clearInterval(pollInterval);
			stopFinalResultsRefreshWatch();
			resultsRefreshPolicyJobId = null;
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
	const selectedBatchGenerationReport = $derived(
		selectedBatch?.generation_report ?? null
	);
	const selectedBatchSourceRuns = $derived.by(() => {
		const reported = selectedBatch?.source_prediction_run_ids ?? selectedBatchGenerationReport?.prediction_run_ids ?? [];
		const fallback = selectedBatch?.source_prediction_run_id ? [selectedBatch.source_prediction_run_id] : [];
		return [...new Set(reported.length > 0 ? reported : fallback)].filter((runId) => runId > 0);
	});
	const selectedBatchTickets = $derived.by(() => {
		if (selectedBatchIdNumber === null) return [];
		const fromBatch = batchTickets.filter((ticket) => ticket.batch_id === selectedBatchIdNumber);
		if (fromBatch.length > 0) return fromBatch;
		return tickets.filter((ticket) => ticket.batch_id === selectedBatchIdNumber);
	});
	const selectedBatchCompleted = $derived(
		selectedBatchTickets.filter((ticket) =>
			['won', 'lost', 'cashed_out', 'void'].includes(ticket.status)
		).length
	);
	const selectedBatchProgress = $derived(
		selectedBatch?.tickets_count
			? `${selectedBatchCompleted}/${selectedBatch.tickets_count} finalizate`
			: `${selectedBatchCompleted}/${selectedBatchTickets.length} finalizate`
	);
	const batchOptions = $derived(
		batches.map((batch) => ({
			value: String(batch.id),
			label: `#${batch.id}${batch.name ? ` · ${batch.name}` : ''} (${ticketCountLabel(batch.tickets_count)})`
		}))
	);

	const generatedDraftTickets = $derived(tickets.filter((ticket) => ticket.status === 'generated'));
	const generatedDraftBatchOptions = $derived.by(() => {
		const ids = new Set(
			generatedDraftTickets
				.map((ticket) => ticket.batch_id)
				.filter((batchId): batchId is number => typeof batchId === 'number')
		);
		return batches
			.filter((batch) => ids.has(batch.id))
			.map((batch) => ({
				value: String(batch.id),
				label: `Lot generat #${batch.id} · ${ticketCountLabel(batch.tickets_count)} · run #${batch.source_prediction_run_id ?? 'indisponibil'}`
			}));
	});
	const generatedBatchExpectedCount = $derived(
		batches.find((batch) => batch.id === generatedBatchId)?.tickets_count ?? 0
	);
	const generatedBatchState = $derived(
		generatedBatchLoadState({
			expectedCount: generatedBatchExpectedCount,
			tickets: generatedTickets,
			loading: generatedBatchLoading
		})
	);
	const generatedTicketProbabilityRows = $derived.by(() =>
		generatedTickets.map((ticket) => ({
			id: ticket.id,
			label: `Bilet #${ticket.reference ?? ticket.id}`,
			probability:
				ticket.total_odds > 1 && Number.isFinite(ticket.total_odds)
					? 1 / ticket.total_odds
					: null,
			odds: ticket.total_odds,
			legs: ticket.legs.length,
			source: 'Probabilitate implicită din cota totală a biletului'
		})));
	const generatedUniqueMatches = $derived(
		new Set(generatedTickets.flatMap((ticket) => ticket.legs.map((leg) => leg.match_id))).size
	);
	const activeTickets = $derived(
		tickets.filter((ticket) => ticket.status === 'open' || ticket.status === 'watchlist')
	);
	const voidTickets = $derived(tickets.filter((ticket) => ticket.status === 'void').length);
	const winRate = $derived(
		stats.won + stats.lost > 0 ? (stats.won / (stats.won + stats.lost)) * 100 : 0
	);
	const selectedRunId = $derived(selectedPredictionRunId());
	const generationRunIds = $derived(
		handoff.runIds.length > 0 ? handoff.runIds : selectedRunId ? [selectedRunId] : []
	);
	const generationPreflight = $derived(
		ticketGenerationPreflight({
			runId: generatePredictionRunId,
			runIds: handoff.runIds,
			bankrollId: selectedBankrollId,
			ticketCount: generateTicketCount,
			markets: generateMarkets,
			minOdds: generateMinOdds,
			maxOdds: generateMaxOdds
		})
	);
	const generatedWarningCodes = $derived(riskWarningCodes(generatedRiskAssessment));
	const ticketPreflightIsCurrent = $derived(
		ticketPreflight !== null && ticketPreflightSignature === currentPreflightSignature()
	);
	const canonicalPreflightRisks = $derived(
		ticketPreflight?.risks.filter((risk) => risk.difficulty === risk.tier) ?? []
	);
	const generationCta = $derived(
		generationRunIds.length > 0
			? `Generează ${ticketCountLabel(Number(generateTicketCount) || 0)} din ${generationRunIds.length === 1 ? `run #${generationRunIds[0]}` : `${generationRunIds.length} run-uri`}`
			: `Selectează run-ul pentru ${ticketCountLabel(Number(generateTicketCount) || 0)}`
	);
	const analyzeHref = $derived.by(() => {
		const runIds =
			handoff.runIds.length > 0
				? handoff.runIds
				: generatedSourceRunIds.length > 0
					? generatedSourceRunIds
					: selectedBatchSourceRuns;
		const candidateIds =
			handoff.candidateIds.length > 0
				? handoff.candidateIds
				: generatedLineage
					? [...new Set(
							generatedLineage.tickets
								.flatMap((ticket) => ticket.legs.map((leg) => leg.model_prediction_id))
								.filter((id): id is number => typeof id === 'number' && id > 0)
						)]
					: [];
		const datasetId =
			handoff.datasetId ??
			generationReport?.source_dataset_id ??
			selectedBatchGenerationReport?.source_dataset_id ??
			null;

		return analyzeReturnHref({
			source: handoff.source,
			datasetId,
			runIds,
			candidateIds
		});
	});
	const verificationAction = $derived(
		verificationActionState({
			settlementChecking,
			resultsRefreshing,
			watchingResultsRefresh: resultsRefreshWatchJobId !== null
		})
	);
	const verificationActionLabel = $derived(
		settlementChecking
			? 'Se verifică și se finalizează...'
			: resultsRefreshing
				? 'Se actualizează rezultatele finale...'
				: resultsRefreshWatchJobId !== null
					? 'Se așteaptă actualizarea rezultatelor...'
					: 'Verifică și finalizează'
	);
	const automaticVerificationJobs = $derived(scheduledJobsForArea(scheduledJobs, 'verification'));
	const automaticTicketJobs = $derived(scheduledJobsForArea(scheduledJobs, 'tickets'));
	const tabs = $derived([
		{ id: 'generate', label: 'Generează', ariaLabel: 'Generează bilete', count: $betslip.legs.length || undefined },
		{ id: 'review', label: 'Revizuiește lotul', count: generatedDraftTotal || undefined },
		{ id: 'active', label: 'Active', count: activeTicketTotal },
		{ id: 'history', label: 'Istoric', count: batches.length }
	]);
	const matchOptions = $derived(
		matches.map((m) => ({ value: String(m.id), label: `${m.home_team} vs ${m.away_team}` }))
	);

	function swapPreview(
		usableTickets: Ticket[],
		sourceValue: string,
		targetValue: string
	): { sourceLabel: string; targetLabel: string; sourceOdds: number; targetOdds: number } | null {
		const source = parseSwapLeg(sourceValue);
		const target = parseSwapLeg(targetValue);
		if (!source || !target || source.ticketId === target.ticketId || source.legId === target.legId) return null;
		const sourceTicket = usableTickets.find((ticket) => ticket.id === source.ticketId);
		const targetTicket = usableTickets.find((ticket) => ticket.id === target.ticketId);
		const sourceLeg = sourceTicket?.legs.find((leg) => leg.id === source.legId);
		const targetLeg = targetTicket?.legs.find((leg) => leg.id === target.legId);
		if (!sourceTicket || !targetTicket || !sourceLeg || !targetLeg) return null;
		return {
			sourceLabel: `#${sourceTicket.reference ?? sourceTicket.id}: x${sourceTicket.total_odds.toFixed(2)} → x${((sourceTicket.total_odds / sourceLeg.odds) * targetLeg.odds).toFixed(2)}`,
			targetLabel: `#${targetTicket.reference ?? targetTicket.id}: x${targetTicket.total_odds.toFixed(2)} → x${((targetTicket.total_odds / targetLeg.odds) * sourceLeg.odds).toFixed(2)}`,
			sourceOdds: sourceLeg.odds,
			targetOdds: targetLeg.odds
		};
	}

	const generatedSwapPreview = $derived(
		swapPreview(generatedTickets, sourceSwapLeg, targetSwapLeg)
	);
	const historySwapPreview = $derived(
		swapPreview(selectedBatchTickets, historySourceSwapLeg, historyTargetSwapLeg)
	);
</script>

<div class="min-w-0 space-y-5" data-testid="tickets-panel" data-interactive={interactive ? 'true' : 'false'}>
	{#if loading && tickets.length === 0}
		<Loading message="Se încarcă biletele..." />
	{:else if error}
		<div class="border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive" role="alert">{error}</div>
		<Button onclick={() => loadTickets()}>Reîncearcă</Button>
	{/if}

	<section class="border border-border bg-card p-4" aria-labelledby="tickets-source-heading">
		<div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
			<div class="min-w-0 space-y-2">
				<div class="flex flex-wrap items-center gap-2">
					<Badge variant={handoff.runIds.length > 0 ? 'success' : 'warning'}>
						{handoff.runIds.length > 0 ? 'Sursă pregătită' : 'Sursă necesară'}
					</Badge>
					{#if handoff.source === 'analyze'}<Badge variant="info">Din Analiză</Badge>{/if}
				</div>
				<h2 id="tickets-source-heading" class="text-base font-semibold text-foreground">Lineage pentru lotul următor</h2>
				{#if handoff.runIds.length > 0}
					<p class="text-sm text-muted-foreground">
						Ai transferat {handoff.runIds.length} run{handoff.runIds.length === 1 ? '' : '-uri'} de predicție
						{handoff.datasetId !== null ? ` din setul de date #${handoff.datasetId}` : ''}.
					</p>
					<div data-testid="tickets-selected-runs" class="flex max-w-full flex-wrap gap-2 font-mono text-sm">
						{#each handoff.runIds as runId (runId)}<span class="border border-border bg-muted/30 px-2 py-1">run #{runId}</span>{/each}
						{#if handoff.candidateIds.length > 0}<span class="border border-border bg-muted/30 px-2 py-1">{handoff.candidateIds.length} candidați selectați</span>{/if}
					</div>
					{#if handoff.runIds.length > 1}
						<p class="text-xs text-football-green">Lotul va combina candidații eligibili din toate run-urile transferate, păstrând lineage-ul fiecărei predicții.</p>
					{/if}
				{:else}
					<p class="text-sm text-muted-foreground">Alege explicit un run de predicție. Nu vom folosi automat un run „recent” fără lineage.</p>
				{/if}
			</div>
			<a href={analyzeHref} class="inline-flex min-h-11 shrink-0 items-center justify-center border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-muted">
				{handoff.source === 'analyze' ? 'Înapoi la analiza filtrată' : 'Deschide Analiză'}
			</a>
		</div>
	</section>

	<section aria-labelledby="ticket-summary-heading" class="space-y-2">
		<h2 id="ticket-summary-heading" class="sr-only">Rezumatul biletelor</h2>
		<div class="grid grid-cols-2 gap-2 lg:grid-cols-4">
			<Card class="p-3"><p class="text-xs text-muted-foreground">De revizuit</p><p class="mt-1 font-mono text-xl font-bold text-football-gold">{generatedDraftTotal}</p></Card>
			<Card class="p-3"><p class="text-xs text-muted-foreground">Active</p><p class="mt-1 font-mono text-xl font-bold text-foreground">{activeTicketTotal}</p></Card>
			<Card class="p-3"><p class="text-xs text-muted-foreground">Finalizate</p><p class="mt-1 font-mono text-xl font-bold text-foreground">{stats.won + stats.lost + voidTickets}</p></Card>
			<Card class="p-3"><p class="text-xs text-muted-foreground">Profit / pierdere</p><p class="mt-1 font-mono text-xl font-bold {stats.profit_loss >= 0 ? 'text-football-green' : 'text-destructive'}">{stats.profit_loss > 0 ? '+' : ''}{stats.profit_loss.toFixed(2)}</p></Card>
		</div>
		<details class="border border-border bg-card">
			<summary class="flex min-h-11 cursor-pointer items-center justify-between gap-3 px-3 py-2 text-sm font-medium text-foreground"><span>Vezi statisticile de rezultat</span><span class="font-mono text-xs text-muted-foreground">{stats.total} total · {winRate.toFixed(1)}%</span></summary>
			<div class="grid grid-cols-2 gap-px border-t border-border bg-border sm:grid-cols-4">
				<div class="bg-card p-3"><p class="text-xs text-muted-foreground">Câștigate</p><p class="mt-1 font-mono text-lg text-football-green">{stats.won}</p></div>
				<div class="bg-card p-3"><p class="text-xs text-muted-foreground">Pierdute</p><p class="mt-1 font-mono text-lg text-destructive">{stats.lost}</p></div>
				<div class="bg-card p-3"><p class="text-xs text-muted-foreground">Anulate</p><p class="mt-1 font-mono text-lg text-foreground">{voidTickets}</p></div>
				<div class="bg-card p-3"><p class="text-xs text-muted-foreground">Rată de câștig</p><p class="mt-1 font-mono text-lg text-foreground">{winRate.toFixed(1)}%</p></div>
			</div>
		</details>
	</section>

	<Tabs bind:activeTab {tabs}>
		{#if activeTab === 'generate'}
			<div class="space-y-5 pt-5">
				<Card variant="active" class="p-4">
					<div class="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
						<div>
							<p class="text-xs font-semibold uppercase tracking-[0.16em] text-football-green">Generare automată</p>
							<h2 class="mt-1 text-lg font-semibold text-foreground">Configurează lotul</h2>
							<p class="mt-1 max-w-2xl text-sm text-muted-foreground">
								{handoff.candidateIds.length > 0
									? `Generarea trimite exact cele ${handoff.candidateIds.length} predicții selectate; backendul verifică apartenența lor la toate run-urile sursă.`
									: 'Generarea folosește toți candidații eligibili persistați din run-urile sursă.'}
								Nu plasează ordine externe.
							</p>
						</div>
						<Badge variant="warning">Revizuire obligatorie</Badge>
					</div>

					{#if generateError}<div class="mb-4 border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{generateError}</div>{/if}
					{#if generateMessage}<div class="mb-4 border border-football-green/30 bg-football-green/10 p-3 text-sm text-football-green" role="status">{generateMessage}</div>{/if}

					<div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
						{#if handoff.runIds.length > 1}
							<div class="space-y-1.5"><p class="text-sm font-medium text-foreground">Run-uri de predicție sursă</p><div class="flex min-h-10 flex-wrap items-center gap-2 border border-input bg-background px-3 py-2 font-mono text-xs">{#each handoff.runIds as runId (runId)}<span>#{runId}</span>{/each}</div></div>
						{:else if handoff.runIds.length > 0}
							<Select class="min-h-11" label="Run de predicție sursă" name="ticket-source-run" bind:value={generatePredictionRunId} options={handoff.runIds.map((runId) => ({ value: String(runId), label: `Run #${runId}` }))} />
						{:else}
							<Input class="min-h-11" label="Run de predicție sursă" name="ticket-source-run" type="number" min="1" step="1" bind:value={generatePredictionRunId} error={generationPreflight.errors.runId} />
						{/if}
						<Select class="min-h-11" label="Bankroll / cont" name="ticket-bankroll" bind:value={selectedBankrollId} options={bankrolls.map((bankroll) => ({ value: String(bankroll.id), label: `${bankroll.name} · ${bankroll.currency} ${bankroll.balance.toFixed(2)}` }))} placeholder="Selectează bankroll..." />
						<Input class="min-h-11" label="Număr de bilete" name="ticket-count" type="number" min="1" max="50" bind:value={generateTicketCount} error={generationPreflight.errors.ticketCount} />
						<div class="space-y-1.5">
							<label for="ticket-difficulty" class="text-sm font-medium leading-none">Siguranță / dificultate</label>
							<select id="ticket-difficulty" name="ticket-difficulty" class="touch-control flex min-h-11 w-full border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring" value={generateDifficulty} onchange={(event) => { generateDifficulty = event.currentTarget.value as 'safe' | 'balanced' | 'aggressive'; accumulatorRiskAcknowledged = false; }}>
								<option value="safe">Single · implicit</option>
								<option value="balanced">Double · risc suplimentar</option>
								<option value="aggressive">Treble · risc ridicat</option>
							</select>
						</div>
						<Input class="min-h-11" label="Cotă minimă" name="ticket-min-odds" type="number" min="1.01" step="0.01" bind:value={generateMinOdds} error={generationPreflight.errors.minOdds} />
						<Input class="min-h-11" label="Cotă maximă" name="ticket-max-odds" type="number" min="1.01" step="0.01" bind:value={generateMaxOdds} error={generationPreflight.errors.maxOdds} />
						<div class="border border-border bg-muted/20 p-3 text-sm"><p class="font-medium text-foreground">Miză calculată server-side</p><p class="mt-1 text-xs text-muted-foreground">Politica bankroll-ului stabilește miza și impune hard caps de 5% per bilet și 20% expunere deschisă.</p></div>
					</div>

					{#if generateDifficulty !== 'safe'}
						<label class="mt-4 flex min-h-11 items-start gap-3 border border-football-gold/40 bg-football-gold/10 p-3 text-sm text-foreground">
							<input type="checkbox" class="mt-0.5 size-5 accent-football-gold" bind:checked={accumulatorRiskAcknowledged} />
							<span><strong>Confirm riscul acumulatorului.</strong> Fiecare selecție trebuie să aibă valoare individuală, iar miza rămâne flat și plafonată.</span>
						</label>
					{/if}

					{#if bankrolls.length === 0}
						<div class="mt-4 border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">Nu există bankroll disponibil. <a class="font-semibold underline" href="/account">Creează unul în Cont</a> înainte de generare.</div>
					{:else if generationPreflight.errors.bankrollId}
						<p class="mt-2 text-sm font-medium text-destructive">{generationPreflight.errors.bankrollId}</p>
					{/if}

					<fieldset class="mt-5 space-y-2">
						<legend class="text-sm font-medium text-foreground">Piețe incluse</legend>
						<div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
							{#each [{ id: '1x2', label: '1X2 · rezultat' }, { id: 'btts', label: 'Ambele marchează' }, { id: 'ou_2_5', label: 'Peste/Sub 2.5' }] as market (market.id)}
								<label class="flex min-h-11 items-center gap-3 border border-border bg-muted/20 px-3 py-2 text-sm text-foreground hover:bg-muted/40">
									<input type="checkbox" class="h-4 w-4 accent-football-green" checked={generateMarkets.includes(market.id)} onchange={() => toggleGenerateMarket(market.id)} />
									<span>{market.label}</span>
								</label>
							{/each}
						</div>
						{#if generationPreflight.errors.markets}<p class="text-sm font-medium text-destructive">{generationPreflight.errors.markets}</p>{/if}
					</fieldset>

					<div class="mt-5 grid gap-3 border border-border bg-muted/20 p-4 sm:grid-cols-3">
						<div><p class="text-xs uppercase tracking-wide text-muted-foreground">Sursă</p><p class="mt-1 font-mono text-sm text-foreground">{generationRunIds.length > 0 ? generationRunIds.map((runId) => `#${runId}`).join(', ') : 'lipsește'}</p></div>
						<div><p class="text-xs uppercase tracking-wide text-muted-foreground">Selecție predicții</p><p class="mt-1 font-mono text-sm text-foreground">{handoff.candidateIds.length > 0 ? `subset exact · ${handoff.candidateIds.length} ID-uri` : 'toți candidații eligibili din run'}</p></div>
						<div><p class="text-xs uppercase tracking-wide text-muted-foreground">Excluderi</p><p class="mt-1 text-sm text-muted-foreground">Validate de backend la generare</p></div>
					</div>

					<section class="mt-5 border border-border bg-background p-4" aria-labelledby="ticket-preflight-heading">
						<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
							<div>
								<h3 id="ticket-preflight-heading" class="font-semibold text-foreground">Verificare înainte de generare</h3>
								<p class="mt-1 max-w-2xl text-sm leading-5 text-muted-foreground">Backendul aplică aceleași reguli ca generarea și arată dacă există suficiente predicții și meciuri unice pentru 1, 2 sau 3 selecții.</p>
							</div>
							<Button type="button" variant="secondary" class="min-h-11 shrink-0" onclick={() => void checkTicketAvailability()} disabled={ticketPreflightLoading || !generationPreflight.valid}>
								{ticketPreflightLoading ? 'Se verifică...' : 'Verifică disponibilitatea'}
							</Button>
						</div>

						{#if ticketPreflightError}<p class="mt-3 border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{ticketPreflightError}</p>{/if}
						{#if ticketPreflight && !ticketPreflightIsCurrent}<p class="mt-3 border border-football-gold/30 bg-football-gold/10 p-3 text-sm text-foreground">Configurația s-a schimbat. Rulează din nou verificarea pentru rezultate actuale.</p>{/if}

						{#if ticketPreflight}
							<div class="mt-4 grid gap-2 sm:grid-cols-3" aria-label="Disponibilitate pe niveluri de risc">
								{#each canonicalPreflightRisks as risk (risk.difficulty)}
									<article class={`border p-3 ${risk.can_generate ? 'border-football-green/40 bg-football-green/5' : 'border-border bg-muted/20'}`}>
										<div class="flex items-center justify-between gap-2"><h4 class="font-medium text-foreground">{riskLabel(risk.difficulty)}</h4><Badge variant={risk.can_generate ? 'success' : 'warning'}>{risk.can_generate ? 'Disponibil' : 'Blocat'}</Badge></div>
										<p class="mt-2 font-mono text-sm text-foreground">{risk.required_legs} {risk.required_legs === 1 ? 'meci' : 'meciuri'} / bilet</p>
										<p class="mt-1 text-xs leading-5 text-muted-foreground">{risk.eligible_candidates} predicții eligibile · {risk.eligible_unique_matches} meciuri unice</p>
									</article>
								{/each}
							</div>
							<div class="mt-3 grid gap-3 border-t border-border pt-3 text-sm sm:grid-cols-3">
								<div><p class="text-xs uppercase tracking-wide text-muted-foreground">Scanate</p><p class="mt-1 font-mono text-foreground">{ticketPreflight.scanned_predictions}</p></div>
								<div><p class="text-xs uppercase tracking-wide text-muted-foreground">Eligibile</p><p class="mt-1 font-mono text-football-green">{ticketPreflight.eligible_candidates}</p></div>
								<div><p class="text-xs uppercase tracking-wide text-muted-foreground">Excluse</p><p class="mt-1 font-mono text-football-gold">{ticketPreflight.excluded_predictions}</p></div>
							</div>
							{#if Object.keys(ticketPreflight.excluded_by_reason).length > 0}
								<details class="mt-3 border border-border bg-muted/10">
									<summary class="min-h-11 cursor-pointer px-3 py-2 text-sm font-medium text-foreground">De ce au fost excluse predicții</summary>
									<ul class="space-y-1 border-t border-border p-3 text-sm text-muted-foreground">
										{#each Object.entries(ticketPreflight.excluded_by_reason) as [reason, count] (reason)}<li class="flex justify-between gap-3"><span>{exclusionLabel(reason)}</span><span class="font-mono text-foreground">{count}</span></li>{/each}
									</ul>
								</details>
							{/if}
						{/if}
					</section>

					<details class="mt-5 border border-border bg-background" bind:open={automationOpen}>
						<summary class="flex min-h-11 cursor-pointer items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-foreground">
							<span>Automatizare</span><span class="text-xs font-normal text-muted-foreground">Aceeași configurație · la fiecare {autoTicketIntervalNumber} {autoTicketIntervalUnit.toLowerCase()}</span>
						</summary>
						<div class="space-y-4 border-t border-border p-4">
							<p class="text-sm text-muted-foreground">Salvarea creează un job recurent; nu rulează generarea imediat și nu plasează ordine.</p>
							<label class="flex min-h-11 items-center gap-3 text-sm text-foreground"><input type="checkbox" class="h-4 w-4 accent-football-green" bind:checked={autoTicketGenerationEnabled} /><span>Activează generarea automată salvată</span></label>
							<div class="grid gap-3 sm:grid-cols-2"><Input class="min-h-11" label="Repetă la fiecare" type="number" min="1" bind:value={autoTicketIntervalNumber} disabled={!autoTicketGenerationEnabled} /><Select class="min-h-11" label="Unitate interval" bind:value={autoTicketIntervalUnit} options={[{ value: 'Hours', label: 'ore' }, { value: 'Days', label: 'zile' }, { value: 'Weeks', label: 'săptămâni' }]} disabled={!autoTicketGenerationEnabled} /></div>
							<Button class="min-h-11" type="button" variant="secondary" onclick={saveAutomaticTicketGenerationAction} disabled={!interactive || savingScheduledJob || !autoTicketGenerationEnabled || !generationPreflight.valid}>{savingScheduledJob ? 'Se salvează...' : 'Salvează automatizarea'}</Button>
							{#if automaticTicketJobs.length > 0}<div class="flex flex-wrap gap-2">{#each automaticTicketJobs as scheduledJob (scheduledJob.id)}<Button class="min-h-11" type="button" variant={scheduledJob.enabled ? 'secondary' : 'ghost'} size="sm" title={describeScheduledJob(scheduledJob)} onclick={() => toggleScheduledJob(scheduledJob.id)}>{scheduledJob.name}<span class="ml-1 font-mono text-xs">{scheduledJob.enabled ? 'activ' : 'pauzat'}</span></Button>{/each}</div>{:else}<p class="text-sm text-muted-foreground">Nu există încă o automatizare de bilete.</p>{/if}
						</div>
					</details>

					<div data-testid="tickets-generate-sticky-cta" class="mobile-above-nav fixed inset-x-3 z-30 border border-football-green/40 bg-background/95 p-3 shadow-2xl backdrop-blur sm:inset-x-4 lg:static lg:mt-5 lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none">
						<Button class="min-h-11" type="button" variant="glow" fullWidth onclick={generateAutomaticTickets} disabled={generatingTickets || !generationPreflight.valid}>{generatingTickets ? 'Se generează lotul...' : generationCta}</Button>
						<p class="mt-2 hidden text-center text-sm text-muted-foreground lg:block">Rezultatul se deschide în „Revizuiește lotul”. Generarea nu execută ordine externe.</p>
					</div>
				</Card>

				<details class="border border-border bg-card" bind:open={manualPlacementOpen}>
					<summary class="flex min-h-12 cursor-pointer flex-col justify-center px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
						<span class="font-semibold text-foreground">Înregistrează un bilet manual</span><span class="text-sm text-muted-foreground">Evidență internă · fără plasare externă</span>
					</summary>
					<form onsubmit={(event) => { event.preventDefault(); void placeBet(); }} class="space-y-4 border-t border-border p-4">
						{#if betError}<div class="border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{betError}</div>{/if}
						<Select class="min-h-11" label="Bankroll" bind:value={selectedBankrollId} options={bankrolls.map((bankroll) => ({ value: String(bankroll.id), label: `${bankroll.name} · ${bankroll.currency} ${bankroll.balance.toFixed(2)}` }))} placeholder="Selectează bankroll..." />
						{#if $betslip.legs.length > 0}
							<div class="space-y-2">{#each $betslip.legs as leg (leg.id)}<div class="flex min-w-0 items-center justify-between gap-3 border border-border bg-background px-3 py-2 text-sm"><div class="min-w-0"><p class="truncate font-medium text-foreground">{leg.matchName}</p><p class="truncate text-xs text-muted-foreground">{leg.market} · {leg.selection}{leg.source ? ` · ${leg.source}` : ''}</p></div><span class="shrink-0 font-mono text-football-green">{leg.odds.toFixed(2)}</span></div>{/each}</div>
							<div class="grid grid-cols-1 gap-4 sm:grid-cols-2"><Input class="min-h-11" label="Miză" type="number" step="0.01" value={$betslip.stake.toString()} oninput={(event) => betslip.setStake(parseFloat(event.currentTarget.value) || 0)} /><Select class="min-h-11" label="Tip bilet" value={$betslip.ticketType} options={[{ value: 'single', label: 'Simplu' }, { value: 'accumulator', label: 'Multiplu' }]} onchange={onTicketTypeChange} /></div>
							<div class="grid grid-cols-2 gap-3 border border-border bg-background p-3 text-sm"><div><p class="text-muted-foreground">Cotă combinată</p><p class="font-mono font-medium text-foreground">x{$betslipCombinedOdds.toFixed(2)}</p></div><div><p class="text-muted-foreground">Retur potențial</p><p class="font-mono text-football-green">£{$betslipPotentialReturn.toFixed(2)}</p></div></div>
							<div class="flex flex-col gap-2 sm:flex-row"><Button class="min-h-11" aria-label="Golește selecțiile" type="button" variant="secondary" onclick={() => betslip.clearLegs()}>Golește selecțiile</Button><Button aria-label="Înregistrează biletul în platformă" type="submit" disabled={betSubmitting || $betslip.stake <= 0 || bankrolls.length === 0} class="min-h-11 flex-1">{betSubmitting ? 'Se înregistrează...' : 'Înregistrează biletul'}</Button></div>
						{:else}
							<Select class="min-h-11" label="Meci" bind:value={betMatchId} options={matchOptions} placeholder="Selectează meci..." disabled={matchOptions.length === 0} />
							<div class="grid grid-cols-1 gap-4 sm:grid-cols-2"><Select class="min-h-11" label="Piață" bind:value={betMarket} options={[{ value: '1x2', label: '1X2 · rezultat' }, { value: 'over_under', label: 'Peste/Sub' }, { value: 'both_score', label: 'Ambele marchează' }]} /><Select class="min-h-11" label="Selecție" bind:value={betSelection} options={[{ value: 'home', label: 'Gazde' }, { value: 'draw', label: 'Egal' }, { value: 'away', label: 'Oaspeți' }]} /><Input class="min-h-11" label="Cotă" type="number" step="0.01" bind:value={betOdds} /><Input class="min-h-11" label="Miză" type="number" step="0.50" bind:value={betStake} /></div>
							{#if matchOptions.length === 0}<div class="border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-200">Nu există meciuri programate pentru plasare manuală. Pregătește datele mai întâi.</div>{/if}
							<Button class="min-h-11" aria-label="Înregistrează biletul manual" type="submit" disabled={betSubmitting || !betMatchId || bankrolls.length === 0}>{betSubmitting ? 'Se înregistrează...' : 'Înregistrează biletul'}</Button>
						{/if}
					</form>
				</details>
			</div>
			{:else if activeTab === 'review'}
				<div class="space-y-5 pt-5">
					{#if generatedDraftBatchOptions.length > 1}
						<div class="max-w-xl"><Select class="min-h-11" label="Lot draft de revizuit" value={String(generatedBatchId ?? '')} options={generatedDraftBatchOptions} onchange={onGeneratedBatchChange} /></div>
					{/if}
					{#if generatedBatchLoading}
						<Loading message={`Se încarcă toate biletele din lotul #${generatedBatchId ?? '—'}...`} />
					{:else if generatedBatchLoadError}
						<div class="border border-destructive/30 bg-destructive/10 p-4" role="alert"><p class="text-sm font-medium text-destructive">{generatedBatchLoadError}</p><p class="mt-2 text-sm text-muted-foreground">Revizuirea și activarea sunt blocate până când lotul complet este disponibil.</p>{#if generatedBatchId !== null}<Button class="mt-3" variant="secondary" onclick={retryFullGeneratedBatch}>Reîncarcă lotul complet</Button>{/if}</div>
					{:else if generatedTickets.length === 0}
						<div class="border border-border bg-card px-4 py-12 text-center"><h2 class="text-lg font-semibold text-foreground">Nu există un lot nou de revizuit</h2><p class="mt-2 text-sm text-muted-foreground">Generează un lot dintr-un run explicit sau deschide Istoric pentru loturile persistate.</p><Button class="mt-4 min-h-11" onclick={() => (activeTab = 'generate')}>Configurează un lot</Button></div>
					{:else}
						<section class="border border-football-green/30 bg-football-green/5 p-4" aria-labelledby="generated-batch-heading">
							<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><p class="text-xs uppercase tracking-wide text-football-green">Lot generat · încă nerevizuit</p><h2 id="generated-batch-heading" class="mt-1 text-lg font-semibold text-foreground">Lot #{generatedBatchId} · revizia {generatedBatchRevision}</h2><p class="mt-1 text-sm text-muted-foreground">{generatedBatchState.loadedCount}/{generatedBatchState.expectedCount} bilete încărcate · surse {generatedSourceRunIds.length > 0 ? generatedSourceRunIds.map((id) => `run #${id}`).join(', ') : 'indisponibile'} · set de date {generationReport?.source_dataset_id ? `#${generationReport.source_dataset_id}` : handoff.datasetId ? `#${handoff.datasetId}` : 'indisponibil'}</p></div><Badge variant={generatedBatchState.complete ? 'success' : 'warning'}>{generatedBatchState.complete ? 'Lot complet' : 'Lot incomplet'}</Badge></div>
							{#if generationReport}<div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4"><div><p class="text-[11px] uppercase text-muted-foreground">Scanate</p><p class="font-mono text-foreground">{generationReport.scanned_predictions ?? '—'}</p></div><div><p class="text-[11px] uppercase text-muted-foreground">Eligibile</p><p class="font-mono text-football-green">{generationReport.eligible_candidates ?? '—'}</p></div><div><p class="text-[11px] uppercase text-muted-foreground">Excluse</p><p class="font-mono text-yellow-300">{generationReport.excluded_predictions ?? '—'}</p></div><div><p class="text-[11px] uppercase text-muted-foreground">Stare run</p><p class="font-mono text-foreground">{generationReport.prediction_run_status ?? '—'}</p></div></div>{/if}
							<div class="mt-3 border border-border bg-background p-3 text-sm"><p class="font-medium text-foreground">Policy v{generatedRiskPolicyVersion ?? '—'} · miză server-side</p><p class="mt-1 text-xs text-muted-foreground">{generatedStakingSnapshot ? 'Snapshotul de staking este persistat pentru fiecare bilet.' : 'Snapshotul de staking nu este disponibil.'} {generatedWarningCodes.length > 0 ? `Avertismente acceptate la activare: ${generatedWarningCodes.join(', ')}.` : 'Fără avertismente de risc raportate.'}</p></div>
							<div class="mt-4 grid gap-2 border border-border bg-background p-3 text-xs sm:grid-cols-5">
								<div><p class="font-semibold text-football-green">1 · Date</p><p class="mt-1 text-muted-foreground">Set {generationReport?.source_dataset_id ? `#${generationReport.source_dataset_id}` : 'indisponibil'}</p></div>
								<div><p class="font-semibold text-football-green">2 · Strategii</p><p class="mt-1 text-muted-foreground">{generatedSourceRunIds.length} run-uri</p></div>
								<div><p class="font-semibold text-football-green">3 · Predicții</p><p class="mt-1 text-muted-foreground">{generationReport?.scanned_predictions ?? '—'} scanate</p></div>
								<div><p class="font-semibold text-football-green">4 · Filtrare</p><p class="mt-1 text-muted-foreground">{generationReport?.eligible_candidates ?? '—'} eligibile</p></div>
								<div><p class="font-semibold text-football-gold">5 · Draft</p><p class="mt-1 text-muted-foreground">{generatedBatchState.loadedCount} bilete</p></div>
							</div>
			<RiskLadder
				title="Probabilitate implicită pe bilet"
				description="Vezi separat probabilitatea implicită a fiecărui bilet generat; nu confundăm cota totală cu probabilitatea modelului."
				display="rows"
				probabilityRows={generatedTicketProbabilityRows}
				eligibleCandidates={generationReport?.eligible_candidates ?? 0}
				uniqueMatches={generatedUniqueMatches}
			/>
			<TicketDecisionEvidence tickets={generatedTickets} />
			{#if generatedLineageLoading}
				<p class="mt-4 border border-border bg-background p-3 text-sm text-muted-foreground" role="status">Se încarcă proveniența exactă a predicțiilor...</p>
			{:else if generatedLineageError}
				<div class="mt-4 border border-football-gold/40 bg-football-gold/10 p-3 text-sm text-foreground" role="status">{generatedLineageError} Lotul rămâne revizuibil pe baza raportului de generare.</div>
				{:else if generatedLineage}
					<details class="mt-4 border border-border bg-background" data-testid="ticket-lineage-detail">
						<summary class="min-h-12 cursor-pointer list-none px-4 py-3 text-sm font-semibold text-foreground">Proveniență exactă: dataset → strategie/run → predicție → selecție</summary>
						<div class="border-t border-border px-4 py-3">
							<a href={analyzeHref} class="inline-flex min-h-11 items-center justify-center border border-border px-3 text-sm font-medium text-foreground transition-colors hover:border-football-blue/60 hover:text-football-blue">
								Deschide această sursă în Analiză
							</a>
						</div>
						<div class="space-y-4 border-t border-border p-4">
						<div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
							{#each generatedLineage.source_runs as sourceRun (sourceRun.id)}
								<div class="border border-border bg-card p-3 text-xs">
									<p class="font-mono font-semibold text-foreground">Run #{sourceRun.id}</p>
									<p class="mt-1 text-muted-foreground">{sourceRun.strategy_name ?? sourceRun.model_type} · {sourceRun.status}</p>
									<p class="mt-1 text-muted-foreground">Set #{sourceRun.source_dataset_id ?? '—'} · {sourceRun.matches_count} meciuri</p>
								</div>
							{/each}
						</div>
						<div class="space-y-2">
							{#each generatedLineage.tickets as lineageTicket (lineageTicket.id)}
								<div class="border border-border bg-card p-3">
									<p class="font-mono text-xs font-semibold text-foreground">Bilet #{lineageTicket.reference ?? lineageTicket.id}</p>
									<div class="mt-2 space-y-2">
										{#each lineageTicket.legs as lineageLeg (lineageLeg.id)}
											<div class="grid gap-2 border-l-2 border-football-green/50 pl-3 text-xs sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
												<div>
													<p class="font-medium text-foreground">{lineageLeg.match?.home_team ?? 'Meci'} vs {lineageLeg.match?.away_team ?? '?'}</p>
													<p class="mt-1 text-muted-foreground">{lineageLeg.run?.strategy_name ?? lineageLeg.run?.model_type ?? 'Run indisponibil'} · {lineageLeg.run ? `run #${lineageLeg.run.id}` : 'run indisponibil'} · predicție #{lineageLeg.model_prediction_id ?? '—'}</p>
												</div>
												<div class="text-left sm:text-right">
													<p class="font-mono text-foreground">{lineageLeg.prediction?.quality_report?.model?.pick ?? lineageLeg.selection} · @{lineageLeg.odds.toFixed(2)}</p>
													<p class="mt-1 text-muted-foreground">Model p {lineageModelProbability(lineageLeg) === null ? '—' : `${lineageModelProbability(lineageLeg)?.toFixed(1)}%`} · EV {typeof lineageLeg.prediction?.quality_report?.edge?.pick_edge_pct === 'number' ? `${lineageLeg.prediction.quality_report.edge.pick_edge_pct.toFixed(1)}%` : '—'} · {lineageLeg.prediction?.quality_report?.reliability?.label ?? 'fiabilitate indisponibilă'}</p>
												</div>
											</div>
										{/each}
									</div>
								</div>
							{/each}
						</div>
					</div>
				</details>
			{/if}
			<p class="mt-3 text-sm leading-5 text-football-gold">Aceste bilete sunt doar generate. Nu sunt active, nu afectează statisticile și nu debitează miza până când confirmi revizuirea și activezi lotul.</p>
							<div class="mt-4 border-t border-football-green/20 pt-4">
								<AlertDialog.Root bind:open={discardConfirmOpen} onOpenChange={(open) => { if (open) discardError = ''; }}>
									<AlertDialog.Trigger type="button" class="touch-target inline-flex min-h-11 items-center justify-center px-4 text-sm font-medium text-destructive transition-colors hover:bg-destructive/10 hover:text-destructive">
										Renunță la lotul draft
									</AlertDialog.Trigger>
									<AlertDialog.Portal>
										<AlertDialog.Overlay class="fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
										<AlertDialog.Content onOpenAutoFocus={(event) => { event.preventDefault(); discardCancelButton?.focus(); }} class="fixed left-1/2 top-1/2 z-50 grid max-h-[calc(100dvh-var(--mobile-nav-height)-2rem)] w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 gap-4 overflow-y-auto border bg-background p-6 shadow-lg sm:max-h-[calc(100dvh-2rem)] sm:max-w-lg">
											<DialogHeader>
												<AlertDialog.Title level={3} class="text-lg font-semibold leading-none tracking-tight">Renunți la lotul draft #{generatedBatchId}?</AlertDialog.Title>
												<AlertDialog.Description class="text-sm leading-5 text-muted-foreground">Vor fi eliminate numai biletele generate din acest lot. Acțiunea nu activează bilete și nu modifică miza, deoarece draftul nu a fost debitat.</AlertDialog.Description>
											</DialogHeader>
											{#if discardError}<p class="text-sm text-destructive" role="alert">{discardError}</p>{/if}
											<DialogFooter class="gap-2 sm:space-x-0">
												<AlertDialog.Cancel bind:ref={discardCancelButton} type="button" class="touch-target inline-flex min-h-11 items-center justify-center bg-secondary px-4 text-sm font-medium text-secondary-foreground transition-colors hover:bg-secondary/80" disabled={discardingGeneratedBatch}>Păstrează lotul</AlertDialog.Cancel>
												<Button class="min-h-11" variant="danger" onclick={discardGeneratedDraft} disabled={discardingGeneratedBatch}>{discardingGeneratedBatch ? 'Se elimină...' : 'Confirmă renunțarea'}</Button>
											</DialogFooter>
										</AlertDialog.Content>
									</AlertDialog.Portal>
								</AlertDialog.Root>
							</div>
					</section>
					<div class="grid min-w-0 gap-4 xl:grid-cols-2">
						{#each generatedTickets as ticket (ticket.id)}
							{@const contributingRunIds = ticketRunIdsFromReport(ticket.id, generationReport, generatedSourceRunIds)}
							<article class="min-w-0 border border-border bg-card p-4">
						<div class="flex flex-wrap items-start justify-between gap-3"><div><div class="flex flex-wrap items-center gap-2"><span class="font-mono text-sm text-foreground">#{ticket.reference ?? ticket.id}</span><Badge variant={statusBadge[ticket.status] ?? 'default'}>{ticketStatusLabel(ticket.status)}</Badge><Badge variant="info">{selectionCountLabel(ticket.legs.length)}</Badge></div><p data-testid={`ticket-contributing-runs-${ticket.id}`} class="mt-2 text-sm text-muted-foreground">Sursa acestui bilet: <span class="font-mono text-foreground">{runLineageLabel(contributingRunIds)}</span> · lot #{ticket.batch_id ?? generatedBatchId}</p></div><div class="text-right"><p class="font-mono text-lg text-football-green">x{ticket.total_odds.toFixed(2)}</p><p class="text-sm text-muted-foreground">estimare implicită {estimateWinChance(ticket).toFixed(1)}%</p></div></div>
								<div class="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3"><div><p class="text-xs text-muted-foreground">Miză</p><p class="font-mono text-foreground">{ticket.stake.toFixed(2)}</p></div><div><p class="text-xs text-muted-foreground">Retur potențial</p><p class="font-mono text-foreground">{ticket.potential_return.toFixed(2)}</p></div><div><p class="text-xs text-muted-foreground">Calitate</p><p class="text-yellow-300">Verifică selecțiile</p></div></div>
								<details class="mt-4 border-t border-border pt-3"><summary class="min-h-11 cursor-pointer py-3 text-sm font-semibold text-foreground">Vezi selecțiile și cotele</summary><div class="space-y-2">{#each ticket.legs as leg (leg.id)}<div class="min-w-0 border border-border bg-muted/20 p-3"><div class="flex flex-wrap items-start justify-between gap-2"><div class="min-w-0"><p class="font-medium text-foreground">{leg.match?.home_team ?? 'Meci'} vs {leg.match?.away_team ?? '?'}</p><p class="text-sm text-muted-foreground">{leg.match?.league ?? 'Ligă indisponibilă'} · {matchStatusText(leg.match)}</p></div><Badge variant={leg.status === 'won' ? 'success' : leg.status === 'lost' ? 'danger' : 'neutral'}>{ticketStatusLabel(leg.status)}</Badge></div><div class="mt-2 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4"><span>{leg.market}</span><span>{leg.selection}</span><span>@ {leg.odds.toFixed(2)}</span><span>estimare implicită {(100 / leg.odds).toFixed(1)}%</span></div>{#if leg.model_prediction_id}<p class="mt-2 font-mono text-sm text-muted-foreground">predicție #{leg.model_prediction_id}</p>{/if}</div>{/each}</div></details>
							</article>
						{/each}
					</div>

					<details class="border border-border bg-card">
						<summary class="min-h-12 cursor-pointer px-4 py-4 font-semibold text-foreground">Schimbă selecții între bilete</summary>
						<div class="space-y-4 border-t border-border p-4"><p class="text-sm text-muted-foreground">Alege două selecții din bilete diferite. Vezi impactul estimat asupra cotelor, apoi confirmă explicit.</p><div class="grid gap-3 lg:grid-cols-2"><Select class="min-h-11" label="Selecție sursă" bind:value={sourceSwapLeg} options={generatedLegOptions()} placeholder="Alege selecția sursă..." /><Select class="min-h-11" label="Selecție destinație" bind:value={targetSwapLeg} options={generatedLegOptions()} placeholder="Alege selecția destinație..." /></div>
							{#if generatedSwapPreview}<Button variant="secondary" onclick={() => (swapPreviewOpen = true)}>Previzualizează schimbul</Button>{:else}<p class="text-xs text-yellow-300">Selectează picioare din două bilete diferite.</p>{/if}
							{#if swapPreviewOpen && generatedSwapPreview}<div class="border border-yellow-500/30 bg-yellow-500/10 p-4"><p class="text-sm font-semibold text-foreground">Previzualizare înainte / după</p><p class="mt-2 font-mono text-sm text-foreground">{generatedSwapPreview.sourceLabel}</p><p class="mt-1 font-mono text-sm text-foreground">{generatedSwapPreview.targetLabel}</p><p class="mt-2 text-xs text-muted-foreground">Se schimbă selecțiile cu cote {generatedSwapPreview.sourceOdds.toFixed(2)} și {generatedSwapPreview.targetOdds.toFixed(2)}. Backendul va recalcula valorile finale.</p><Button class="mt-3" variant="primary" onclick={swapGeneratedLegs} disabled={swappingLegs}>{swappingLegs ? 'Se confirmă...' : 'Confirmă schimbul'}</Button></div>{/if}
							{#if swapMessage}<p class="text-sm text-muted-foreground" role="status">{swapMessage}</p>{/if}</div>
					</details>

					<div data-testid="tickets-review-sticky-cta" class="mobile-above-nav fixed inset-x-3 z-30 border border-football-green/40 bg-background/95 p-3 shadow-2xl backdrop-blur sm:inset-x-4 lg:static lg:border-border lg:bg-card/95 lg:p-4 lg:shadow-lg">
						<div class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 sm:gap-3">
							<label class="flex min-h-11 items-center gap-2 text-sm text-foreground"><input type="checkbox" class="size-5 shrink-0 accent-football-green" bind:checked={generatedReviewAcknowledged} disabled={!generatedBatchState.complete} /><span><span class="sm:hidden">Am verificat lotul</span><span class="hidden sm:inline">Am verificat toate cele {ticketCountLabel(generatedBatchState.expectedCount)}, sursa, selecțiile, cotele și miza.</span></span></label>
							<div class="flex gap-2"><Button class="hidden min-h-11 sm:inline-flex" variant="secondary" onclick={() => (activeTab = 'generate')}>Modifică</Button><Button class="min-h-11" onclick={activateGeneratedTickets} disabled={!generatedReviewAcknowledged || !generatedBatchState.complete || activatingGeneratedBatch}>{activatingGeneratedBatch ? 'Se activează...' : 'Activează lotul'}</Button></div>
						</div>
						<p class="mt-2 hidden text-sm text-muted-foreground lg:block">Activarea persistă schimbarea de stare și debitează miza internă; nu trimite o comandă externă.</p>
						{#if activationError}<p class="mt-2 text-sm text-destructive" role="alert">{activationError}</p>{/if}
					</div>
				{/if}
			</div>
		{:else if activeTab === 'active'}
			<div class="space-y-5 pt-5">
				<section class="border border-border bg-card p-4" aria-labelledby="verification-heading">
					<div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between"><div><h2 id="verification-heading" class="text-base font-semibold text-foreground">Verificare rezultate</h2><p class="mt-1 max-w-2xl text-sm text-muted-foreground">Actualizează scorurile finale, inspectează rezultatul jobului, apoi finalizează doar biletele cu rezultate confirmate.</p></div><div class="flex flex-col gap-2 sm:flex-row"><Button class="min-h-11" onclick={refreshFinalResults} disabled={resultsRefreshing || activeTickets.length === 0}>{resultsRefreshing ? 'Se actualizează...' : 'Actualizează rezultate finale'}</Button><Button class="min-h-11" variant="secondary" onclick={verifyResults} disabled={verificationAction.disabled}>{verificationActionLabel}</Button></div></div>
					{#if resultsRefreshMessage}<p class="mt-3 text-xs text-muted-foreground" role="status">{resultsRefreshMessage}</p>{/if}{#if resultsRefreshConflictPolicy}<p class="mt-2 text-xs text-muted-foreground" role="status">{resultsRefreshConflictPolicy}</p>{/if}{#if settlementMessage}<p class="mt-2 text-xs text-muted-foreground" role="status">{settlementMessage}</p>{/if}{#if scheduledJobsError}<p class="mt-2 text-xs text-destructive" role="alert">{scheduledJobsError}</p>{/if}
					<details class="mt-4 border border-border bg-background" bind:open={verificationAutomationOpen}><summary class="min-h-11 cursor-pointer px-4 py-3 text-sm font-semibold text-foreground">Automatizare verificare</summary><div class="space-y-4 border-t border-border p-4"><label class="flex min-h-11 items-center gap-3 text-sm text-foreground"><input aria-label="Activează verificarea programată" type="checkbox" class="size-5 accent-football-blue" bind:checked={autoVerificationEnabled} /><span>Activează verificarea programată</span></label><div class="grid gap-3 sm:grid-cols-2"><Input class="min-h-11" label="Număr interval" name="tickets-auto-verification-interval" type="number" min="1" bind:value={autoVerificationIntervalNumber} disabled={!autoVerificationEnabled} /><Select class="min-h-11" label="Unitate interval" bind:value={autoVerificationIntervalUnit} options={[{ value: 'Hours', label: 'ore' }, { value: 'Days', label: 'zile' }, { value: 'Weeks', label: 'săptămâni' }]} disabled={!autoVerificationEnabled} /></div><div class="flex flex-wrap gap-2"><Button aria-label="Salvează verificarea automată" variant="secondary" onclick={saveAutomaticVerificationAction} disabled={!interactive || savingScheduledJob || !autoVerificationEnabled}>{savingScheduledJob ? 'Se salvează...' : 'Salvează verificarea automată'}</Button><Button variant="ghost" onclick={fetchScheduledJobs} disabled={loadingScheduledJobs}>{loadingScheduledJobs ? 'Se actualizează...' : 'Actualizează joburile'}</Button></div>{#if automaticVerificationJobs.length > 0}<div class="flex flex-wrap gap-2">{#each automaticVerificationJobs as scheduledJob (scheduledJob.id)}<Button class="min-h-11" variant={scheduledJob.enabled ? 'secondary' : 'ghost'} size="sm" title={describeScheduledJob(scheduledJob)} onclick={() => toggleScheduledJob(scheduledJob.id)}>{scheduledJob.name}<span class="ml-1 font-mono text-xs">{scheduledJob.enabled ? 'activ' : 'pauzat'}</span></Button>{/each}</div>{:else}<p class="text-sm text-muted-foreground">Nu există job automat de verificare.</p>{/if}</div></details>
				</section>

				{#if activeTickets.length === 0}
					<div class="border border-border bg-card py-12 text-center"><h2 class="text-lg font-semibold text-foreground">Nu există bilete active</h2><p class="mt-2 text-sm text-muted-foreground">Generează un lot nou sau înregistrează un bilet manual.</p><Button class="mt-4" onclick={() => (activeTab = 'generate')}>Mergi la Generează</Button></div>
				{:else}
					<div class="grid min-w-0 gap-4 xl:grid-cols-2">{#each activeTickets as ticket (ticket.id)}<article class="min-w-0 border border-border bg-card p-4"><div class="flex flex-wrap items-start justify-between gap-3"><div><div class="flex flex-wrap items-center gap-2"><span class="font-mono text-sm text-foreground">#{ticket.reference}</span><Badge variant="info">{localizedTicketTypeLabel(ticketTypeLabel(ticket))}</Badge><Badge variant={statusBadge[ticket.status] ?? 'default'}>{ticketStatusLabel(ticket.status)}</Badge></div><p class="mt-2 text-sm text-muted-foreground">{ticket.legs.filter((leg) => leg.status !== 'pending').length}/{ticket.legs.length} selecții finalizate · {new Date(ticket.created_at).toLocaleString('ro-RO')}</p></div><div class="text-right"><p class="font-mono text-lg text-football-green">x{ticket.total_odds.toFixed(2)}</p><p class="text-sm text-muted-foreground">retur {ticket.potential_return.toFixed(2)}</p></div></div><div class="mt-4 h-1.5 bg-muted"><div class="h-full bg-football-green" style={`width: ${ticket.legs.length > 0 ? (ticket.legs.filter((leg) => leg.status !== 'pending').length / ticket.legs.length) * 100 : 0}%`}></div></div><div class="mt-4 space-y-2">{#each ticket.legs as leg (leg.id)}<div class="border border-border bg-muted/20 p-3 text-sm"><div class="flex flex-wrap justify-between gap-2"><span class="font-medium text-foreground">{leg.match?.home_team ?? 'Meci'} vs {leg.match?.away_team ?? '?'}</span><Badge variant={leg.status === 'won' ? 'success' : leg.status === 'lost' ? 'danger' : 'neutral'}>{ticketStatusLabel(leg.status)}</Badge></div><p class="mt-1 text-sm text-muted-foreground">{matchStatusText(leg.match)} · {leg.market}/{leg.selection} @ {leg.odds.toFixed(2)}{leg.match?.status === 'finished' ? ` · scor ${leg.match.home_score ?? '?'}-${leg.match.away_score ?? '?'}` : ''}</p></div>{/each}</div>{#if paperTradingEnabled}<div class="mt-4 flex flex-col gap-2 border-t border-border pt-4 sm:flex-row sm:items-center"><Button class="min-h-11" variant="secondary" size="sm" disabled={paperExecutingTicketId === ticket.id || paperExecutions[ticket.id]?.status === 'filled'} onclick={() => executePaperTicket(ticket)}>{paperExecutingTicketId === ticket.id ? 'Se execută simularea...' : 'Simulează BACK LIMIT'}</Button><span class="text-sm text-muted-foreground">Simulare locală · fără ordin extern</span></div>{#if paperExecutionMessages[ticket.id]}<p class="mt-2 text-sm text-muted-foreground" role="status">{paperExecutionMessages[ticket.id]}</p>{/if}{/if}</article>{/each}</div>
				{/if}
			</div>
		{:else if activeTab === 'history'}
			<div class="space-y-5 pt-5">
				{#if batches.length === 0}
					<div class="border border-border bg-card py-12 text-center"><h2 class="text-lg font-semibold text-foreground">Nu există loturi istorice</h2><p class="mt-2 text-sm text-muted-foreground">Primul lot generat va apărea aici.</p><Button class="mt-4 min-h-11" onclick={() => (activeTab = 'generate')}>Generează primul lot</Button></div>
				{:else}
					<section class="border border-border bg-card p-4"><div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"><Select class="min-h-11" label="Lot de bilete" bind:value={selectedBatchId} options={batchOptions} placeholder="Selectează lot..." onchange={onBatchChange} /><div class="grid grid-cols-2 gap-3 border border-border bg-muted/20 p-3 text-sm"><div><p class="text-xs text-muted-foreground">Creat</p><p class="text-foreground">{selectedBatch ? new Date(selectedBatch.created_at).toLocaleString('ro-RO') : '—'}</p></div><div><p class="text-xs text-muted-foreground">Progres</p><p class="font-mono text-foreground">{selectedBatchProgress}</p></div><div><p class="text-xs text-muted-foreground">Miză lot</p><p class="font-mono text-foreground">{selectedBatch?.total_stake?.toFixed(2) ?? '—'}</p></div><div><p class="text-xs text-muted-foreground">Run-uri sursă</p><p data-testid="tickets-history-source-runs" class="font-mono {selectedBatchSourceRuns.length > 0 ? 'text-foreground' : 'text-football-gold'}">{selectedBatchSourceRuns.length > 0 ? runLineageLabel(selectedBatchSourceRuns) : 'lot vechi · indisponibil'}</p></div>{#if selectedBatchGenerationReport}<div><p class="text-xs text-muted-foreground">Candidați eligibili</p><p class="font-mono text-football-green">{selectedBatchGenerationReport.eligible_candidates ?? '—'}</p></div><div><p class="text-xs text-muted-foreground">Excluderi</p><p class="font-mono text-football-gold">{selectedBatchGenerationReport.excluded_predictions ?? '—'}</p></div><div><p class="text-xs text-muted-foreground">Stare run</p><p class="font-mono text-foreground">{selectedBatchGenerationReport.prediction_run_status ?? '—'}</p></div><div><p class="text-xs text-muted-foreground">Subset solicitat</p><p class="font-mono text-foreground">{selectedBatchGenerationReport.requested_prediction_ids?.length ?? 'toți eligibili'}</p></div>{/if}</div></div></section>
					{#if batchTicketsLoading}<Loading message="Se încarcă lotul..." />{:else if batchLoadError}<div class="border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{batchLoadError}</div>{:else if selectedBatchTickets.length === 0}<p class="border border-border bg-card py-12 text-center text-muted-foreground">Lotul nu conține bilete.</p>{:else}
							<div class="space-y-3">{#each selectedBatchTickets as ticket (ticket.id)}<details class="border border-border bg-card"><summary class="min-h-14 cursor-pointer list-none p-4"><div class="flex flex-wrap items-center justify-between gap-3"><div><div class="flex flex-wrap items-center gap-2"><span class="font-mono text-sm text-foreground">#{ticket.reference ?? ticket.id}</span><Badge variant={statusBadge[ticket.status] ?? 'default'}>{ticketStatusLabel(ticket.status)}</Badge><span class="text-sm text-muted-foreground">{selectionCountLabel(ticket.legs.length)}</span></div><p data-testid={`ticket-history-contributing-runs-${ticket.id}`} class="mt-2 text-sm text-muted-foreground">Sursa biletului: <span class="font-mono text-foreground">{runLineageLabel(ticketRunIdsFromReport(ticket.id, selectedBatchGenerationReport, selectedBatchSourceRuns))}</span></p></div><div class="text-right"><p class="font-mono text-football-green">x{ticket.total_odds.toFixed(2)}</p><p class="text-sm text-muted-foreground">{ticketProfitLoss(ticket) === null ? 'Profit/pierdere după activare și închidere' : `Profit/pierdere ${ticketProfitLoss(ticket)?.toFixed(2)}`}</p></div></div></summary><div class="space-y-2 border-t border-border p-4">{#each ticket.legs as leg (leg.id)}<div class="border border-border bg-muted/20 p-3 text-sm"><div class="flex flex-wrap justify-between gap-2"><span class="font-medium text-foreground">{leg.match?.home_team ?? 'Meci'} vs {leg.match?.away_team ?? '?'}</span><Badge variant={leg.status === 'won' ? 'success' : leg.status === 'lost' ? 'danger' : 'neutral'}>{ticketStatusLabel(leg.status)}</Badge></div><p class="mt-1 text-sm text-muted-foreground">{matchStatusText(leg.match)} · {leg.market}/{leg.selection} @ {leg.odds.toFixed(2)}</p></div>{/each}</div></details>{/each}</div>
						<details class="border border-border bg-card"><summary class="min-h-12 cursor-pointer px-4 py-4 font-semibold text-foreground">Ajustează selecțiile lotului</summary><div class="space-y-4 border-t border-border p-4"><div class="grid gap-3 lg:grid-cols-2"><Select class="min-h-11" label="Selecție sursă" bind:value={historySourceSwapLeg} options={batchLegOptions(selectedBatchTickets)} placeholder="Alege sursa..." /><Select class="min-h-11" label="Selecție destinație" bind:value={historyTargetSwapLeg} options={batchLegOptions(selectedBatchTickets)} placeholder="Alege destinația..." /></div>{#if historySwapPreview}<Button class="min-h-11" variant="secondary" onclick={() => (historySwapPreviewOpen = true)}>Previzualizează schimbul</Button>{:else}<p class="text-sm text-yellow-300">Selectează selecții din două bilete diferite.</p>{/if}{#if historySwapPreviewOpen && historySwapPreview}<div class="border border-yellow-500/30 bg-yellow-500/10 p-4"><p class="font-mono text-sm text-foreground">{historySwapPreview.sourceLabel}</p><p class="mt-1 font-mono text-sm text-foreground">{historySwapPreview.targetLabel}</p><Button class="mt-3 min-h-11" onclick={swapBatchLegs} disabled={historySwappingLegs}>{historySwappingLegs ? 'Se confirmă...' : 'Confirmă schimbul'}</Button></div>{/if}{#if historySwapMessage}<p class="text-sm text-muted-foreground" role="status">{historySwapMessage}</p>{/if}</div></details>
					{/if}
				{/if}
			</div>
		{/if}
	</Tabs>
</div>
