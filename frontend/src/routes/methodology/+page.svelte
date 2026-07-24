<script lang="ts">
	import { AlertTriangle, ArrowLeft, Database, GitBranch, Scale, Sigma } from 'lucide-svelte';
	import PublicFooter from '$lib/components/PublicFooter.svelte';

	const steps = [
		{
			icon: Database,
			title: '1. Pregătirea datelor',
			text: 'Utilizatorul alege competițiile, intervalul și acoperirea. Joburile și sursele rămân inspectabile, iar datele lipsă sau parțiale sunt semnalate.'
		},
		{
			icon: Sigma,
			title: '2. Analiza statistică',
			text: 'Strategiile compatibile procesează datasetul pregătit. Platforma afișează probabilități și rezultate per strategie, fără a transforma estimările în certitudini.'
		},
		{
			icon: GitBranch,
			title: '3. Trasabilitatea rezultatului',
			text: 'Candidații păstrează legătura cu datasetul și rularea de predicție. Rezultatele reutilizate, parțiale sau eșuate sunt etichetate explicit.'
		},
		{
			icon: Scale,
			title: '4. Revizuirea deciziei',
			text: 'Selecțiile pot fi comparate și revizuite înainte de generarea, activarea sau înregistrarea unui bilet. Orice acțiune externă rămâne separată, iar automatizarea nu înlocuiește confirmarea utilizatorului.'
		}
	];
</script>

<article class="mx-auto max-w-4xl space-y-10 pb-12 pt-6 sm:pt-10">
	<header class="border-b border-border pb-8">
		<a class="inline-flex min-h-11 items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground" href="/about">
			<ArrowLeft class="size-4" aria-hidden="true" /> Despre platformă
		</a>
		<p class="mt-5 text-xs font-semibold uppercase tracking-[0.2em] text-football-green">Metodologie</p>
		<h1 class="mt-3 font-sport text-3xl font-extrabold text-foreground sm:text-4xl">De la date la o decizie revizuibilă</h1>
		<p class="mt-4 max-w-3xl text-base leading-7 text-muted-foreground">
			Betfront structurează procesul de analiză astfel încât sursa, starea și limitele fiecărui rezultat să poată fi verificate înainte de utilizare.
		</p>
	</header>

	<section class="space-y-4" aria-label="Etapele metodologiei">
		{#each steps as step (step.title)}
			<section class="grid gap-4 border border-border bg-card p-5 sm:grid-cols-[auto_1fr] sm:p-6">
				<step.icon class="size-6 text-football-green" aria-hidden="true" />
				<div>
					<h2 class="font-semibold text-foreground">{step.title}</h2>
					<p class="mt-2 text-sm leading-6 text-muted-foreground">{step.text}</p>
				</div>
			</section>
		{/each}
	</section>

	<section
		class="border border-[hsl(var(--status-warning-border))] bg-[hsl(var(--status-warning-bg))] p-5 sm:p-6"
		aria-labelledby="limits-heading"
	>
		<div class="flex items-start gap-3">
			<AlertTriangle class="mt-0.5 size-5 shrink-0 text-[hsl(var(--status-warning-text))]" aria-hidden="true" />
			<div>
				<h2 id="limits-heading" class="font-semibold text-foreground">Limite de interpretare</h2>
				<ul class="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-muted-foreground">
					<li>Datele pot fi incomplete, întârziate sau afectate de schimbări ale surselor externe.</li>
					<li>Performanța istorică a unui model nu garantează rezultate viitoare.</li>
					<li>Cotele se pot modifica după momentul colectării sau generării unei selecții.</li>
					<li>Rezultatele trebuie interpretate împreună cu bugetul și limitele personale.</li>
				</ul>
			</div>
		</div>
	</section>
</article>

<PublicFooter />
