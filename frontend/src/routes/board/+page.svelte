<script lang="ts">
	import { matchesApi } from '$lib/api/matches';
	import { ApiClientError } from '$lib/api/client';
	import type { Match } from '$lib/types';
	import { onMount } from 'svelte';
	import Ticker from '$lib/components/Ticker.svelte';
	import MatchCard from '$lib/components/MatchCard.svelte';
	import MatchCardSkeleton from '$lib/components/MatchCardSkeleton.svelte';
	import OddsTable from '$lib/components/OddsTable.svelte';
	import Button from '$lib/components/ui/Button.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Loading from '$lib/components/Loading.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import { RefreshCw } from 'lucide-svelte';
	import { fade } from 'svelte/transition';

	let {
		data
	}: {
		data: {
			matches: Match[];
		};
	} = $props();

	let matches = $state<Match[]>([]);
	let hasLocalSnapshot = $state(false);
	let loading = $state(false);
	let error = $state('');
	let activeTab = $state('grid');
	let visibleMatches = $derived(hasLocalSnapshot ? matches : (data.matches ?? []));

	async function refresh() {
		loading = true;
		try {
			matches = await matchesApi.getMatches();
			hasLocalSnapshot = true;
		} catch (err) {
			error = err instanceof ApiClientError ? err.message : 'Failed to refresh';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		const pollInterval = setInterval(refresh, 10000);
		return () => {
			clearInterval(pollInterval);
		};
	});

	const upcomingMatches = $derived(
		visibleMatches.filter((m) => m.status === 'scheduled' || m.status === 'live')
	);

	const tabs = [
		{ id: 'grid', label: 'Match Grid' },
		{ id: 'table', label: 'Odds Table' }
	];
</script>

<div class="space-y-4" transition:fade={{ duration: 200 }}>
	<div>
		<h1 class="text-2xl font-extrabold font-sport text-foreground">ODDS BOARD</h1>
		<p class="mt-1 text-muted-foreground">Public match discovery with live odds snapshots and upcoming fixtures</p>
	</div>

	<Card>
		<div class="flex flex-col gap-4 p-4 md:flex-row md:items-center md:justify-between">
			<div class="space-y-1">
				<p class="text-xs font-semibold uppercase tracking-[0.2em] text-football-green">Public Preview</p>
				<h2 class="text-lg font-semibold text-foreground">Use the board to browse. Sign in to scrape, predict, and place tickets.</h2>
				<p class="text-sm text-muted-foreground">
					Authenticated users get the full workflow on the dashboard: scrape data, run models, build a slip, and place tickets from one shell.
				</p>
			</div>
			<div class="flex flex-wrap gap-2">
				<a href="/login">
					<Button variant="primary">Sign In</Button>
				</a>
				<a href="/signup">
					<Button variant="secondary">Create Account</Button>
				</a>
			</div>
		</div>
	</Card>

	<div class="grid gap-4 md:grid-cols-3">
		<Card>
			<div class="space-y-2 p-4">
				<p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">1. Scrape</p>
				<h3 class="font-semibold text-foreground">Collect fresh markets and match history</h3>
				<p class="text-sm text-muted-foreground">Run the ingestion jobs that populate the rest of the product with real fixtures and odds.</p>
			</div>
		</Card>
		<Card>
			<div class="space-y-2 p-4">
				<p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">2. Predict</p>
				<h3 class="font-semibold text-foreground">Generate selections with model context</h3>
				<p class="text-sm text-muted-foreground">Filter leagues, run strategies, and add the highest-conviction predictions directly to your bet slip.</p>
			</div>
		</Card>
		<Card>
			<div class="space-y-2 p-4">
				<p class="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">3. Ticket</p>
				<h3 class="font-semibold text-foreground">Review selections and place a real ticket</h3>
				<p class="text-sm text-muted-foreground">Use bankroll-backed ticket review instead of manual copy/paste across disconnected screens.</p>
			</div>
		</Card>
	</div>

	<Ticker matches={upcomingMatches} />

	<div class="flex items-center justify-between">
		<Tabs bind:activeTab {tabs} />

		<div class="flex items-center space-x-2">
			{#if loading}
				<div
					class="w-4 h-4  animate-spin border-2 border-border border-t-football-green"
				></div>
			{/if}
			<Button onclick={refresh} variant="ghost" size="sm">
				<RefreshCw class="w-3.5 h-3.5 mr-1.5" />
				Refresh
			</Button>
		</div>
	</div>

	{#if error}
		<div class="p-3 text-sm border bg-destructive/10 border-destructive/30 text-destructive ">{error}</div>
	{/if}

	{#if activeTab === 'grid'}
		{#if loading && matches.length === 0}
			<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
				{#each Array(6) as _, index (index)}
					<MatchCardSkeleton />
				{/each}
			</div>
		{:else if upcomingMatches.length === 0}
			<div class="text-center py-12 text-muted-foreground">
				<p class="text-lg">No matches available</p>
				<p class="text-sm mt-1">Check back later for upcoming fixtures</p>
			</div>
		{:else}
			<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
				{#each upcomingMatches as match (match.id)}
					<MatchCard {match} />
				{/each}
			</div>
		{/if}
	{:else}
		<OddsTable matches={upcomingMatches} />
	{/if}
</div>
