<script lang="ts">
	import { onMount } from 'svelte';
	import {
		AlertTriangle,
		CheckCircle2,
		CircleDashed,
		Globe2,
		LoaderCircle,
		RefreshCw,
		Search,
		ShieldCheck,
		XCircle
	} from 'lucide-svelte';
	import { catalogApi } from '$lib/api/catalog';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Select } from '$lib/components/ui/select';
	import type {
		Country,
		FootballCatalogDiscoveryValidationResponse,
		LeagueInfo
	} from '$lib/types';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	let countries = $state<Country[]>([]);
	let selectedCountries = $state<string[]>([]);
	let countryQuery = $state('');
	let isLoading = $state(true);
	let isRunning = $state(false);
	let errorMessage = $state<string | null>(null);
	let result = $state<FootballCatalogDiscoveryValidationResponse | null>(null);
	let maxAttempts = $state(3);
	let batchSize = $state(20);
	const maxSelectedCountries = 20;

	const isAdmin = $derived(Boolean(data.user?.is_admin));
	const filteredCountries = $derived(
		countries.filter((item) =>
			item.country.toLocaleLowerCase('ro-RO').includes(countryQuery.trim().toLocaleLowerCase('ro-RO'))
		)
	);
	const catalogRows = $derived.by(() => {
		const selected = new Set(selectedCountries);
		return countries
			.filter((country) => selected.size === 0 || selected.has(country.country))
			.flatMap((country) =>
				country.leagues.map((league) => ({ country: country.country, league }))
			);
	});
	const availableCount = $derived(
		catalogRows.filter(({ league }) => (league.status ?? 'available') === 'available').length
	);
	const pendingCount = $derived(
		catalogRows.filter(({ league }) =>
			['validation_pending', 'validation_passed'].includes(league.status ?? '')
		).length
	);
	const unavailableCount = $derived(
		catalogRows.filter(({ league }) => league.status === 'unavailable').length
	);

	onMount(() => {
		void loadCatalog();
	});

	async function loadCatalog(showLoading = true) {
		if (showLoading) isLoading = true;
		errorMessage = null;
		try {
			countries = (await catalogApi.getAllLeagues()).sort((a, b) =>
				a.country.localeCompare(b.country, 'ro-RO')
			);
		} catch (error) {
			errorMessage = error instanceof Error ? error.message : 'Catalogul nu a putut fi încărcat.';
		} finally {
			if (showLoading) isLoading = false;
		}
	}

	function toggleCountry(country: string) {
		if (!selectedCountries.includes(country) && selectedCountries.length >= maxSelectedCountries) return;
		selectedCountries = selectedCountries.includes(country)
			? selectedCountries.filter((item) => item !== country)
			: [...selectedCountries, country];
	}

	function selectAllVisible() {
		const remaining = maxSelectedCountries - selectedCountries.length;
		const additions = filteredCountries
			.map((item) => item.country)
			.filter((country) => !selectedCountries.includes(country))
			.slice(0, remaining);
		selectedCountries = [...selectedCountries, ...additions];
	}

	async function runDiscoveryAndValidation() {
		if (!isAdmin || selectedCountries.length === 0 || isRunning) return;
		isRunning = true;
		errorMessage = null;
		result = null;
		try {
			result = await catalogApi.discoverAndValidate(
				selectedCountries,
				maxAttempts,
				batchSize
			);
			await loadCatalog(false);
		} catch (error) {
			errorMessage = error instanceof Error ? error.message : 'Fluxul nu a putut fi finalizat.';
		} finally {
			isRunning = false;
		}
	}

	function statusMeta(league: LeagueInfo): { label: string; className: string } {
		switch (league.status) {
			case 'validation_pending':
			case 'validation_passed':
				return {
					label: 'În verificare',
					className:
						'border-[hsl(var(--status-warning-border))] bg-[hsl(var(--status-warning-bg))] text-[hsl(var(--status-warning-text))]'
				};
			case 'unavailable':
				return {
					label: 'Respinsă',
					className:
						'border-[hsl(var(--status-danger-border))] bg-[hsl(var(--status-danger-bg))] text-[hsl(var(--status-danger-text))]'
				};
			default:
				return {
					label: league.source === 'discovered' ? 'Validată' : 'Disponibilă',
					className:
						'border-[hsl(var(--status-success-border))] bg-[hsl(var(--status-success-bg))] text-[hsl(var(--status-success-text))]'
				};
		}
	}

	function stopReasonLabel(value: FootballCatalogDiscoveryValidationResponse['stop_reason']) {
		if (value === 'all_validated') return 'Toate ligile au fost validate';
		if (value === 'no_candidates') return 'Nu au fost găsite candidate';
		return 'S-a atins limita de încercări';
	}
