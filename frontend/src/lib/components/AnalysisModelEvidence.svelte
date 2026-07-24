<script lang="ts">
	import { Activity, AlertTriangle, Grid3X3, Info } from 'lucide-svelte';
	import type { PredictionCalibrationReport, PredictionScoreGridItem } from '$lib/types';
	import Badge from './ui/Badge.svelte';

	let {
		calibration,
		calibrationLoading = false,
		calibrationError = '',
		scoreRows = [],
		scoreGridLoading = false,
		scoreGridError = ''
	}: {
		calibration: PredictionCalibrationReport | null;
		calibrationLoading?: boolean;
		calibrationError?: string;
		scoreRows?: PredictionScoreGridItem[];
		scoreGridLoading?: boolean;
		scoreGridError?: string;
	} = $props();

	let selectedScoreKey = $state('');
	const selectedScore = $derived(
		scoreRows.find((row) => scoreKey(row) === selectedScoreKey) ?? scoreRows[0] ?? null
	);
	const grid = $derived(selectedScore?.cells ?? []);
	const strongestCell = $derived(selectedScore?.top_scores[0] ?? null);
	const goalRange = $derived(
		Array.from({ length: (selectedScore?.max_displayed_goals ?? 5) + 1 }, (_, index) => index)
	);

	function scoreKey(row: PredictionScoreGridItem): string {
		return `${row.source_run_id ?? 'run'}-${row.match_id}-${row.model_type}`;
	}

	function percent(value: number): string {
		return `${(value * 100).toFixed(1)}%`;
	}

	function calibrationTone(gap: number): string {
		if (gap <= 0.03) return 'text-football-green';
		if (gap <= 0.08) return 'text-football-gold';
		return 'text-football-red';
	}

	function unavailableReason(reason: string | null): string {
		if (reason === 'score_grid_not_persisted_for_prediction') {
			return 'Acest run a fost creat înainte ca grila de scor să fie salvată.';
		}
		if (reason === 'score_grid_payload_invalid') {
			return 'Grila salvată pentru acest run nu poate fi afișată în siguranță.';
		}
		return 'Grila de scor nu este disponibilă pentru acest run.';
	}
</script>

