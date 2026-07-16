<script lang="ts">
	type RiskTier = {
		id: 'safe' | 'balanced' | 'aggressive';
		label: string;
		legs: number;
		description: string;
		accent: string;
		bar: string;
	};

	type RiskRow = RiskTier & {
		available: boolean | null;
		combinedProbability: number | null;
		fairOdds: number | null;
		barPercent: number;
		availabilityLabel: string;
	};

	export type RiskProbabilityRow = {
		id: string | number;
		label: string;
		probability: number | null;
		source?: string;
		odds?: number | null;
		legs?: number | null;
	};

	type Props = {
		probabilities?: number[];
		probabilityRows?: RiskProbabilityRow[];
		eligibleCandidates?: number;
		uniqueMatches?: number;
		title?: string;
		description?: string;
		display?: 'ladder' | 'rows';
	};

	let {
		probabilities = [],
		probabilityRows = [],
		eligibleCandidates,
		uniqueMatches,
		title = 'Gradaje de risc',
		description = 'Compară rapid numărul de picioare și probabilitatea estimată înainte de generare.',
		display = 'ladder'
	}: Props = $props();
	const titleId = $props.id();

	const tiers: RiskTier[] = [
		{
			id: 'safe',
			label: 'Prudent',
			legs: 1,
			description: 'Un singur meci, expunere minimă',
			accent: 'border-football-green/40 bg-football-green/5',
			bar: 'bg-football-green'
		},
		{
			id: 'balanced',
			label: 'Echilibrat',
			legs: 2,
			description: 'Două meciuri, compromis între risc și retur',
			accent: 'border-football-gold/40 bg-football-gold/5',
			bar: 'bg-football-gold'
		},
		{
			id: 'aggressive',
			label: 'Agresiv',
			legs: 3,
			description: 'Trei meciuri, probabilitate cumulată mai mică',
			accent: 'border-football-red/40 bg-football-red/5',
			bar: 'bg-football-red'
		}
	];

	const normalizedProbabilityRows = $derived.by((): RiskProbabilityRow[] => {
		if (probabilityRows.length > 0) {
			return probabilityRows.map((row) => ({
				...row,
				probability:
					typeof row.probability === 'number' && Number.isFinite(row.probability)
						? Math.min(1, Math.max(0, row.probability))
						: null
			}));
		}
		return probabilities
			.filter((value) => Number.isFinite(value))
			.map((value, index) => ({
				id: index,
				label: `Intrare ${index + 1}`,
				probability: Math.min(1, Math.max(0, value)),
				source: 'Probabilitate transmisă de analiză'
			} satisfies RiskProbabilityRow));
	});
	const normalizedProbabilities = $derived(
		normalizedProbabilityRows
			.map((row) => row.probability)
			.filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
	);
	const normalizedEligibleCandidates = $derived(
		typeof eligibleCandidates === 'number' && Number.isFinite(eligibleCandidates)
			? Math.max(0, Math.floor(eligibleCandidates))
			: null
	);
	const normalizedUniqueMatches = $derived(
		typeof uniqueMatches === 'number' && Number.isFinite(uniqueMatches)
			? Math.max(0, Math.floor(uniqueMatches))
			: null
	);

	function combinedProbability(legCount: number): number | null {
		const legProbabilities = normalizedProbabilities.slice(0, legCount);
		if (legProbabilities.length < legCount) return null;

		const product = legProbabilities.reduce((result, probability) => result * probability, 1);
		return Math.min(1, Math.max(0, product));
	}

	function formatProbability(value: number | null): string {
		return value === null ? '—' : `${(value * 100).toFixed(1)}%`;
	}

	function formatFairOdds(value: number | null): string {
		if (value === null || value <= 0) return '—';
		return `x${value.toFixed(2)}`;
	}

	const ladderRows = $derived(
		tiers.map((tier): RiskRow => {
			const available =
				normalizedUniqueMatches === null ? null : normalizedUniqueMatches >= tier.legs;
			const probability = available === false ? null : combinedProbability(tier.legs);
			const barPercent = probability === null ? 0 : Math.round(probability * 100);

			return {
				...tier,
				available,
				combinedProbability: probability,
				fairOdds: probability && probability > 0 ? 1 / probability : null,
				barPercent,
				availabilityLabel:
					available === true
						? 'Disponibil'
						: available === false
							? `Blocat · necesită ${tier.legs} ${tier.legs === 1 ? 'meci' : 'meciuri'} unice`
							: 'Așteaptă acoperirea'
			};
		})
	);
</script>

