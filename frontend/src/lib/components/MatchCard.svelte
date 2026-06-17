<script lang="ts">
	import type { Match } from '$lib/types';
	import Badge from './ui/Badge.svelte';
	import Card from './ui/Card.svelte';
	import OddsComparisonChart from './charts/OddsComparisonChart.svelte';

	let {
		match
	}: {
		match: Match;
	} = $props();

	const bestHomeOdds = $derived(
		match.odds.length > 0 ? Math.max(...match.odds.map((o) => o.home_odds)) : 0
	);
	const bestDrawOdds = $derived(
		match.odds.length > 0 ? Math.max(...match.odds.map((o) => o.draw_odds ?? 0)) : 0
	);
	const bestAwayOdds = $derived(
		match.odds.length > 0 ? Math.max(...match.odds.map((o) => o.away_odds)) : 0
	);

	const bestBookmaker = $derived(
		match.odds.length > 0
			? match.odds.reduce((a, b) => (a.home_odds > b.home_odds ? a : b)).bookmaker
			: ''
	);

	const matchDate = $derived(new Date(match.start_time).toLocaleDateString('en-GB', {
		weekday: 'short',
		day: 'numeric',
		month: 'short',
		hour: '2-digit',
		minute: '2-digit'
	}));

	const statusVariant: Record<string, 'live' | 'success' | 'warning' | 'danger' | 'info'> = {
		scheduled: 'info',
		live: 'live',
		finished: 'success',
		postponed: 'warning',
		cancelled: 'danger'
	};

	const statusBorderClass: Record<string, string> = {
		scheduled: 'border-t-football-blue',
		live: 'border-t-football-green',
		finished: 'border-t-border',
		postponed: 'border-t-football-gold',
		cancelled: 'border-t-destructive'
	};
</script>

<Card class="p-4 {statusBorderClass[match.status] || 'border-t-border'}" interactive aria-label="{match.home_team} vs {match.away_team}, {match.league}, {match.status}">
	<div class="flex items-center justify-between mb-3">
		<div class="flex items-center space-x-2">
			<span class="text-xs font-mono text-muted-foreground">{match.league}</span>
			<Badge variant={statusVariant[match.status] || 'default'}>{match.status}</Badge>
			{#if match.status === 'live'}
				<span class="relative flex h-2 w-2">
					<span class="animate-ping absolute inline-flex h-full w-full  opacity-75 bg-football-green"></span>
					<span class="relative inline-flex  h-2 w-2 bg-football-green"></span>
				</span>
			{/if}
		</div>
		<span class="text-xs font-mono text-muted-foreground">{matchDate}</span>
	</div>

	<div class="space-y-2">
		<div class="flex items-center justify-between">
			<div class="flex items-center space-x-2">
				<div class="w-6 h-6 flex items-center justify-center text-[10px] font-bold  bg-muted text-football-green border border-border">
					H
				</div>
				<span class="text-sm font-medium font-sport text-foreground">{match.home_team}</span>
			</div>
			{#if match.home_score !== null}
				<span class="text-lg font-bold font-mono text-foreground">{match.home_score}</span>
			{/if}
			<div class="flex items-center space-x-1">
				{#if bestHomeOdds > 0}
					<span class="text-sm font-mono font-semibold px-2 py-0.5  bg-football-green/10 text-football-green border border-football-green/20">
						{bestHomeOdds.toFixed(2)}
					</span>
				{/if}
			</div>
		</div>

		<div class="flex items-center justify-between">
			<div class="flex items-center space-x-2">
				<div class="w-6 h-6 flex items-center justify-center text-[10px] font-bold  bg-muted text-football-blue border border-border">
					A
				</div>
				<span class="text-sm font-medium font-sport text-foreground">{match.away_team}</span>
			</div>
			{#if match.away_score !== null}
				<span class="text-lg font-bold font-mono text-foreground">{match.away_score}</span>
			{/if}
			<div class="flex items-center space-x-1">
				{#if bestAwayOdds > 0}
					<span class="text-sm font-mono font-semibold px-2 py-0.5  bg-football-blue/10 text-football-blue border border-football-blue/20">
						{bestAwayOdds.toFixed(2)}
					</span>
				{/if}
			</div>
		</div>

		{#if match.odds.length > 1}
			<div class="pt-2 border-t border-border">
				<p class="text-xs font-mono text-muted-foreground">Best odds from <span class="text-football-green">{bestBookmaker}</span></p>
				{#if match.odds.length > 2}
					<div class="mt-2">
						<div class="text-xs uppercase tracking-wider mb-2 text-muted-foreground">Odds Comparison</div>
						<OddsComparisonChart data={match.odds.map(o => ({ bookmaker: o.bookmaker, odds: o.home_odds }))} />
					</div>
				{/if}
			</div>
		{/if}
	</div>
</Card>
