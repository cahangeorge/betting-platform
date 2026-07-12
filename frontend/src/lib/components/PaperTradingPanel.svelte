<script lang="ts">
	import { ApiClientError } from '$lib/api/client';
	import { tradingApi } from '$lib/api/trading';
	import type { TradingAccount, TradingAccountHealth } from '$lib/types';
	import Button from './ui/Button.svelte';
	import Card from './ui/Card.svelte';

	let { serverAccounts = [] }: { serverAccounts?: TradingAccount[] } = $props();
	let accounts = $derived(serverAccounts);
	let health = $state<Record<number, TradingAccountHealth>>({});
	let message = $state('');
	let creating = $state(false);

	async function createPaperAccount() {
		creating = true;
		message = '';
		try {
			const account = await tradingApi.createPaperAccount({ name: 'Local paper account', initial_balance: 1000, currency: 'EUR' });
			accounts = [account, ...accounts];
			message = 'Paper-local account created. It contains no bookmaker credentials.';
			await checkHealth(account.id);
		} catch (err) {
			message = err instanceof ApiClientError ? err.message : 'Failed to create paper trading account';
		} finally {
			creating = false;
		}
	}

	async function checkHealth(accountId: number) {
		message = '';
		try {
			health = { ...health, [accountId]: await tradingApi.getAccountHealth(accountId) };
		} catch (err) {
			message = err instanceof ApiClientError ? err.message : 'Failed to check paper account health';
		}
	}
</script>

<Card class="border-l-3 border-l-football-blue p-4">
	<div class="flex flex-wrap items-start justify-between gap-3">
		<div>
			<h2 class="text-base font-semibold text-foreground">Paper execution accounts</h2>
			<p class="mt-1 text-xs text-muted-foreground">
				Isolated local simulation. Live trading is disabled; Betfair is read-only and not configured.
			</p>
		</div>
		<Button size="sm" variant="secondary" onclick={createPaperAccount} disabled={creating}>
			{creating ? 'Creating...' : 'Create paper account'}
		</Button>
	</div>

	<div class="mt-4 space-y-2">
		{#each accounts as account (account.id)}
			<div class="flex flex-wrap items-center justify-between gap-3 border border-border bg-muted/20 p-3 text-sm">
				<div>
					<p class="font-medium text-foreground">{account.name}</p>
					<p class="font-mono text-xs text-muted-foreground">{account.currency} {account.balance.toFixed(2)} · {account.provider} · {account.enabled ? 'enabled' : 'disabled'}</p>
					{#if health[account.id]}
						<p class="mt-1 text-xs text-muted-foreground" role="status">
							{health[account.id].status} · live: disabled · Betfair: {health[account.id].betfair_read_only_status}
						</p>
					{/if}
				</div>
				<Button size="sm" variant="ghost" onclick={() => checkHealth(account.id)}>Check health</Button>
			</div>
		{:else}
			<p class="text-sm text-muted-foreground">No paper execution account yet.</p>
		{/each}
	</div>
	{#if message}<p class="mt-3 text-xs text-muted-foreground" role="status">{message}</p>{/if}
</Card>
