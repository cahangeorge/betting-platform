<script lang="ts">
	export type StrategyComparisonCandidate = {
		matchId: number;
		match: string;
		league?: string | null;
		market: string;
		selection: string;
		strategyName: string;
		probability: number;
		edge?: number | null;
		ticketEligible?: boolean | null;
		reliability?: string | null;
	};

	type Props = {
		candidates?: StrategyComparisonCandidate[];
		title?: string;
	};

	type ConsensusRow = {
		key: string;
		matchId: number;
		match: string;
		league: string;
		market: string;
		selection: string;
		strategyNames: string[];
		strategyCount: number;
		marketStrategyCount: number;
		agreementPercent: number;
		averageProbability: number;
		minProbability: number;
		maxProbability: number;
		averageEdge: number | null;
		eligibleCount: number;
		reliability: string;
	};

	let { candidates = [], title = 'Consensul modelelor' }: Props = $props();
	const titleId = $props.id();

	const rows = $derived.by(() => {
		const groups = new Map<string, StrategyComparisonCandidate[]>();

		for (const candidate of candidates) {
			if (!Number.isFinite(candidate.probability)) continue;
			const key = `${candidate.matchId}:${candidate.market}:${candidate.selection}`;
			const current = groups.get(key) ?? [];
			current.push(candidate);
			groups.set(key, current);
		}

		const marketTotals = new Map<string, Set<string>>();
		for (const candidate of candidates) {
			if (!Number.isFinite(candidate.probability)) continue;
			const key = `${candidate.matchId}:${candidate.market}`;
			const strategies = marketTotals.get(key) ?? new Set<string>();
			strategies.add(candidate.strategyName);
			marketTotals.set(key, strategies);
		}

		return [...groups.entries()]
			.map(([key, group]): ConsensusRow => {
				const probabilities = group.map((candidate) => candidate.probability);
				const edges = group
					.map((candidate) => candidate.edge)
					.filter((edge): edge is number => typeof edge === 'number' && Number.isFinite(edge));
				const strategyNames = [...new Set(group.map((candidate) => candidate.strategyName))];
				const marketStrategyCount = marketTotals.get(`${group[0].matchId}:${group[0].market}`)?.size ?? strategyNames.length;
				const eligibleCount = group.filter((candidate) => candidate.ticketEligible === true).length;
				const allEligible = eligibleCount === strategyNames.length && strategyNames.length > 0;
				const reliability = allEligible
					? 'Eligibil pe toate modelele'
					: eligibleCount > 0
						? `Eligibil parțial (${eligibleCount}/${strategyNames.length})`
						: 'Blocat sau neverificat';

				return {
					key,
					matchId: group[0].matchId,
					match: group[0].match,
					league: group[0].league || 'Ligă necunoscută',
					market: group[0].market,
					selection: group[0].selection,
					strategyNames,
					strategyCount: strategyNames.length,
					marketStrategyCount,
					agreementPercent: marketStrategyCount > 0 ? Math.round((strategyNames.length / marketStrategyCount) * 100) : 0,
					averageProbability: probabilities.reduce((sum, value) => sum + value, 0) / probabilities.length,
					minProbability: Math.min(...probabilities),
					maxProbability: Math.max(...probabilities),
					averageEdge: edges.length > 0 ? edges.reduce((sum, value) => sum + value, 0) / edges.length : null,
					eligibleCount,
					reliability
				};
			})
			.sort((a, b) => b.agreementPercent - a.agreementPercent || b.averageProbability - a.averageProbability);
	});

	function formatProbability(value: number): string {
		return `${(value * 100).toFixed(1)}%`;
	}

	function formatPercent(value: number | null): string {
		return value === null ? '—' : `${value.toFixed(1)}%`;
	}

	function marketLabel(market: string): string {
		return (
			{
				'1x2': 'Rezultat final (1X2)',
				btts: 'Ambele marchează',
				ou_2_5: 'Peste / sub 2.5',
				'over_under_2.5': 'Peste / sub 2.5'
			} as Record<string, string>
		)[market] ?? market;
	}
</script>

