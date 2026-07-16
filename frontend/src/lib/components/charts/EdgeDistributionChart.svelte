<script lang="ts">
	let {
		data
	}: {
		data: { edge: string; count: number }[];
	} = $props();

	const chartData = $derived(data.filter((item) => item.edge && Number.isFinite(item.count) && item.count >= 0));
	const maxCount = $derived(Math.max(1, ...chartData.map((item) => item.count)));
	const total = $derived(chartData.reduce((sum, item) => sum + item.count, 0));
</script>

<div class="h-[200px] w-full">
	{#if chartData.length > 0}
		<div
			class="flex h-full items-stretch gap-1 border border-border/60 bg-muted/10 px-3 pb-2 pt-3 sm:gap-2"
			role="img"
			aria-label={`Distribuția edge-ului pentru ${total} selecții`}
		>
			{#each chartData as item (item.edge)}
				<div class="grid min-w-0 flex-1 grid-rows-[1fr_auto] gap-1">
					<div class="flex min-h-0 flex-col items-center justify-end gap-1">
						<span class="font-mono text-xs font-semibold text-foreground">{item.count}</span>
						<div
							class="w-full min-w-1 border border-football-green/40 bg-football-green/75"
							style={`height: ${Math.max(4, (item.count / maxCount) * 132)}px;`}
							title={`${item.edge}: ${item.count} selecții`}
						></div>
					</div>
					<span class="max-w-full truncate text-center font-mono text-[10px] text-muted-foreground">{item.edge}</span>
				</div>
			{/each}
		</div>
	{:else}
		<div class="flex h-full items-center justify-center border border-dashed border-border/60 bg-muted/20 text-sm text-muted-foreground">
			Distribuția edge-ului nu este încă disponibilă.
		</div>
	{/if}
</div>
