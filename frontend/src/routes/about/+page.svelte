<script lang="ts">
	import {
		ArrowRight,
		ChartNoAxesCombined,
		Database,
		ListChecks,
		ShieldCheck
	} from 'lucide-svelte';
	import PublicFooter from '$lib/components/PublicFooter.svelte';

	const capabilities = [
		{
			icon: Database,
			title: 'Date pregătite cu context',
			description:
				'Competițiile, intervalele și sursele selectate rămân vizibile de la colectare până la analiză.'
		},
		{
			icon: ChartNoAxesCombined,
			title: 'Analiză comparabilă',
			description:
				'Rezultatele modelelor sunt prezentate cu probabilități, cote disponibile și semnale de fiabilitate.'
		},
		{
			icon: ListChecks,
			title: 'Revizuire înainte de acțiune',
			description:
				'Candidații și biletele sunt inspectați înainte de activare sau de orice acțiune externă; platforma nu ascunde pașii intermediari.'
		}
	];
</script>

<article class="mx-auto max-w-5xl space-y-12 pb-12 pt-6 sm:pt-10">
	<header class="border-b border-border pb-10">
		<p class="text-xs font-semibold uppercase tracking-[0.2em] text-football-green">Despre Betfront</p>
		<h1 class="mt-4 max-w-3xl font-sport text-3xl font-extrabold leading-tight text-foreground sm:text-5xl">
			Un flux mai clar pentru analiza pariurilor sportive
		</h1>
		<p class="mt-5 max-w-3xl text-base leading-7 text-muted-foreground sm:text-lg">
			Betfront reunește pregătirea datelor, modelele statistice, evaluarea oportunităților și
			revizuirea biletelor într-un spațiu de lucru trasabil. Scopul este să susțină o decizie
			informată, nu să promită un rezultat.
		</p>
		<div class="mt-7 flex flex-col gap-3 sm:flex-row">
			<a
				href="/signup"
				class="inline-flex min-h-11 items-center justify-center gap-2 bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
			>
				Creează un cont <ArrowRight class="size-4" aria-hidden="true" />
			</a>
			<a
				href="/methodology"
				class="inline-flex min-h-11 items-center justify-center border border-border px-5 py-3 text-sm font-semibold text-foreground transition-colors hover:bg-muted"
			>
				Vezi metodologia
			</a>
		</div>
	</header>

	<section aria-labelledby="capabilities-heading">
		<div class="max-w-2xl">
			<p class="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Cum ajută</p>
			<h2 id="capabilities-heading" class="mt-2 font-sport text-2xl font-bold text-foreground sm:text-3xl">
				Contextul rămâne vizibil de la date la bilet
			</h2>
		</div>
		<div class="mt-6 grid gap-4 md:grid-cols-3">
			{#each capabilities as capability (capability.title)}
				<section class="border border-border bg-card p-5">
					<capability.icon class="size-5 text-football-green" aria-hidden="true" />
					<h3 class="mt-4 font-semibold text-foreground">{capability.title}</h3>
					<p class="mt-2 text-sm leading-6 text-muted-foreground">{capability.description}</p>
				</section>
			{/each}
		</div>
	</section>

	<section class="grid gap-5 border border-border bg-card p-5 sm:p-7 lg:grid-cols-[1fr_1.4fr]" aria-labelledby="trust-heading">
		<div>
			<ShieldCheck class="size-7 text-football-green" aria-hidden="true" />
			<h2 id="trust-heading" class="mt-4 font-sport text-2xl font-bold text-foreground">
				Încredere prin transparență
			</h2>
		</div>
		<ul class="space-y-3 text-sm leading-6 text-muted-foreground">
			<li>Rulările păstrează datasetul sursă, momentul creării și starea persistată.</li>
			<li>Rezultatele parțiale, eșecurile și strategiile indisponibile sunt semnalate explicit.</li>
			<li>Execuția paper este diferențiată vizibil de orice plasare externă.</li>
			<li>Nicio probabilitate sau cotă nu reprezintă o garanție de câștig.</li>
		</ul>
	</section>

	<nav class="grid gap-3 border-t border-border pt-7 sm:grid-cols-2" aria-label="Informații publice Betfront">
		<a class="border border-border p-4 transition-colors hover:bg-muted" href="/methodology">
			<span class="font-semibold text-foreground">Metodologie și limite</span>
			<span class="mt-1 block text-sm text-muted-foreground">Cum sunt pregătite și interpretate datele.</span>
		</a>
		<a class="border border-border p-4 transition-colors hover:bg-muted" href="/responsible-gambling">
			<span class="font-semibold text-foreground">Utilizare responsabilă</span>
			<span class="mt-1 block text-sm text-muted-foreground">Principii pentru control, limite și pauze.</span>
		</a>
	</nav>
</article>

<PublicFooter />
