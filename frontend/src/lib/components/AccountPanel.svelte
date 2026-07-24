<script lang="ts">
	import { bankrollApi } from '$lib/api/bankroll';
	import { ApiClientError } from '$lib/api/client';
	import type { Bankroll, BookmakerAccount, LedgerEntry } from '$lib/types';
	import { onMount } from 'svelte';
	import { parseBankrollId, shouldAutoLoadAccountData } from './account-panel.helpers';
	import Button from './ui/Button.svelte';
	import Card from './ui/Card.svelte';
	import Input from './ui/Input.svelte';
	import Tabs from './ui/Tabs.svelte';
	import Select from './ui/Select.svelte';
	import Badge from './ui/Badge.svelte';
	import Loading from './Loading.svelte';
	import EquityCurveChart from './charts/EquityCurveChart.svelte';
	import RiskPolicyPanel from './RiskPolicyPanel.svelte';

	let {
		serverBankrolls,
		serverAccounts,
		serverLedger
	}: {
		serverBankrolls?: Bankroll[];
		serverAccounts?: BookmakerAccount[];
		serverLedger?: LedgerEntry[];
	} = $props();

	let bankrolls = $state<Bankroll[]>([]);
	let accounts = $state<BookmakerAccount[]>([]);
	let ledger = $state<LedgerEntry[]>([]);
	let loading = $state(false);
	let error = $state('');
	let activeTab = $state('bankrolls');
	let hasRequestedInitialLoad = $state(false);
	let interactive = $state(false);

	// New bankroll form
	let showNewBankroll = $state(false);
	let newBankrollName = $state('');
	let newBankrollType = $state<'paper' | 'real'>('paper');
	let newBankrollBalance = $state('1000');
	let newBankrollCurrency = $state('USD');

	// New account form
	let showNewAccount = $state(false);
	let newAccountBookmaker = $state('');
	let newAccountName = $state('');
	let newAccountBalance = $state('0');
	let selectedBankrollId = $state<number | null>(null);
	let bankrollContextGeneration = 0;

	let formError = $state('');

	async function loadBankrollContext(bankrollId: number) {
		const generation = ++bankrollContextGeneration;
		loading = true;
		error = '';
		try {
			const [nextAccounts, nextLedger] = await Promise.all([
				bankrollApi.getAccounts(bankrollId),
				bankrollApi.getLedger(bankrollId)
			]);
			if (generation !== bankrollContextGeneration || selectedBankrollId !== bankrollId) return;
			accounts = nextAccounts;
			ledger = nextLedger;
		} catch (err) {
			if (generation !== bankrollContextGeneration) return;
			error = err instanceof ApiClientError ? err.message : 'Failed to load bankroll data';
		} finally {
			if (generation === bankrollContextGeneration) loading = false;
		}
	}

	function changeBankroll(event: Event) {
		const bankrollId = parseBankrollId((event.currentTarget as HTMLSelectElement).value);
		if (bankrollId === selectedBankrollId) return;
		selectedBankrollId = bankrollId;
		accounts = [];
		ledger = [];
		if (bankrollId) void loadBankrollContext(bankrollId);
	}

	async function loadData() {
		const generation = ++bankrollContextGeneration;
		loading = true;
		error = '';
		try {
			const b = await bankrollApi.getBankrolls();
			const primaryBankrollId = selectedBankrollId ?? b[0]?.id ?? null;
			const [a, l] = primaryBankrollId
				? await Promise.all([
						bankrollApi.getAccounts(primaryBankrollId),
						bankrollApi.getLedger(primaryBankrollId)
					])
				: [[], []];
			bankrolls = b;
			if (generation !== bankrollContextGeneration) return;
			accounts = a;
			ledger = l;
			if (selectedBankrollId === null && b.length > 0) {
				selectedBankrollId = b[0].id;
			}
		} catch (err) {
			if (generation !== bankrollContextGeneration) return;
			error = err instanceof ApiClientError ? err.message : 'Failed to load account data';
		} finally {
			if (generation === bankrollContextGeneration) loading = false;
		}
	}

	async function createBankroll() {
		if (!newBankrollName.trim()) return;
		formError = '';
		try {
			const br = await bankrollApi.createBankroll({
				name: newBankrollName,
				type: newBankrollType,
				currency: newBankrollCurrency,
				initial_balance: parseFloat(newBankrollBalance)
			});
			bankrolls = [...bankrolls, br];
			showNewBankroll = false;
			newBankrollName = '';
			newBankrollBalance = '1000';
		} catch (err) {
			formError = err instanceof ApiClientError ? err.message : 'Failed to create bankroll';
		}
	}

	async function createAccount() {
		if (!newAccountBookmaker.trim() || !newAccountName.trim()) return;
		formError = '';
		try {
			const acct = await bankrollApi.createAccount({
				bookmaker: newAccountBookmaker,
				account_name: newAccountName,
				balance: parseFloat(newAccountBalance),
				bankroll_id: selectedBankrollId || bankrolls[0]?.id || 0
			});
			accounts = [...accounts, acct];
			showNewAccount = false;
			newAccountBookmaker = '';
			newAccountName = '';
		} catch (err) {
			formError = err instanceof ApiClientError ? err.message : 'Failed to create account';
		}
	}

	onMount(() => {
		interactive = true;
		bankrolls = serverBankrolls ?? [];
		accounts = serverAccounts ?? [];
		ledger = serverLedger ?? [];
		if (selectedBankrollId === null && serverBankrolls?.[0]) {
			selectedBankrollId = serverBankrolls[0].id;
		}

		if (
			shouldAutoLoadAccountData({
				serverBankrolls,
				serverAccounts,
				serverLedger,
				hasRequestedInitialLoad
			})
		) {
			hasRequestedInitialLoad = true;
			void loadData();
		}
	});

	const tabs = $derived([
		{ id: 'bankrolls', label: 'Bankrolls', count: bankrolls.length },
		{ id: 'accounts', label: 'Bookmaker Accounts', count: accounts.length },
		{ id: 'ledger', label: 'Ledger', count: ledger.length },
		{ id: 'risk', label: 'Risk & limits' }
	]);

	const ledgerCols = [
		{ key: 'created_at', label: 'Date' },
		{ key: 'entry_type', label: 'Type' },
		{ key: 'description', label: 'Description' },
		{ key: 'amount', label: 'Amount' },
		{ key: 'balance_after', label: 'Balance' }
	];

	const ledgerRows = $derived(
		ledger.map((e) => ({
			created_at: new Date(e.created_at).toLocaleDateString(),
			entry_type: e.entry_type.replace('_', ' '),
			description: e.description,
			amount: e.amount > 0 ? `+${e.amount.toFixed(2)}` : e.amount.toFixed(2),
			balance_after: e.balance_after.toFixed(2)
		}))
	);

	const bankrollOptions = $derived(
		bankrolls.map((b) => ({ value: String(b.id), label: b.name }))
	);

	const equityCurveData = $derived(
		ledger.map((entry) => ({
			date: entry.created_at,
			bankroll: entry.balance_after
		}))
	);