<section class="border border-border bg-card p-3 sm:p-4" aria-labelledby="model-evidence-heading">
	<div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
		<div>
			<p class="text-xs font-semibold uppercase tracking-wide text-football-blue">Calitatea probabilității</p>
			<h3 id="model-evidence-heading" class="mt-1 text-lg font-semibold text-foreground">Calibrare și scenarii de scor</h3>
			<p class="mt-1 max-w-3xl text-sm leading-5 text-muted-foreground">Compară încrederea declarată cu frecvența observată și inspectează scenarii de scor fără a transforma automat scorul corect într-o selecție de bilet.</p>
		</div>
		<Badge variant="info">Analiză · nu recomandare</Badge>
	</div>

	<div class="mt-4 grid min-w-0 gap-4 xl:grid-cols-2">
		<div class="min-w-0 border border-border bg-background p-3 sm:p-4">
			<div class="flex items-start gap-2"><Activity class="mt-0.5 size-5 shrink-0 text-football-green" aria-hidden="true" /><div><h4 class="font-semibold text-foreground">Calibrare pe model și piață</h4><p class="mt-1 text-xs leading-5 text-muted-foreground">ECE mai mic înseamnă că probabilitatea declarată urmărește mai bine frecvența reală.</p></div></div>
			{#if calibrationLoading}
				<p class="mt-4 border border-border bg-card p-3 text-sm text-muted-foreground" role="status">Se calculează calibrarea rezultatelor rezolvate...</p>
			{:else if calibrationError}
				<p class="mt-4 border border-football-gold/40 bg-football-gold/10 p-3 text-sm text-foreground" role="status">{calibrationError}</p>
			{:else if !calibration || calibration.groups.length === 0}
				<div class="mt-4 flex gap-2 border border-border bg-card p-3 text-sm text-muted-foreground"><Info class="mt-0.5 size-4 shrink-0" aria-hidden="true" /><p>Nu există încă suficiente predicții cu rezultat final pentru acest run. Matricea se va popula după rezolvare.</p></div>
			{:else}
				<p class="mt-4 text-xs text-muted-foreground">{calibration.resolved_predictions} predicții rezolvate în run-urile curente</p>
				<div class="mt-3 space-y-3">
					{#each calibration.groups as group, groupIndex (`${group.source_run_id ?? 'all'}-${group.model_type}-${group.market}-${groupIndex}`)}
						<details class="border border-border bg-card">
							<summary class="flex min-h-12 cursor-pointer list-none flex-wrap items-center justify-between gap-2 px-3 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
								<span><span class="block text-sm font-medium text-foreground">{group.model_type} · {group.market}</span><span class="mt-1 block text-xs text-muted-foreground">{group.source_run_id ? `run #${group.source_run_id} · ` : ''}{group.resolved_predictions} rezultate · acuratețe {percent(group.accuracy)}</span></span>
								<span class={`font-mono text-xs ${calibrationTone(group.expected_calibration_error)}`}>ECE {percent(group.expected_calibration_error)}</span>
							</summary>
							<div class="border-t border-border p-3">
								<div class="grid grid-cols-3 gap-2 text-xs"><div><p class="text-muted-foreground">Brier</p><p class="mt-1 font-mono text-foreground">{group.brier_score.toFixed(3)}</p></div><div><p class="text-muted-foreground">Log loss</p><p class="mt-1 font-mono text-foreground">{group.log_loss.toFixed(3)}</p></div><div><p class="text-muted-foreground">ECE</p><p class={`mt-1 font-mono ${calibrationTone(group.expected_calibration_error)}`}>{percent(group.expected_calibration_error)}</p></div></div>
								<div class="mt-4 grid grid-cols-5 gap-1 sm:grid-cols-10" aria-label={`Grafic de calibrare ${group.model_type} ${group.market}`}>
									{#each group.buckets as bucket (`${bucket.lower_bound}-${bucket.upper_bound}`)}
										<div class="min-w-0 text-center" title={`${percent(bucket.mean_predicted_probability)} estimat, ${percent(bucket.observed_frequency)} observat, ${bucket.samples} mostre`}>
											<div class="relative mx-auto flex h-20 w-full max-w-8 items-end justify-center gap-px border-b border-border bg-muted/20">
												<span class="w-1.5 bg-football-blue" style={`height:${Math.max(2, bucket.mean_predicted_probability * 100)}%`} aria-hidden="true"></span>
												<span class="w-1.5 bg-football-green" style={`height:${Math.max(2, bucket.observed_frequency * 100)}%`} aria-hidden="true"></span>
											</div>
											<p class="mt-1 truncate font-mono text-[10px] text-muted-foreground">{Math.round(bucket.upper_bound * 100)}</p>
											<span class="sr-only">Estimat {percent(bucket.mean_predicted_probability)}, observat {percent(bucket.observed_frequency)}, {bucket.samples} mostre</span>
										</div>
									{/each}
								</div>
								<p class="mt-2 text-[11px] text-muted-foreground"><span class="text-football-blue">■ estimat</span> · <span class="text-football-green">■ observat</span></p>
							</div>
						</details>
					{/each}
				</div>
			{/if}
		</div>

		<div class="min-w-0 border border-border bg-background p-3 sm:p-4">
			<div class="flex items-start gap-2"><Grid3X3 class="mt-0.5 size-5 shrink-0 text-football-gold" aria-hidden="true" /><div><h4 class="font-semibold text-foreground">Grilă de scor salvată</h4><p class="mt-1 text-xs leading-5 text-muted-foreground">Scenarii persistate odată cu predicția, fără recalculare în browser și fără transfer către generatorul de bilete.</p></div></div>
			{#if scoreGridLoading}
				<p class="mt-4 border border-border bg-card p-3 text-sm text-muted-foreground" role="status">Se încarcă grilele de scor ale run-urilor curente...</p>
			{:else if scoreGridError && scoreRows.length === 0}
				<p class="mt-4 border border-football-gold/40 bg-football-gold/10 p-3 text-sm text-foreground" role="status">{scoreGridError}</p>
			{:else if scoreRows.length === 0}
				<div class="mt-4 flex gap-2 border border-border bg-card p-3 text-sm text-muted-foreground"><Info class="mt-0.5 size-4 shrink-0" aria-hidden="true" /><p>Run-ul nu expune încă goluri așteptate pentru o grilă de scor.</p></div>
			{:else}
				<label for="score-grid-match" class="mt-4 block text-sm font-medium text-foreground">Meci analizat</label>
				<select id="score-grid-match" class="mt-1 min-h-11 w-full min-w-0 border border-input bg-card px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring" bind:value={selectedScoreKey}>
					{#each scoreRows as row (scoreKey(row))}<option value={scoreKey(row)}>{row.home_team} – {row.away_team} · {row.model_type}{row.source_run_id ? ` · run #${row.source_run_id}` : ''}</option>{/each}
				</select>
				{#if selectedScore}
					<div class="mt-3 flex flex-wrap gap-2 text-xs"><Badge variant="info">{selectedScore.source_markets.join(', ') || 'piețe nespecificate'}</Badge>{#if selectedScore.available && selectedScore.home_expected_goals !== null && selectedScore.away_expected_goals !== null}<Badge variant="neutral">xG gazde {selectedScore.home_expected_goals.toFixed(2)}</Badge><Badge variant="neutral">xG oaspeți {selectedScore.away_expected_goals.toFixed(2)}</Badge>{#if strongestCell}<Badge variant="warning">vârf {strongestCell.home_goals}–{strongestCell.away_goals} · {percent(strongestCell.probability)}</Badge>{/if}{/if}</div>
					{#if !selectedScore.available}
						<div class="mt-3 flex gap-2 border border-border bg-card p-3 text-sm text-muted-foreground"><Info class="mt-0.5 size-4 shrink-0" aria-hidden="true" /><p>{unavailableReason(selectedScore.unavailable_reason)} Predicțiile rămân vizibile în analiză.</p></div>
					{:else}
					<div class="mt-3 overflow-x-auto" role="region" aria-label={`Grilă probabilități scor pentru ${selectedScore.home_team} versus ${selectedScore.away_team}`}>
						<div class="grid min-w-[17rem] gap-px bg-border text-center text-[10px] sm:text-xs" style={`grid-template-columns: repeat(${goalRange.length + 1}, minmax(2.25rem, 1fr))`}>
							<div class="bg-card p-1.5 text-muted-foreground">G\O</div>
							{#each goalRange as away (away)}<div class="bg-card p-1.5 font-mono text-muted-foreground">{away}</div>{/each}
							{#each goalRange as home (home)}
								<div class="bg-card p-1.5 font-mono text-muted-foreground">{home}</div>
								{#each goalRange as away (away)}
									{@const cell = grid.find((item) => item.home_goals === home && item.away_goals === away)}
									<div class={`p-1.5 font-mono ${cell === strongestCell ? 'bg-football-gold/30 text-foreground' : 'bg-background text-muted-foreground'}`} title={`${home}-${away}: ${cell ? percent(cell.probability) : '—'}`}>{cell ? `${(cell.probability * 100).toFixed(0)}%` : '—'}</div>
								{/each}
							{/each}
						</div>
					</div>
					<p class="mt-2 text-[11px] text-muted-foreground">Masă probabilistică afișată: {selectedScore.displayed_probability_mass === null ? '—' : percent(selectedScore.displayed_probability_mass)} · {selectedScore.prediction_ids.length} predicții sursă.</p>
					<div class="mt-3 flex gap-2 border border-football-gold/30 bg-football-gold/10 p-3 text-xs leading-5 text-muted-foreground"><AlertTriangle class="mt-0.5 size-4 shrink-0 text-football-gold" aria-hidden="true" /><p>Snapshot explicativ produs de modelul {selectedScore.model_type}. Probabilitățile sunt afișate exact cum au fost persistate de backend; interfața nu le recalculează și nu le trimite în generatorul de bilete.</p></div>
					{/if}
				{/if}
			{/if}
		</div>
	</div>
</section>
