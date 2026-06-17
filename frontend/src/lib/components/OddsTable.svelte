<script lang="ts">
	import type { Match } from '$lib/types';
	import Badge from './ui/Badge.svelte';
	import Button from './ui/Button.svelte';
	import { cn } from '$lib/utils';

	let {
		matches
	}: {
		matches: Match[];
	} = $props();

	let selectedLeague = $state('all');

	const leagues = $derived([...new Set(matches.map((m) => m.league))]);

	const filteredMatches = $derived(
		selectedLeague === 'all'
			? matches
			: matches.filter((m) => m.league === selectedLeague)
	);

	const bookmakers = $derived(
		matches.length > 0
			? [...new Set(matches.flatMap((m) => m.odds.map((o) => o.bookmaker)))]
			: []
	);
</script>

<div class="space-y-4">
	<div class="flex items-center space-x-3 overflow-x-auto pb-2">
		<Button
			variant={selectedLeague === 'all' ? 'primary' : 'secondary'}
			size="sm"
			onclick={() => (selectedLeague = 'all')}
		>
			All Leagues
		</Button>
		{#each leagues as league (league)}
			<Button
				variant={selectedLeague === league ? 'primary' : 'secondary'}
				size="sm"
				class="whitespace-nowrap"
				onclick={() => (selectedLeague = league)}
			>
				{league}
			</Button>
		{/each}
	</div>

	<div class="overflow-x-auto  border border-border">
		<table class="w-full text-sm">
			<thead>
				<tr class="bg-muted">
					<th class="px-3 py-3 text-left text-xs uppercase tracking-wider text-muted-foreground font-sans">Match</th>
					<th class="px-3 py-3 text-left text-xs uppercase tracking-wider text-muted-foreground font-sans">League</th>
					<th class="px-3 py-3 text-center text-xs uppercase tracking-wider text-muted-foreground font-sans">Date</th>
					{#each bookmakers as bm (bm)}
						<th class="px-3 py-3 text-center text-xs uppercase tracking-wider text-muted-foreground font-sans" colspan="3">
							{bm}
						</th>
					{/each}
					<th class="px-3 py-3 text-center text-xs uppercase tracking-wider text-football-green font-sans">
						Best
					</th>
				</tr>
				{#if bookmakers.length > 0}
					<tr class="text-xs text-muted-foreground bg-background">
						<th colspan="3"></th>
						{#each bookmakers as bm (bm)}
							<th class="px-1 py-1 text-center font-normal font-mono">1</th>
							<th class="px-1 py-1 text-center font-normal font-mono">X</th>
							<th class="px-1 py-1 text-center font-normal font-mono">2</th>
						{/each}
						<th class="px-1 py-1 text-center font-normal font-mono text-football-green">1</th>
						<th class="px-1 py-1 text-center font-normal font-mono text-football-gold">X</th>
						<th class="px-1 py-1 text-center font-normal font-mono text-football-blue">2</th>
					</tr>
				{/if}
			</thead>
			<tbody>
				{#each filteredMatches as match (match.id)}
					<tr class="transition-colors duration-200 border-b border-border hover:bg-muted">
						<td class="px-3 py-3">
							<div class="text-foreground font-medium font-sport">{match.home_team}</div>
							<div class="text-muted-foreground">{match.away_team}</div>
						</td>
						<td class="px-3 py-3 text-xs font-mono text-muted-foreground">{match.league}</td>
						<td class="px-3 py-3 text-xs text-center font-mono text-muted-foreground">
							{new Date(match.start_time).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
						</td>
						{#each bookmakers as bm (bm)}
							{@const odds = match.odds.find((o) => o.bookmaker === bm)}
							{@const maxHome = Math.max(...match.odds.map((o) => o.home_odds), 0)}
							{@const maxAway = Math.max(...match.odds.map((o) => o.away_odds), 0)}
							<td class="px-3 py-3 text-center font-mono text-sm {odds && odds.home_odds === maxHome ? 'text-football-green font-semibold' : 'text-foreground'}">
								{odds ? odds.home_odds.toFixed(2) : '-'}
							</td>
							<td class="px-3 py-3 text-center font-mono text-sm text-muted-foreground">
								{odds && odds.draw_odds ? odds.draw_odds.toFixed(2) : '-'}
							</td>
							<td class="px-3 py-3 text-center font-mono text-sm {odds && odds.away_odds === maxAway ? 'text-football-blue font-semibold' : 'text-foreground'}">
								{odds ? odds.away_odds.toFixed(2) : '-'}
							</td>
						{/each}
						<td class="px-3 py-3 text-center font-mono font-bold text-football-green">
							{Math.max(...match.odds.map(o => o.home_odds), 0) > 0 ? Math.max(...match.odds.map(o => o.home_odds), 0).toFixed(2) : '-'}
						</td>
						<td class="px-3 py-3 text-center font-mono font-bold text-football-gold">
							{Math.max(...match.odds.filter(o => o.draw_odds).map(o => o.draw_odds as number), 0) > 0 ? Math.max(...match.odds.filter(o => o.draw_odds).map(o => o.draw_odds as number), 0).toFixed(2) : '-'}
						</td>
						<td class="px-3 py-3 text-center font-mono font-bold text-football-blue">
							{Math.max(...match.odds.map(o => o.away_odds), 0) > 0 ? Math.max(...match.odds.map(o => o.away_odds), 0).toFixed(2) : '-'}
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan={3 + bookmakers.length * 3 + 3} class="px-4 py-12 text-center text-muted-foreground">
							No matches available
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
