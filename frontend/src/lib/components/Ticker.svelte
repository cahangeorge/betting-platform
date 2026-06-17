<script lang="ts">
	import type { Match } from '$lib/types';

	let {
		matches
	}: {
		matches: Match[];
	} = $props();

	let tickerItems = $derived(
		matches
			.filter((m) => m.status === 'scheduled' || m.status === 'live')
			.flatMap((m) => {
				const bestHome = m.odds.length > 0 ? Math.max(...m.odds.map((o) => o.home_odds)) : 0;
				const bestAway = m.odds.length > 0 ? Math.max(...m.odds.map((o) => o.away_odds)) : 0;
				return [
					{ text: `${m.home_team} vs ${m.away_team}`, type: 'match' as const },
					{ text: `${bestHome.toFixed(2)}`, type: 'odds-home' as const },
					{ text: `${bestAway.toFixed(2)}`, type: 'odds-away' as const }
				];
			})
	);

	let displayItems = $derived([...tickerItems, ...tickerItems]);
</script>

{#if matches.length > 0}
	<div class="w-full overflow-hidden border-y border-border py-2 bg-background/80 backdrop-blur-sm">
		<div class="animate-ticker flex items-center space-x-6 whitespace-nowrap">
			{#each displayItems as item, i (i)}
				<span class="flex items-center space-x-2">
					{#if item.type === 'match'}
						<span class="text-sm font-medium font-sport text-foreground">{item.text}</span>
						<span class="text-xs text-border">|</span>
					{:else if item.type === 'odds-home'}
						<span class="text-xs font-mono font-semibold text-football-green">{item.text}</span>
					{:else if item.type === 'odds-away'}
						<span class="text-xs font-mono font-semibold text-football-blue">{item.text}</span>
						<span class="text-border mx-2">&#9670;</span>
					{/if}
				</span>
			{/each}
		</div>
	</div>
{/if}
