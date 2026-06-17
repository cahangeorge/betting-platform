<script lang="ts">
	import TicketsPanel from '$lib/components/TicketsPanel.svelte';
	import type { BackendLoadStatus } from '$lib/types/backend';
	import { fade } from 'svelte/transition';

	let { data }: import('./$types').PageProps = $props();
	const backendStatus = $derived(((data as { backendStatus?: BackendLoadStatus }).backendStatus as BackendLoadStatus | undefined) ?? {
		state: 'ready',
		message: null,
		failedEndpoints: []
	});
</script>

<div class="space-y-6" transition:fade={{ duration: 200 }}>
	<div>
		<h1 class="text-2xl font-extrabold font-sport text-foreground">TICKETS</h1>
		<p class="mt-1 text-muted-foreground">Place bets, track active tickets, and review betting history</p>
	</div>

	{#if backendStatus.state === 'degraded' && backendStatus.message}
		<div class="border border-yellow-500/30 bg-yellow-500/10 p-4 text-sm text-yellow-200">
			<span class="font-medium">Partial backend data.</span> {backendStatus.message}
		</div>
	{/if}

	<TicketsPanel
		serverTickets={((data as any).tickets) ?? []}
		serverMatches={((data as any).matches) ?? []}
		serverStats={((data as any).stats) ?? { total: 0, won: 0, lost: 0, profit_loss: 0 }}
	/>
</div>