<section class="border border-border bg-card p-4" aria-labelledby={titleId}>
	<div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
		<div>
			<h2 id={titleId} class="text-base font-semibold text-foreground">{title}</h2>
			<p class="mt-1 text-sm leading-5 text-muted-foreground">
				{description}
			</p>
		</div>
		<div class="flex shrink-0 flex-wrap gap-2 text-xs text-muted-foreground">
			{#if normalizedEligibleCandidates !== null}
				<span class="border border-border bg-muted/20 px-2 py-1">
					{normalizedEligibleCandidates} eligibili
				</span>
			{/if}
			{#if normalizedUniqueMatches !== null}
				<span class="border border-border bg-muted/20 px-2 py-1">
					{normalizedUniqueMatches} meciuri unice
				</span>
			{/if}
		</div>
	</div>

	{#if display === 'rows'}
		<div class="mt-4 space-y-2" aria-label="Probabilitate implicită pe bilet">
			{#if normalizedProbabilityRows.length === 0}
				<div class="border border-dashed border-border p-6 text-center text-sm text-muted-foreground">Nu există bilete cu probabilitate disponibilă.</div>
			{:else}
				{#each normalizedProbabilityRows as row (row.id)}
					<article class="min-h-11 border border-border bg-muted/10 p-3">
						<div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(12rem,0.8fr)_auto] sm:items-center">
							<div class="min-w-0">
								<p class="font-medium text-foreground">{row.label}</p>
								<p class="mt-1 text-xs leading-5 text-muted-foreground">{row.source ?? 'Probabilitate implicită din cotă'}</p>
							</div>
							<div>
								<p class="text-xs text-muted-foreground">Probabilitate implicită</p>
								<p class="mt-1 font-mono font-semibold text-foreground">{formatProbability(row.probability)}</p>
							</div>
							<div class="text-left sm:text-right">
								{#if typeof row.odds === 'number' && Number.isFinite(row.odds) && row.odds > 1}<p class="font-mono text-football-gold">x{row.odds.toFixed(2)}</p>{/if}
								{#if typeof row.legs === 'number' && Number.isFinite(row.legs)}<p class="mt-1 text-xs text-muted-foreground">{row.legs} {row.legs === 1 ? 'selecție' : 'selecții'}</p>{/if}
							</div>
						</div>
					</article>
				{/each}
			{/if}
		</div>
		<p class="mt-4 border-l-2 border-football-blue pl-3 text-xs leading-5 text-muted-foreground">
			1 / cotă este o probabilitate implicită de piață și include marja bookmakerului; nu reprezintă probabilitatea modelului și nu este o garanție.
		</p>
	{:else}
	<div class="mt-4 space-y-2" aria-label="Gradaje de risc și probabilitate">
		{#each ladderRows as row (row.id)}
			<article
				class={`min-h-11 border p-3 ${row.accent} ${row.available === false ? 'border-border bg-muted/20' : ''}`}
				aria-label={`${row.label}, ${row.legs} ${row.legs === 1 ? 'meci' : 'meciuri'}, ${row.availabilityLabel}`}
			>
				<div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(14rem,1.2fr)] sm:items-center">
					<div class="min-w-0">
						<div class="flex flex-wrap items-center gap-2">
							<h3 class="font-medium text-foreground">{row.label}</h3>
							<span class="border border-border bg-background/40 px-2 py-0.5 text-xs font-mono text-muted-foreground">
								{row.legs} {row.legs === 1 ? 'meci' : 'meciuri'}
							</span>
							<span class="text-xs font-medium text-muted-foreground">{row.availabilityLabel}</span>
						</div>
						<p class="mt-1 text-sm leading-5 text-muted-foreground">{row.description}</p>
					</div>

					<div class="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
						<div class="min-w-0">
							<p class="text-xs text-muted-foreground">Probabilitate cumulată</p>
							<p class="mt-1 font-mono font-semibold text-foreground">{formatProbability(row.combinedProbability)}</p>
							<div
								class="mt-2 h-2 overflow-hidden bg-muted"
								role="progressbar"
								aria-label={`Probabilitatea estimată pentru ${row.label}`}
								aria-valuemin="0"
								aria-valuemax="100"
								aria-valuenow={row.barPercent}
							>
								<div class={`h-full ${row.bar}`} style={`width: ${row.barPercent}%`}></div>
							</div>
						</div>
						<div>
							<p class="text-xs text-muted-foreground">Cotă echitabilă</p>
							<p class="mt-1 font-mono font-semibold text-foreground">{formatFairOdds(row.fairOdds)}</p>
						</div>
						<div class="col-span-2 sm:col-span-1">
							<p class="text-xs text-muted-foreground">Compoziție</p>
							<p class="mt-1 font-mono text-foreground">
								{row.combinedProbability === null ? 'Date insuficiente' : `${row.legs} × probabilitate`}
							</p>
						</div>
					</div>
				</div>
			</article>
		{/each}
	</div>

	<p class="mt-4 border-l-2 border-football-blue pl-3 text-xs leading-5 text-muted-foreground">
		Estimarea cumulată înmulțește probabilitățile individuale și presupune că meciurile sunt independente.
		Corelațiile dintre selecții, marja bookmakerului și calitatea datelor pot schimba rezultatul real.
	</p>
	{/if}
</section>
