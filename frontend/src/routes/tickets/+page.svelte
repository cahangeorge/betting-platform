<script lang="ts">
	import TicketsPanel from '$lib/components/TicketsPanel.svelte';
	import { parseTicketHandoff } from '$lib/components/tickets-panel.helpers';
	import type { Bankroll, Match, Ticket, TicketBatch, TradingAccount } from '$lib/types';
	import type { BackendLoadStatus } from '$lib/types/backend';
	import { page } from '$app/state';
	import { fade } from 'svelte/transition';

	let { data }: import('./$types').PageProps = $props();
	type TicketsPageData = {
		tickets?: Ticket[];
		matches?: Match[];
		stats?: { total: number; won: number; lost: number; profit_loss: number };
		bankrolls?: Bankroll[];
		batches?: TicketBatch[];
		tradingAccounts?: TradingAccount[];
		paperTradingEnabled?: boolean;
		backendStatus?: BackendLoadStatus;
	};
	const pageData = $derived(data as TicketsPageData);
	const handoff = $derived(parseTicketHandoff(page.url.searchParams));
	const backendStatus = $derived(pageData.backendStatus ?? {
		state: 'ready',
		message: null,
		failedEndpoints: []
	});
</script>

<svelte:head>
	<title>Bilete | Bet</title>
	<meta name="description" content="Generează, revizuiește și urmărește loturi de bilete cu sursa predicțiilor păstrată explicit." />
</svelte:head>

<div class="workbench-page min-w-0 space-y-4 pb-48 sm:space-y-5 sm:pb-44 lg:space-y-6 lg:pb-12" transition:fade={{ duration: 200 }}>
	<header class="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-end sm:justify-between sm:pb-5">
		<div class="max-w-2xl">
			<p class="workbench-eyebrow"><span class="sm:hidden">Pasul 3 din 4</span><span class="hidden sm:inline">Pregătire → Analiză → Bilete → Monitorizare</span></p>
			<h1 class="mt-1 text-3xl font-semibold tracking-tight text-foreground sm:mt-2 sm:text-4xl">Bilete</h1>
			<p class="mt-2 text-sm leading-5 text-muted-foreground sm:mt-3 sm:text-base sm:leading-6">Generează un lot din sursa analizată, verifică selecțiile și activează-l numai după confirmare.</p>
		</div>
	</header>

	<nav aria-label="Progresul fluxului" class="grid grid-cols-4 border border-border bg-card text-center text-[11px] sm:text-sm">
		<a href="/prepare" class="flex min-h-12 items-center justify-center border-r border-border px-1 font-medium text-football-green transition-colors hover:text-foreground sm:min-h-14 sm:px-3"><span class="sm:hidden">Date</span><span class="hidden sm:inline">Pregătire</span></a>
		<a href="/analyze" class="flex min-h-12 items-center justify-center border-r border-border px-1 font-medium text-football-green transition-colors hover:text-foreground sm:min-h-14 sm:px-3"><span class="sm:hidden">Analiză</span><span class="hidden sm:inline">Analiză</span></a>
		<span aria-current="step" class="flex min-h-12 items-center justify-center border-r border-football-green bg-football-green/10 px-1 font-semibold text-foreground sm:min-h-14 sm:px-3">Bilete</span>
		<a href="/monitoring" class="flex min-h-12 items-center justify-center px-1 font-medium text-muted-foreground transition-colors hover:text-foreground sm:min-h-14 sm:px-3"><span class="sm:hidden">Monitor</span><span class="hidden sm:inline">Monitorizare</span></a>
	</nav>

	{#if backendStatus.state === 'degraded' && backendStatus.message}
		<div class="border border-football-gold/30 bg-football-gold/10 p-4 text-sm text-foreground" role="status">
			<span class="font-medium">Date parțiale din backend.</span> {backendStatus.message}
		</div>
	{/if}

	<TicketsPanel
		{handoff}
		serverTickets={pageData.tickets ?? []}
		serverMatches={pageData.matches ?? []}
		serverStats={pageData.stats ?? { total: 0, won: 0, lost: 0, profit_loss: 0 }}
		serverBankrolls={pageData.bankrolls ?? []}
		serverBatches={pageData.batches ?? []}
		serverTradingAccounts={pageData.tradingAccounts ?? []}
		paperTradingEnabled={pageData.paperTradingEnabled ?? false}
	/>
</div>
