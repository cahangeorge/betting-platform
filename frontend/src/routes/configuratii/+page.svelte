<script lang="ts">
	import { page } from '$app/stores';
	import { ApiClientError } from '$lib/api/client';
	import { strategiesApi } from '$lib/api/strategies';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Input from '$lib/components/ui/Input.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Loading from '$lib/components/Loading.svelte';
	import type { Strategy, StrategyCreateRequest } from '$lib/types';
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';

	const modelOptions = [
		{ value: 'poisson', label: 'Poisson' },
		{ value: 'dixon_coles', label: 'Dixon-Coles' },
		{ value: 'bivariate_poisson', label: 'Bivariate Poisson' },
		{ value: 'ensemble', label: 'Ensemble' }
	];

	const activeOptions = [
		{ value: 'true', label: 'Active' },
		{ value: 'false', label: 'Inactive' }
	];

	let strategies = $state<Strategy[]>([]);
	let loading = $state(true);
	let saving = $state(false);
	let duplicatingId = $state<number | null>(null);
	let error = $state('');
	let formError = $state('');
	let notice = $state('');
	const isAdmin = $derived(Boolean($page.data.user?.is_admin));

	let editingStrategyId = $state<number | null>(null);
	let name = $state('');
	let modelType = $state('poisson');
	let description = $state('');
	let parametersText = $state('{}');
	let weightsText = $state('{}');
	let activeValue = $state('true');

	const activeStrategies = $derived(strategies.filter((strategy) => strategy.is_active).length);
	const formTitle = $derived(editingStrategyId ? 'Edit strategy' : 'Create strategy');

	function formatJson(value: Record<string, unknown> | null | undefined): string {
		return JSON.stringify(value ?? {}, null, 2);
	}

	function parseJsonObject(label: string, value: string): Record<string, unknown> | null {
		const trimmed = value.trim();
		if (!trimmed) return {};
		const parsed = JSON.parse(trimmed) as unknown;
		if (parsed === null || Array.isArray(parsed) || typeof parsed !== 'object') {
			throw new Error(`${label} must be a JSON object`);
		}
		return parsed as Record<string, unknown>;
	}

	function resetForm() {
		editingStrategyId = null;
		name = '';
		modelType = 'poisson';
		description = '';
		parametersText = '{}';
		weightsText = '{}';
		activeValue = 'true';
		formError = '';
	}

	function editStrategy(strategy: Strategy) {
		if (!isAdmin) return;
		editingStrategyId = strategy.id;
		name = strategy.name;
		modelType = strategy.model_type;
		description = strategy.description ?? '';
		parametersText = formatJson(strategy.parameters);
		weightsText = formatJson(strategy.weights);
		activeValue = String(strategy.is_active);
		formError = '';
		notice = '';
	}

	async function loadStrategies() {
		loading = true;
		error = '';
		try {
			strategies = await strategiesApi.list();
		} catch (err) {
			strategies = [];
			error = err instanceof ApiClientError ? err.message : 'Failed to load strategies';
		} finally {
			loading = false;
		}
	}

	async function saveStrategy() {
		if (!isAdmin) return;
		if (!name.trim()) {
			formError = 'Name is required';
			return;
		}

		saving = true;
		formError = '';
		notice = '';
		try {
			const parameters = parseJsonObject('Parameters', parametersText);
			const weights = parseJsonObject('Weights', weightsText);
			const payload: StrategyCreateRequest = {
				name: name.trim(),
				model_type: modelType,
				description: description.trim() || undefined,
				parameters: parameters ?? {},
				weights,
				is_active: activeValue === 'true'
			};

			if (editingStrategyId) {
				const updated = await strategiesApi.update(editingStrategyId, payload);
				strategies = strategies.map((strategy) =>
					strategy.id === updated.id ? updated : strategy
				);
				notice = 'Strategy updated.';
			} else {
				const created = await strategiesApi.create(payload);
				strategies = [created, ...strategies];
				notice = 'Strategy created.';
			}
			resetForm();
		} catch (err) {
			formError = err instanceof Error ? err.message : 'Failed to save strategy';
		} finally {
			saving = false;
		}
	}

	async function duplicateStrategy(strategy: Strategy) {
		if (!isAdmin) return;
		duplicatingId = strategy.id;
		formError = '';
		notice = '';
		try {
			const copy = await strategiesApi.duplicate(strategy.id, `Copy of ${strategy.name}`);
			strategies = [copy, ...strategies];
			notice = 'Strategy duplicated with copied configuration.';
		} catch (err) {
			formError = err instanceof ApiClientError ? err.message : 'Failed to duplicate strategy';
		} finally {
			duplicatingId = null;
		}
	}

	onMount(() => {
		void loadStrategies();
	});
</script>

