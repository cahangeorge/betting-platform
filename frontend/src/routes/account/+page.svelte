<script lang="ts">
	import AccountPanel from '$lib/components/AccountPanel.svelte';
	import type { BackendLoadStatus } from '$lib/types/backend';

	let { data }: import('./$types').PageProps = $props();
	const backendStatus = $derived(((data as { backendStatus?: BackendLoadStatus }).backendStatus as BackendLoadStatus | undefined) ?? {
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
	<AccountPanel
		serverBankrolls={((data as any)?.bankrolls) ?? []}
		serverAccounts={((data as any)?.accounts) ?? []}
		serverLedger={((data as any)?.ledger) ?? []}
	/>
</div>