</script>

<div class="space-y-6" data-testid="account-panel" data-interactive={interactive ? 'true' : 'false'}>
	{#if loading}
		<Loading message="Loading account data..." />
	{:else if error}
		<div class="p-4  text-sm bg-destructive/10 border border-destructive/30 text-destructive">{error}</div>
		<Button onclick={loadData}>Retry</Button>
	{:else}
		<Tabs bind:activeTab {tabs}>
				{#if activeTab === 'bankrolls'}
				<div class="space-y-4">
					<!-- Equity Curve Chart -->
					{#if equityCurveData.length > 1}
						<Card>
							<div class="p-4">
								<h4 class="font-medium text-foreground mb-4">Equity Curve</h4>
								<EquityCurveChart data={equityCurveData} />
							</div>
						</Card>
					{/if}

					<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
						{#each bankrolls as br (br.id)}
							<Card>
								<div class="space-y-2">
									<div class="flex items-center justify-between">
										<h4 class="font-medium text-foreground">{br.name}</h4>
										<Badge variant={br.type === 'real' ? 'info' : 'default'}>{br.type}</Badge>
									</div>
									<p class="text-2xl font-bold font-mono text-football-green">
										{br.currency} {br.balance.toFixed(2)}
									</p>
									<p class="text-xs text-muted-foreground">
										Initial: {br.currency} {br.initial_balance.toFixed(2)}
									</p>
								</div>
							</Card>
						{/each}

						{#if showNewBankroll}
							<Card>
								<form onsubmit={(e) => { e.preventDefault(); createBankroll(); }} class="space-y-3">
									<h4 class="font-medium text-foreground">New Bankroll</h4>
									<Input label="Name" bind:value={newBankrollName} placeholder="My Bankroll" />
									<Select
										label="Type"
										bind:value={newBankrollType}
										options={[
											{ value: 'paper', label: 'Paper (Virtual)' },
											{ value: 'real', label: 'Real Money' }
										]}
									/>
									<Input label="Initial Balance" type="number" bind:value={newBankrollBalance} />
									<div class="flex space-x-2">
										<Button type="submit" size="sm">Create</Button>
										<Button variant="ghost" size="sm" onclick={() => (showNewBankroll = false)}>Cancel</Button>
									</div>
								</form>
							</Card>
						{/if}
					</div>

					{#if !showNewBankroll}
						<Button onclick={() => (showNewBankroll = true)} variant="secondary">
							+ Add Bankroll
						</Button>
					{/if}
				</div>

			{:else if activeTab === 'accounts'}
				<div class="space-y-4">
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead class="text-xs uppercase bg-muted border-b border-border text-muted-foreground font-sans">
								<tr>
									<th class="px-4 py-3 text-left">Bookmaker</th>
									<th class="px-4 py-3 text-left">Account</th>
									<th class="px-4 py-3 text-left">Balance</th>
									<th class="px-4 py-3 text-left">Currency</th>
								</tr>
							</thead>
							<tbody>
								{#each accounts as acct (acct.id)}
									<tr class="transition-colors duration-200 border-b border-border hover:bg-muted">
										<td class="px-4 py-3 font-medium text-foreground">{acct.bookmaker}</td>
										<td class="px-4 py-3 text-muted-foreground">{acct.account_name}</td>
										<td class="px-4 py-3 font-mono text-football-green">{acct.balance.toFixed(2)}</td>
										<td class="px-4 py-3 font-mono text-muted-foreground">Inherited</td>
									</tr>
								{:else}
									<tr>
										<td colspan="4" class="px-4 py-8 text-center text-muted-foreground">No accounts linked yet</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>

					{#if showNewAccount}
						<Card title="Link Bookmaker Account">
							<form onsubmit={(e) => { e.preventDefault(); createAccount(); }} class="space-y-3">
								<Input label="Bookmaker Name" bind:value={newAccountBookmaker} placeholder="Bet365" />
								<Input label="Account Name" bind:value={newAccountName} placeholder="Main Account" />
								<Input label="Current Balance" type="number" bind:value={newAccountBalance} />
								{#if bankrollOptions.length > 0}
									<Select
										label="Bankroll"
										value={selectedBankrollId ? String(selectedBankrollId) : ''}
										options={bankrollOptions}
										onchange={changeBankroll}
									/>
								{/if}
								<div class="flex space-x-2">
									<Button type="submit" size="sm">Link Account</Button>
									<Button variant="ghost" size="sm" onclick={() => (showNewAccount = false)}>Cancel</Button>
								</div>
							</form>
						</Card>
					{:else}
						<Button onclick={() => (showNewAccount = true)} variant="secondary">
							+ Link Bookmaker Account
						</Button>
					{/if}
				</div>

			{:else if activeTab === 'ledger'}
				<div class="overflow-x-auto">
					<table class="w-full text-sm">
						<thead class="text-xs uppercase bg-muted border-b border-border text-muted-foreground font-sans">
							<tr>
								{#each ledgerCols as col (col.key)}
									<th class="px-4 py-3 text-left">{col.label}</th>
								{/each}
							</tr>
						</thead>
						<tbody>
							{#each ledgerRows as row (String(row.created_at) + row.entry_type + row.amount)}
								<tr class="transition-colors duration-200 border-b border-border hover:bg-muted">
									<td class="px-4 py-3 text-muted-foreground">{row.created_at}</td>
									<td class="px-4 py-3">
										<Badge variant={row.entry_type.includes('won') || row.entry_type === 'deposit' ? 'success' : row.entry_type.includes('lost') || row.entry_type === 'withdrawal' ? 'danger' : 'default'}>
											{row.entry_type}
										</Badge>
									</td>
									<td class="px-4 py-3 text-muted-foreground">{row.description}</td>
									<td class="px-4 py-3 font-mono {row.amount.startsWith('+') ? 'text-football-green' : 'text-destructive'}">
										{row.amount}
									</td>
									<td class="px-4 py-3 font-mono text-muted-foreground">{row.balance_after}</td>
								</tr>
							{:else}
								<tr>
									<td colspan={ledgerCols.length} class="px-4 py-8 text-center text-muted-foreground">No ledger entries yet</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{:else if activeTab === 'risk'}
				<div class="space-y-4">
					{#if bankrolls.length === 0}
						<div class="border border-border bg-muted/40 p-4 text-sm text-foreground">
							Creează mai întâi un bankroll paper pentru a configura limitele de risc.
						</div>
					{:else}
						<Select
							label="Bankroll"
							value={selectedBankrollId ? String(selectedBankrollId) : ''}
							options={bankrollOptions}
							onchange={changeBankroll}
						/>
						{#if selectedBankrollId}
							{#key selectedBankrollId}
								<RiskPolicyPanel bankrollId={selectedBankrollId} />
							{/key}
						{/if}
					{/if}
				</div>
			{/if}
		</Tabs>
	{/if}
</div>