<div class="space-y-6" transition:fade={{ duration: 200 }}>
	<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
		<div>
			<h1 class="font-sport text-2xl font-extrabold text-foreground">CONFIGURATII</h1>
			<p class="mt-1 text-muted-foreground">Manage prediction strategies and reusable model configuration.</p>
		</div>
		<Button variant="secondary" onclick={loadStrategies} disabled={loading}>Refresh</Button>
	</div>

	<div class="grid gap-4 md:grid-cols-3">
		<Card>
			<p class="text-xs uppercase tracking-wider text-muted-foreground">Strategies</p>
			<p class="font-mono text-2xl font-bold text-foreground">{strategies.length}</p>
		</Card>
		<Card>
			<p class="text-xs uppercase tracking-wider text-muted-foreground">Active</p>
			<p class="font-mono text-2xl font-bold text-football-green">{activeStrategies}</p>
		</Card>
		<Card>
			<p class="text-xs uppercase tracking-wider text-muted-foreground">Duplicate support</p>
			<p class="mt-2 text-sm text-muted-foreground">Backend duplicate endpoint keeps copies consistent with API validation.</p>
		</Card>
	</div>

	{#if error}
		<div class="border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive" role="alert">
			{error}. Strategy APIs may be unavailable in this environment.
		</div>
	{/if}

	{#if notice}
		<div class="border border-football-green/30 bg-football-green/10 p-4 text-sm text-football-green" role="status">
			{notice}
		</div>
	{/if}

	{#if !isAdmin}
		<div class="border border-football-gold/40 bg-football-gold/10 p-4 text-sm text-foreground" role="status">
			Catalogul de strategii este disponibil doar pentru consultare. Doar administratorii pot crea, edita sau duplica strategii globale.
		</div>
	{/if}

	<div class={isAdmin ? 'grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]' : 'grid gap-6'}>
		<div class="space-y-3">
			{#if loading}
				<Loading message="Loading strategies..." />
			{:else if strategies.length === 0}
				<Card>
					<div class="py-12 text-center">
						<h2 class="text-base font-semibold text-foreground">No strategies configured</h2>
						<p class="mt-2 text-sm text-muted-foreground">Create a strategy to reuse model parameters from Predict.</p>
					</div>
				</Card>
			{:else}
				{#each strategies as strategy (strategy.id)}
					<Card>
						<div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
							<div class="min-w-0 space-y-2">
								<div class="flex flex-wrap items-center gap-2">
									<h2 class="text-lg font-semibold text-foreground">{strategy.name}</h2>
									<Badge variant={strategy.is_active ? 'success' : 'neutral'}>
										{strategy.is_active ? 'active' : 'inactive'}
									</Badge>
									<Badge variant="info">{strategy.model_type}</Badge>
								</div>
								<p class="text-sm text-muted-foreground">
									{strategy.description || 'No description provided.'}
								</p>
								<div class="grid gap-3 text-xs text-muted-foreground sm:grid-cols-2">
									<div class="border border-border bg-background p-3">
										<p class="mb-1 font-semibold uppercase tracking-wide">Parameters</p>
										<pre class="max-h-28 overflow-auto whitespace-pre-wrap font-mono">{formatJson(strategy.parameters)}</pre>
									</div>
									<div class="border border-border bg-background p-3">
										<p class="mb-1 font-semibold uppercase tracking-wide">Weights</p>
										<pre class="max-h-28 overflow-auto whitespace-pre-wrap font-mono">{formatJson(strategy.weights)}</pre>
									</div>
								</div>
							</div>
							{#if isAdmin}
								<div class="flex shrink-0 gap-2">
									<Button variant="secondary" size="sm" onclick={() => editStrategy(strategy)}>Edit</Button>
									<Button
										variant="ghost"
										size="sm"
										disabled={duplicatingId === strategy.id}
										onclick={() => duplicateStrategy(strategy)}
									>
										{duplicatingId === strategy.id ? 'Duplicating...' : 'Duplicate'}
									</Button>
								</div>
							{/if}
						</div>
					</Card>
				{/each}
			{/if}
		</div>

		{#if isAdmin}
		<Card>
			<form
				class="space-y-4"
				onsubmit={(event) => {
					event.preventDefault();
					void saveStrategy();
				}}
			>
				<div class="flex items-center justify-between gap-3">
					<h2 class="text-lg font-semibold text-foreground">{formTitle}</h2>
					{#if editingStrategyId}
						<Button variant="ghost" size="sm" onclick={resetForm}>New</Button>
					{/if}
				</div>

				{#if formError}
					<div class="border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
						{formError}
					</div>
				{/if}

				<Input label="Name" bind:value={name} placeholder="Conservative value model" />
				<Select label="Model" bind:value={modelType} options={modelOptions} />
				<Select label="Status" bind:value={activeValue} options={activeOptions} />

				<div class="space-y-1.5">
					<label for="strategy-description" class="text-sm font-medium leading-none">Description</label>
					<textarea
						id="strategy-description"
						bind:value={description}
						class="min-h-20 w-full border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
						placeholder="When should this strategy be used?"
					></textarea>
				</div>

				<div class="space-y-1.5">
					<label for="strategy-parameters" class="text-sm font-medium leading-none">Parameters JSON</label>
					<textarea
						id="strategy-parameters"
						bind:value={parametersText}
						class="min-h-32 w-full border border-border bg-background px-3 py-2 font-mono text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
						spellcheck="false"
					></textarea>
				</div>

				<div class="space-y-1.5">
					<label for="strategy-weights" class="text-sm font-medium leading-none">Weights JSON</label>
					<textarea
						id="strategy-weights"
						bind:value={weightsText}
						class="min-h-24 w-full border border-border bg-background px-3 py-2 font-mono text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
						spellcheck="false"
					></textarea>
				</div>

				<Button type="submit" disabled={saving} fullWidth>
					{saving ? 'Saving...' : editingStrategyId ? 'Save changes' : 'Create strategy'}
				</Button>
			</form>
		</Card>
		{/if}
	</div>
</div>
