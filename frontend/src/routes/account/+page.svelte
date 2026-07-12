<script lang="ts">
	import AccountPanel from '$lib/components/AccountPanel.svelte';
	import PaperTradingPanel from '$lib/components/PaperTradingPanel.svelte';
	import type { Bankroll, BookmakerAccount, LedgerEntry, TradingAccount } from '$lib/types';
	import type { BackendLoadStatus } from '$lib/types/backend';

	let { data }: import('./$types').PageProps = $props();
	type AccountPageData = {
		bankrolls?: Bankroll[];
		accounts?: BookmakerAccount[];
		ledger?: LedgerEntry[];
		tradingAccounts?: TradingAccount[];
		backendStatus?: BackendLoadStatus;
	};
	const pageData = $derived(data as AccountPageData);
	const backendStatus = $derived(pageData.backendStatus ?? {
		state: 'ready',
		message: null,
		failedEndpoints: []
	});
</script>

<div class="space-y-6">
	<div>
		<h1 class="text-2xl font-extrabold font-sport text-foreground">ACCOUNT</h1>
		<p class="mt-1 text-muted-foreground">Manage bankrolls, bookmaker accounts, and view transaction history</p>
	</div>

	{#if backendStatus.state === 'degraded' && backendStatus.message}
		<div class="border border-yellow-500/30 bg-yellow-500/10 p-4 text-sm text-yellow-200">
			<span class="font-medium">Partial backend data.</span> {backendStatus.message}
		</div>
	{/if}
	<PaperTradingPanel serverAccounts={pageData.tradingAccounts ?? []} />
	<AccountPanel
		serverBankrolls={pageData.bankrolls ?? []}
		serverAccounts={pageData.accounts ?? []}
		serverLedger={pageData.ledger ?? []}
	/>
</div>