<section class="border border-border bg-card p-4" aria-labelledby={titleId}>
	<div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
		<div>
			<h2 id={titleId} class="text-base font-semibold text-foreground">{title}</h2>
			<p class="mt-1 max-w-3xl text-sm leading-5 text-muted-foreground">
				Compară direcția modelelor pentru același meci și aceeași piață. Acordul modelelor este un semnal de stabilitate, nu o garanție.
			</p>
		</div>
		<span class="shrink-0 border border-border bg-muted/20 px-2 py-1 text-xs text-muted-foreground">
			{rows.length} {rows.length === 1 ? 'comparație' : 'comparații'}
		</span>
	</div>

	{#if rows.length === 0}
		<div class="mt-4 border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
			Consensul apare după încărcarea predicțiilor pentru cel puțin un meci.
		</div>
	{:else}
		<div class="mt-4 hidden overflow-x-auto border border-border lg:block">
			<table class="w-full min-w-[940px] border-collapse text-left text-sm">
				<caption class="sr-only">Comparația probabilităților și a acordului dintre strategii</caption>
				<thead class="bg-muted">
					<tr>
						<th class="p-3 font-medium">Meci</th>
						<th class="p-3 font-medium">Piață / selecție</th>
						<th class="p-3 font-medium">Acord</th>
						<th class="p-3 text-right font-medium">Prob. medie</th>
						<th class="p-3 text-right font-medium">Interval</th>
						<th class="p-3 text-right font-medium">EV mediu</th>
						<th class="p-3 font-medium">Eligibilitate</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-border">
					{#each rows as row (row.key)}
						<tr class="bg-card align-top hover:bg-muted/30">
							<td class="p-3">
								<p class="font-medium text-foreground">{row.match}</p>
								<p class="mt-1 text-xs text-muted-foreground">{row.league}</p>
							</td>
							<td class="p-3">
								<p class="text-foreground">{marketLabel(row.market)}</p>
								<p class="mt-1 font-medium text-football-gold">{row.selection}</p>
							</td>
							<td class="p-3">
								<div class="flex min-w-28 items-center gap-2">
									<div class="h-2 min-w-16 flex-1 overflow-hidden bg-muted" role="progressbar" aria-label={`Acord modele pentru ${row.match}`} aria-valuemin="0" aria-valuemax="100" aria-valuenow={row.agreementPercent}>
										<div class="h-full bg-football-green" style={`width: ${row.agreementPercent}%`}></div>
									</div>
									<span class="font-mono text-xs text-foreground">{row.strategyCount}/{row.marketStrategyCount}</span>
								</div>
								<p class="mt-1 text-xs text-muted-foreground">{row.strategyNames.join(' · ')}</p>
							</td>
							<td class="p-3 text-right font-mono font-semibold text-foreground">{formatProbability(row.averageProbability)}</td>
							<td class="p-3 text-right font-mono text-muted-foreground">{formatProbability(row.minProbability)}–{formatProbability(row.maxProbability)}</td>
							<td class={`p-3 text-right font-mono ${row.averageEdge !== null && row.averageEdge > 0 ? 'text-football-green' : 'text-muted-foreground'}`}>{formatPercent(row.averageEdge)}</td>
							<td class="p-3 text-xs text-muted-foreground">{row.reliability}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<div class="mt-3 space-y-3 lg:hidden" aria-label="Comparație modele pe mobil">
			{#each rows as row (row.key)}
				<article class="border border-border bg-card p-4">
					<div class="flex items-start justify-between gap-3">
						<div class="min-w-0">
							<h3 class="font-medium text-foreground">{row.match}</h3>
							<p class="mt-1 text-sm text-muted-foreground">{row.league} · {marketLabel(row.market)}</p>
							<p class="mt-1 font-medium text-football-gold">{row.selection}</p>
						</div>
						<span class="shrink-0 border border-border bg-muted/20 px-2 py-1 font-mono text-xs text-foreground">{row.strategyCount}/{row.marketStrategyCount} acord</span>
					</div>
					<div class="mt-4 grid grid-cols-2 gap-3 text-sm">
						<div>
							<p class="text-xs text-muted-foreground">Probabilitate medie</p>
							<p class="mt-1 font-mono font-semibold text-foreground">{formatProbability(row.averageProbability)}</p>
						</div>
						<div>
							<p class="text-xs text-muted-foreground">Interval modele</p>
							<p class="mt-1 font-mono text-foreground">{formatProbability(row.minProbability)}–{formatProbability(row.maxProbability)}</p>
						</div>
						<div>
							<p class="text-xs text-muted-foreground">EV mediu</p>
							<p class={`mt-1 font-mono ${row.averageEdge !== null && row.averageEdge > 0 ? 'text-football-green' : 'text-foreground'}`}>{formatPercent(row.averageEdge)}</p>
						</div>
						<div>
							<p class="text-xs text-muted-foreground">Status</p>
							<p class="mt-1 text-foreground">{row.reliability}</p>
						</div>
					</div>
					<div class="mt-4">
						<div class="flex items-center justify-between gap-2 text-xs text-muted-foreground"><span>Acord între strategii</span><span class="font-mono text-foreground">{row.agreementPercent}%</span></div>
						<div class="mt-2 h-2 overflow-hidden bg-muted" role="progressbar" aria-label={`Acord modele pentru ${row.match}`} aria-valuemin="0" aria-valuemax="100" aria-valuenow={row.agreementPercent}><div class="h-full bg-football-green" style={`width: ${row.agreementPercent}%`}></div></div>
						<p class="mt-2 text-xs leading-5 text-muted-foreground">Modele: {row.strategyNames.join(' · ')}</p>
					</div>
				</article>
			{/each}
		</div>
	{/if}

	<p class="mt-4 border-l-2 border-football-blue pl-3 text-xs leading-5 text-muted-foreground">
		Probabilitatea medie este agregată din strategiile disponibile; nu înlocuiește verificarea cotei, a istoricului sau a corelației dintre meciuri.
	</p>
</section>
