<script lang="ts">
	let {
		data
	}: {
		data: { bookmaker: string; odds: number }[];
	} = $props();

	const validData = $derived.by(() => {
		const bestByBookmaker = new Map<string, { bookmaker: string; odds: number }>();

		for (const item of data) {
			if (!item.bookmaker || !Number.isFinite(item.odds) || item.odds <= 0) continue;

			const existing = bestByBookmaker.get(item.bookmaker);
			if (!existing || item.odds > existing.odds) {
				bestByBookmaker.set(item.bookmaker, item);
			}
		}

		return Array.from(bestByBookmaker.values());
	});

	const maxOdds = $derived(validData.length > 0 ? Math.max(...validData.map((d) => d.odds)) : 0);

	const chartData = $derived(
		validData.map((d) => ({
			...d,
			isBest: d.odds === maxOdds
		}))
	);
</script>

<div class="w-full" style="height: 200px;">
	{#if chartData.length > 0}
		<div
			class="flex h-full items-end gap-2 rounded border border-border/60 bg-muted/20 p-3"
			aria-label="Odds comparison by bookmaker"
		>
			{#each chartData as item (item.bookmaker)}
				<div class="flex min-w-0 flex-1 flex-col items-center gap-1">
					<div
						class="flex w-full items-start justify-center rounded-t border border-football-blue/30 px-0.5 pt-1 text-[10px] font-semibold text-background"
						class:bg-football-green={item.isBest}
						class:bg-football-blue={!item.isBest}
						style={`height: ${Math.max(12, (item.odds / (maxOdds || 1)) * 140)}px;`}
						title={`${item.bookmaker}: ${item.odds.toFixed(2)}`}
					>
						<span>{item.odds.toFixed(2)}</span>
					</div>
					<span class="max-w-full truncate text-[10px] text-muted-foreground">{item.bookmaker}</span>
				</div>
			{/each}
		</div>
	{:else}
		<div
			class="flex h-full items-center justify-center rounded border border-border/60 bg-muted/20 text-xs text-muted-foreground"
		>
			No odds to compare
		</div>
	{/if}
</div>