</script>

<svelte:head>
	<title>Listare țări/ligi · Betfront</title>
	<meta
		name="description"
		content="Descoperă și validează ligile OddsPortal pentru mai multe țări dintr-un singur flux controlat."
	/>
</svelte:head>

<div class="mx-auto w-full max-w-[1600px] space-y-5 sm:space-y-6">
	<header class="border border-border bg-card px-4 py-5 shadow-sm sm:px-6 sm:py-6">
		<div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
			<div class="max-w-3xl">
				<p class="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Configurații · Catalog fotbal</p>
				<h1 class="mt-2 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">Listare țări/ligi</h1>
				<p class="mt-2 text-sm leading-6 text-muted-foreground sm:text-base">
					Selectează una sau mai multe țări. Platforma caută ligile în OddsPortal, le verifică pe paginile de rezultate și reia candidatele nevalidate în limita configurată.
				</p>
			</div>
			<div class="grid grid-cols-3 gap-2 sm:min-w-[25rem]">
				<div class="border border-border bg-background p-3">
					<p class="text-xs text-muted-foreground">Țări selectate</p>
					<p class="mt-1 font-mono text-xl font-semibold text-foreground">{selectedCountries.length}</p>
				</div>
				<div class="border border-border bg-background p-3">
					<p class="text-xs text-muted-foreground">Ligi în catalog</p>
					<p class="mt-1 font-mono text-xl font-semibold text-foreground">{catalogRows.length}</p>
				</div>
				<div class="border border-border bg-background p-3">
					<p class="text-xs text-muted-foreground">Validate</p>
					<p class="mt-1 font-mono text-xl font-semibold text-[hsl(var(--status-success-text))]">{availableCount}</p>
				</div>
			</div>
		</div>
	</header>

	<section class="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]" aria-labelledby="workflow-heading">
		<div class="min-w-0 border border-border bg-card p-4 shadow-sm sm:p-5">
			<div class="flex items-start justify-between gap-3">
				<div>
					<p class="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Pasul 1</p>
					<h2 id="workflow-heading" class="mt-1 text-lg font-semibold text-foreground">Alege țările</h2>
				</div>
				<Globe2 class="h-5 w-5 text-primary" aria-hidden="true" />
			</div>

			<div class="mt-4">
				<label for="country-search" class="text-sm font-medium text-foreground">Caută în catalogul de țări</label>
				<div class="relative mt-2">
					<Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
					<Input id="country-search" bind:value={countryQuery} class="pl-9" placeholder="Ex: România, Argentina, Australia" />
				</div>
			</div>

			<div class="mt-3 flex flex-wrap items-center justify-between gap-2">
				<p class="text-xs text-muted-foreground">Multi-select · maxim {maxSelectedCountries} · {filteredCountries.length} țări afișate</p>
				<div class="flex gap-2">
					<Button variant="ghost" size="sm" onclick={selectAllVisible} disabled={filteredCountries.length === 0 || selectedCountries.length >= maxSelectedCountries}>Selectează afișate</Button>
					<Button variant="ghost" size="sm" onclick={() => (selectedCountries = [])} disabled={selectedCountries.length === 0}>Golește</Button>
				</div>
			</div>

			<div class="mt-3 max-h-[22rem] overflow-y-auto border border-border p-2" aria-label="Selectare multiplă țări">
				{#if isLoading}
					<div class="flex min-h-40 items-center justify-center gap-2 text-sm text-muted-foreground">
						<LoaderCircle class="h-4 w-4 animate-spin" aria-hidden="true" /> Se încarcă țările...
					</div>
				{:else}
					<div class="grid gap-2 sm:grid-cols-2">
						{#each filteredCountries as country (country.country)}
							<label class="flex min-h-12 cursor-pointer items-center gap-3 border border-border bg-background px-3 py-2 transition-colors hover:border-primary/50 hover:bg-muted/50">
								<input
									type="checkbox"
									class="h-4 w-4 accent-[hsl(var(--primary))]"
									checked={selectedCountries.includes(country.country)}
									disabled={selectedCountries.length >= maxSelectedCountries && !selectedCountries.includes(country.country)}
									onchange={() => toggleCountry(country.country)}
								/>
								<span class="min-w-0 flex-1">
									<span class="block truncate text-sm font-medium text-foreground">{country.country}</span>
									<span class="block text-xs text-muted-foreground">{country.leagues.length} ligi cunoscute</span>
								</span>
							</label>
						{:else}
							<p class="col-span-full px-3 py-10 text-center text-sm text-muted-foreground">Nicio țară nu corespunde căutării.</p>
						{/each}
					</div>
				{/if}
			</div>
		</div>

		<div class="min-w-0 border border-border bg-card p-4 shadow-sm sm:p-5">
			<div class="flex items-start justify-between gap-3">
				<div>
					<p class="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Pașii 2–3</p>
					<h2 class="mt-1 text-lg font-semibold text-foreground">Descoperire și validare</h2>
				</div>
				<ShieldCheck class="h-5 w-5 text-primary" aria-hidden="true" />
			</div>

			<ol class="mt-4 grid gap-2 sm:grid-cols-3" aria-label="Etapele fluxului">
				<li class="border border-primary/30 bg-primary/5 p-3">
					<p class="text-xs font-semibold text-primary">01 · Selecție</p>
					<p class="mt-1 text-xs text-muted-foreground">{selectedCountries.length} țări pregătite</p>
				</li>
				<li class="border border-border bg-background p-3">
					<p class="text-xs font-semibold text-foreground">02 · Căutare OddsPortal</p>
					<p class="mt-1 text-xs text-muted-foreground">Catalog live, filtrat pe țări</p>
				</li>
				<li class="border border-border bg-background p-3">
					<p class="text-xs font-semibold text-foreground">03 · Validare rezultate</p>
					<p class="mt-1 text-xs text-muted-foreground">Retry controlat pentru candidate</p>
				</li>
			</ol>

			<div class="mt-5 grid gap-4 sm:grid-cols-2">
				<div>
					<label for="attempts" class="text-sm font-medium text-foreground">Număr maxim de încercări</label>
					<Select id="attempts" bind:value={maxAttempts} class="mt-2">
						<option value={1}>1 încercare</option>
						<option value={2}>2 încercări</option>
						<option value={3}>3 încercări</option>
						<option value={4}>4 încercări</option>
						<option value={5}>5 încercări</option>
					</Select>
				</div>
				<div>
					<label for="batch-size" class="text-sm font-medium text-foreground">Ligi verificate per lot</label>
					<Select id="batch-size" bind:value={batchSize} class="mt-2">
						<option value={10}>10 ligi</option>
						<option value={20}>20 ligi</option>
						<option value={25}>25 ligi</option>
					</Select>
				</div>
			</div>

			<div class="mt-5 border border-border bg-muted/30 p-4">
				<div class="flex items-start gap-3">
					<AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--status-warning-text))]" aria-hidden="true" />
					<div class="text-xs leading-5 text-muted-foreground">
						<p class="font-medium text-foreground">Flux live, cu trafic extern controlat</p>
						<p>O ligă este promovată doar dacă pagina sa de rezultate conține meciuri verificabile. Candidatele respinse sunt reluate până la limita aleasă.</p>
					</div>
				</div>
			</div>

			{#if !isAdmin}
				<div class="mt-4 border border-[hsl(var(--status-warning-border))] bg-[hsl(var(--status-warning-bg))] p-3 text-sm text-[hsl(var(--status-warning-text))]" role="note">
					Doar un administrator poate porni descoperirea live. Catalogul și stările ligilor rămân vizibile pentru verificare.
				</div>
			{/if}

			<Button
				class="mt-5 w-full sm:w-auto"
				size="lg"
				onclick={runDiscoveryAndValidation}
				disabled={!isAdmin || selectedCountries.length === 0 || isRunning}
			>
				{#if isRunning}
					<LoaderCircle class="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> Caută și validează...
				{:else}
					<RefreshCw class="mr-2 h-4 w-4" aria-hidden="true" /> Caută și validează ligile
				{/if}
			</Button>
			<p class="mt-2 text-xs text-muted-foreground" aria-live="polite">
				{#if selectedCountries.length === 0}
					Selectează cel puțin o țară pentru a activa fluxul.
				{:else}
					Vor fi procesate: {selectedCountries.join(', ')}.
				{/if}
			</p>
		</div>
	</section>

	{#if errorMessage}
		<div class="flex items-start gap-3 border border-[hsl(var(--status-danger-border))] bg-[hsl(var(--status-danger-bg))] p-4 text-sm text-[hsl(var(--status-danger-text))]" role="alert">
			<XCircle class="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
			<div><p class="font-semibold">Fluxul a întâmpinat o problemă</p><p class="mt-1">{errorMessage}</p></div>
		</div>
	{/if}

	{#if result}
		<section class="border border-border bg-card p-4 shadow-sm sm:p-5" aria-labelledby="run-result-heading">
			<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
				<div>
					<p class="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Ultima execuție</p>
					<h2 id="run-result-heading" class="mt-1 text-lg font-semibold text-foreground">{stopReasonLabel(result.stop_reason)}</h2>
				</div>
				<span class="inline-flex w-fit items-center gap-2 border border-border bg-background px-3 py-2 text-xs text-muted-foreground">
					{#if result.stop_reason === 'all_validated'}<CheckCircle2 class="h-4 w-4 text-[hsl(var(--status-success-text))]" />{:else}<CircleDashed class="h-4 w-4 text-[hsl(var(--status-warning-text))]" />{/if}
					{result.attempts_used} / {maxAttempts} încercări
				</span>
			</div>

			<div class="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
				<div class="border border-border bg-background p-3"><p class="text-xs text-muted-foreground">Descoperite</p><p class="mt-1 font-mono text-xl font-semibold">{result.discovered}</p></div>
				<div class="border border-border bg-background p-3"><p class="text-xs text-muted-foreground">Validate</p><p class="mt-1 font-mono text-xl font-semibold text-[hsl(var(--status-success-text))]">{result.available}</p></div>
				<div class="border border-border bg-background p-3"><p class="text-xs text-muted-foreground">Respinse</p><p class="mt-1 font-mono text-xl font-semibold text-[hsl(var(--status-danger-text))]">{result.unavailable}</p></div>
				<div class="border border-border bg-background p-3"><p class="text-xs text-muted-foreground">În așteptare</p><p class="mt-1 font-mono text-xl font-semibold text-[hsl(var(--status-warning-text))]">{result.pending}</p></div>
			</div>

			<div class="mt-4 overflow-x-auto">
				<table class="w-full min-w-[44rem] border-collapse text-left text-sm">
					<thead><tr class="border-b border-border text-xs uppercase tracking-[0.08em] text-muted-foreground"><th class="px-3 py-3">Încercare</th><th class="px-3 py-3">Descoperite</th><th class="px-3 py-3">Verificate</th><th class="px-3 py-3">Validate</th><th class="px-3 py-3">Respinse</th><th class="px-3 py-3">În așteptare</th></tr></thead>
					<tbody>
						{#each result.attempts as attempt (attempt.attempt)}
							<tr class="border-b border-border/70 last:border-0"><td class="px-3 py-3 font-mono font-semibold">#{attempt.attempt}</td><td class="px-3 py-3">{attempt.discovered}</td><td class="px-3 py-3">{attempt.checked}</td><td class="px-3 py-3 text-[hsl(var(--status-success-text))]">{attempt.available}</td><td class="px-3 py-3 text-[hsl(var(--status-danger-text))]">{attempt.unavailable}</td><td class="px-3 py-3 text-[hsl(var(--status-warning-text))]">{attempt.pending}</td></tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{/if}

	<section class="min-w-0 border border-border bg-card shadow-sm" aria-labelledby="catalog-heading">
		<div class="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-end sm:justify-between sm:p-5">
			<div>
				<p class="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Catalog curent</p>
				<h2 id="catalog-heading" class="mt-1 text-lg font-semibold text-foreground">Starea ligilor</h2>
				<p class="mt-1 text-xs text-muted-foreground">{selectedCountries.length > 0 ? 'Filtrat după țările selectate.' : 'Sunt afișate toate țările disponibile.'}</p>
			</div>
			<div class="flex flex-wrap gap-2 text-xs">
				<span class="border border-[hsl(var(--status-success-border))] bg-[hsl(var(--status-success-bg))] px-2.5 py-1 text-[hsl(var(--status-success-text))]">{availableCount} disponibile</span>
				<span class="border border-[hsl(var(--status-warning-border))] bg-[hsl(var(--status-warning-bg))] px-2.5 py-1 text-[hsl(var(--status-warning-text))]">{pendingCount} în verificare</span>
				<span class="border border-[hsl(var(--status-danger-border))] bg-[hsl(var(--status-danger-bg))] px-2.5 py-1 text-[hsl(var(--status-danger-text))]">{unavailableCount} respinse</span>
			</div>
		</div>

		{#if isLoading}
			<div class="flex min-h-48 items-center justify-center gap-2 text-sm text-muted-foreground"><LoaderCircle class="h-4 w-4 animate-spin" /> Se încarcă ligile...</div>
		{:else if catalogRows.length === 0}
			<div class="p-10 text-center text-sm text-muted-foreground">Nu există ligi pentru selecția curentă.</div>
		{:else}
			<div class="hidden overflow-x-auto md:block">
				<table class="w-full min-w-[54rem] border-collapse text-left text-sm">
					<thead><tr class="border-b border-border bg-muted/30 text-xs uppercase tracking-[0.08em] text-muted-foreground"><th class="px-4 py-3">Țară</th><th class="px-4 py-3">Ligă</th><th class="px-4 py-3">Sursă</th><th class="px-4 py-3">Stare</th><th class="px-4 py-3">Capabilitate</th></tr></thead>
					<tbody>
						{#each catalogRows as row (`${row.country}-${row.league.id}`)}
							{@const meta = statusMeta(row.league)}
							<tr class="border-b border-border/70 last:border-0 hover:bg-muted/20">
								<td class="px-4 py-3 font-medium text-foreground">{row.country}</td>
								<td class="px-4 py-3"><p class="font-medium text-foreground">{row.league.name}</p><p class="mt-0.5 font-mono text-xs text-muted-foreground">{row.league.scrape_slug ?? row.league.id}</p></td>
								<td class="px-4 py-3 text-muted-foreground">{row.league.source === 'discovered' ? 'OddsPortal live' : 'Catalog intern'}</td>
								<td class="px-4 py-3"><span class={`inline-flex border px-2.5 py-1 text-xs font-medium ${meta.className}`}>{meta.label}</span></td>
								<td class="px-4 py-3 text-muted-foreground">{row.league.scrape_capability === 'upcoming' ? 'Meciuri viitoare' : 'Istoric + viitoare'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			<div class="grid gap-3 p-3 md:hidden">
				{#each catalogRows as row (`mobile-${row.country}-${row.league.id}`)}
					{@const meta = statusMeta(row.league)}
					<article class="min-w-0 border border-border bg-background p-3">
						<div class="flex items-start justify-between gap-3">
							<div class="min-w-0"><p class="text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">{row.country}</p><h3 class="mt-1 break-words text-sm font-semibold text-foreground">{row.league.name}</h3></div>
							<span class={`shrink-0 border px-2 py-1 text-[0.7rem] font-medium ${meta.className}`}>{meta.label}</span>
						</div>
						<dl class="mt-3 grid grid-cols-2 gap-2 text-xs">
							<div><dt class="text-muted-foreground">Sursă</dt><dd class="mt-0.5 text-foreground">{row.league.source === 'discovered' ? 'OddsPortal live' : 'Catalog intern'}</dd></div>
							<div><dt class="text-muted-foreground">Acoperire</dt><dd class="mt-0.5 text-foreground">{row.league.scrape_capability === 'upcoming' ? 'Viitoare' : 'Istoric + viitoare'}</dd></div>
						</dl>
						<p class="mt-3 break-all border-t border-border pt-2 font-mono text-[0.68rem] text-muted-foreground">{row.league.scrape_slug ?? row.league.id}</p>
					</article>
				{/each}
			</div>
		{/if}
	</section>
</div>
