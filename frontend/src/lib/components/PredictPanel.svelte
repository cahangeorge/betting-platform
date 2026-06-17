<script lang="ts">
	import { predictionsApi } from '$lib/api/predictions';
	import { matchesApi } from '$lib/api/matches';
	import { ApiClientError } from '$lib/api/client';
	import type { PredictionRun, PredictionModel, Match, ModelType } from '$lib/types';
	import Button from './ui/Button.svelte';
	import Card from './ui/Card.svelte';
	import Tabs from './ui/Tabs.svelte';
	import Select from './ui/Select.svelte';
	import Input from './ui/Input.svelte';
	import Badge from './ui/Badge.svelte';
	import Loading from './Loading.svelte';
	import { cn } from '$lib/utils';
	import PnLByLeagueChart from './charts/PnLByLeagueChart.svelte';
	import WinRateByModelChart from './charts/WinRateByModelChart.svelte';

	let runs = $state<PredictionRun[]>([]);
	let models = $state<PredictionModel[]>([]);
	let matches = $state<Match[]>([]);
	let loading = $state(true);
	let submitting = $state(false);
	let error = $state('');
	let activeTab = $state('all');
	let pollInterval = $state<ReturnType<typeof setInterval> | null>(null);

	// Run form
	let selectedModel = $state('');
	let selectedMatchIds = $state<number[]>([]);
	let backtestFrom = $state('');
	let backtestTo = $state('');
	let formError = $state('');

	const statusBadge: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
		completed: 'success',
		running: 'warning',
		pending: 'info',
		failed: 'danger'
	};

	const modelAccentClass: Record<string, string> = {
		poisson: 'border-t-football-green',
		bivariate_poisson: 'border-t-football-green',
		dixon_coles: 'border-t-football-blue',
		elo: 'border-t-football-blue',
		xgboost: 'border-t-purple-500',
		ensemble: 'border-t-football-gold'
	};

	async function loadData() {
		try {
			const [r, m, mt] = await Promise.all([
				predictionsApi.getRuns(),
				predictionsApi.getModels(),
				matchesApi.getMatches({ status: 'scheduled' })
			]);
			runs = r;
			models = m;
			matches = mt;
			if (!selectedModel && m.length > 0) selectedModel = m[0].type;
		} catch (err) {
			error = err instanceof ApiClientError ? err.message : 'Failed to load predictions';
		} finally {
			loading = false;
		}
	}

	async function submitRun() {
		if (!selectedModel || selectedMatchIds.length === 0) {
			formError = 'Select a model and at least one match';
			return;
		}
		submitting = true;
		formError = '';
		try {
			const run = await predictionsApi.createRun({
				model_type: selectedModel as ModelType,
				match_ids: selectedMatchIds
			});
			runs = [run, ...runs];
			activeTab = 'all';
		} catch (err) {
			formError = err instanceof ApiClientError ? err.message : 'Failed to start prediction run';
		} finally {
			submitting = false;
		}
	}

	function toggleMatch(id: number) {
		if (selectedMatchIds.includes(id)) {
			selectedMatchIds = selectedMatchIds.filter((m) => m !== id);
		} else {
			selectedMatchIds = [...selectedMatchIds, id];
		}
	}

	// Auto-refresh
	$effect(() => {
		loadData();
		pollInterval = setInterval(loadData, 5000);
		return () => {
			if (pollInterval) clearInterval(pollInterval);
		};
	});

	const tabs = $derived([
		{ id: 'all', label: 'All Runs', count: runs.length },
		{ id: 'new', label: 'Run Prediction' },
		{ id: 'backtest', label: 'Backtest' }
	]);

	const modelOptions = $derived(
		models.map((m) => ({ value: m.type, label: m.name }))
	);

	const matchOptions = $derived(
		matches.map((m) => ({
			value: String(m.id),
			label: `${m.home_team} vs ${m.away_team}`
		}))
	);

	const pnlByLeagueData = $derived(() => {
		const completedRuns = runs.filter((r) => r.status === 'completed' && r.results);
		if (completedRuns.length === 0) return [];
		const leagueMap: Record<string, number> = {};
		for (const run of completedRuns) {
			if (!run.results) continue;
			for (const result of run.results) {
				const league = result.home_team.split(' ')[0];
				if (!leagueMap[league]) leagueMap[league] = 0;
				leagueMap[league] += result.confidence * 10;
			}
		}
		return Object.entries(leagueMap).map(([league, profit]) => ({ league, profit }));
	});

	const winRateByModelData = $derived(() => {
		const completedRuns = runs.filter((r) => r.status === 'completed' && r.results);
		if (completedRuns.length === 0) return [];
		const modelMap: Record<string, { wins: number; total: number }> = {};
		for (const run of completedRuns) {
			if (!run.results) continue;
			if (!modelMap[run.model_type]) modelMap[run.model_type] = { wins: 0, total: 0 };
			modelMap[run.model_type].total += run.results.length;
			modelMap[run.model_type].wins += run.results.filter((r) => r.confidence > 0.7).length;
		}
		return Object.entries(modelMap).map(([model, stats]) => ({
			model,
			winRate: Math.round((stats.wins / stats.total) * 100),
			count: stats.total
		}));
	});
</script>

<div class="space-y-6">
	{#if error}
		<div class="p-4  text-sm bg-destructive/10 border border-destructive/30 text-destructive">{error}</div>
		<Button onclick={loadData}>Retry</Button>
	{/if}

	<Tabs bind:activeTab {tabs}>
		{#if activeTab === 'all'}
			{#if loading && runs.length === 0}
				<Loading message="Loading predictions..." />
			{:else if runs.length === 0}
				<div class="text-center py-12 text-muted-foreground">
					<p class="text-lg mb-2">No prediction runs yet</p>
					<p class="text-sm">Go to Run Prediction to start one</p>
				</div>
			{:else}
				<div class="space-y-4">
					{#each runs as run (run.id)}
						<Card class={cn(modelAccentClass[run.model_type] || 'border-t-football-green', 'p-4')}>
							<div class="flex items-center justify-between mb-3">
								<div class="flex items-center space-x-3">
									<h4 class="font-medium text-foreground">{run.model_type}</h4>
									<Badge variant={statusBadge[run.status] || 'default'}>{run.status}</Badge>
								</div>
								<span class="text-xs text-muted-foreground">{new Date(run.created_at).toLocaleString()}</span>
							</div>

							{#if run.results && run.results.length > 0}
								<div class="overflow-x-auto">
									<table class="w-full text-sm">
										<thead class="text-xs uppercase bg-muted border-b border-border text-muted-foreground font-sans">
											<tr>
												<th class="px-3 py-2 text-left">Match</th>
												<th class="px-3 py-2 text-center">1</th>
												<th class="px-3 py-2 text-center">X</th>
												<th class="px-3 py-2 text-center">2</th>
												<th class="px-3 py-2 text-center">Score</th>
												<th class="px-3 py-2 text-center">Confidence</th>
											</tr>
										</thead>
										<tbody>
											{#each run.results as r (r.match_id)}
												<tr class="transition-colors duration-200 border-b border-border hover:bg-muted">
													<td class="px-3 py-2 text-foreground">{r.home_team} vs {r.away_team}</td>
													<td class="px-3 py-2 text-center font-mono">{(r.home_prob * 100).toFixed(1)}%</td>
													<td class="px-3 py-2 text-center font-mono">{(r.draw_prob * 100).toFixed(1)}%</td>
													<td class="px-3 py-2 text-center font-mono">{(r.away_prob * 100).toFixed(1)}%</td>
													<td class="px-3 py-2 text-center font-mono text-football-green">{r.predicted_score}</td>
													<td class="px-3 py-2 text-center">
														<div class="inline-flex items-center">
															<div class="w-16 h-1.5  bg-muted">
																<div
																	class="h-1.5 "
																	style="width: {r.confidence * 100}%; background: linear-gradient(90deg, hsl(var(--football-green)), hsl(var(--football-blue)));"
																></div>
															</div>
														</div>
													</td>
												</tr>
											{/each}
										</tbody>
									</table>
								</div>
							{:else if run.status === 'running' || run.status === 'pending'}
								<div class="flex items-center space-x-2 text-sm">
									<div class="w-4 h-4 border-2 border-t-transparent animate-spin  border-football-gold"></div>
									<span class="text-football-gold">Running prediction...</span>
								</div>
							{/if}

							{#if run.error}
								<div class="mt-2 p-2 text-xs  bg-destructive/10 text-destructive">{run.error}</div>
							{/if}
						</Card>
					{/each}
				</div>
			{/if}

		{:else if activeTab === 'new'}
			<Card class="p-4 border-t-football-green">
				<h3 class="text-lg font-semibold mb-4 text-foreground">Run Prediction</h3>
				<form onsubmit={(e) => { e.preventDefault(); submitRun(); }} class="space-y-4">
					{#if formError}
						<div class="p-3 text-sm  bg-destructive/10 border border-destructive/30 text-destructive">{formError}</div>
					{/if}

					<Select
						label="Model"
						bind:value={selectedModel}
						options={modelOptions}
					/>

					{#if models.length > 0 && selectedModel}
						{@const model = models.find((m) => m.type === selectedModel)}
						{#if model}
							<p class="text-xs text-muted-foreground">{model.description}</p>
						{/if}
					{/if}

					<div>
						<p class="text-sm font-medium text-foreground mb-1.5">Select Matches</p>
						<div class="max-h-48 overflow-y-auto space-y-2 border border-border  p-3 scroll-thin">
							{#each matches as m (m.id)}
								<label class="flex items-center space-x-3 cursor-pointer p-2  transition-colors duration-200 hover:bg-muted {selectedMatchIds.includes(m.id) ? 'bg-football-green/5' : ''}">
									<input
										type="checkbox"
										checked={selectedMatchIds.includes(m.id)}
										onchange={() => toggleMatch(m.id)}
										class="w-4 h-4 accent-[hsl(var(--football-green))]"
									/>
									<span class="text-sm text-muted-foreground">{m.home_team} vs {m.away_team}</span>
									<span class="text-xs ml-auto text-muted-foreground">{new Date(m.start_time).toLocaleDateString()}</span>
								</label>
							{:else}
								<p class="text-sm text-center py-4 text-muted-foreground">No upcoming matches available</p>
							{/each}
						</div>
					</div>

					<Button type="submit" disabled={submitting || matches.length === 0}>
						{submitting ? 'Starting...' : 'Run Prediction'}
					</Button>
				</form>
			</Card>

		{:else if activeTab === 'backtest'}
			<Card class="p-4 border-t-football-gold">
				<h3 class="text-lg font-semibold mb-4 text-foreground">Backtest</h3>
				<p class="text-sm mb-4 text-muted-foreground">
					Run historical backtests to evaluate model performance against past match results.
				</p>
				<form onsubmit={(e) => { e.preventDefault(); }} class="space-y-4">
					<Select
						label="Model"
						bind:value={selectedModel}
						options={modelOptions}
					/>
					<div class="grid grid-cols-2 gap-4">
						<Input label="From Date" type="date" bind:value={backtestFrom} />
						<Input label="To Date" type="date" bind:value={backtestTo} />
					</div>
					<Button type="submit">Run Backtest</Button>
				</form>

				<!-- Charts -->
				{#if pnlByLeagueData().length > 0}
					<div class="mt-6 space-y-4">
						<h4 class="text-sm font-medium uppercase tracking-wider text-muted-foreground">Performance by League</h4>
						<PnLByLeagueChart data={pnlByLeagueData()} />
					</div>
				{/if}

				{#if winRateByModelData().length > 0}
					<div class="mt-6 space-y-4">
						<h4 class="text-sm font-medium uppercase tracking-wider text-muted-foreground">Win Rate by Model</h4>
						<WinRateByModelChart data={winRateByModelData()} />
					</div>
				{/if}
			</Card>
		{/if}
	</Tabs>
</div>
