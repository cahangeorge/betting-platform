<script lang="ts">
	import { ArrowLeft, Ban, CirclePause, PiggyBank, ShieldCheck } from 'lucide-svelte';
	import PublicFooter from '$lib/components/PublicFooter.svelte';

	const principles = [
		{
			icon: PiggyBank,
			title: 'Stabilește bugetul înainte',
			text: 'Folosește numai o sumă pe care îți permiți să o pierzi și nu o amesteca cu banii pentru cheltuieli esențiale.'
		},
		{
			icon: Ban,
			title: 'Nu urmări pierderile',
			text: 'Nu crește miza pentru a recupera rapid o pierdere și nu interpreta o probabilitate drept o certitudine.'
		},
		{
			icon: CirclePause,
			title: 'Folosește pauze și limite',
			text: 'Stabilește limite de timp și bani. Oprește-te dacă activitatea produce stres, presiune sau afectează alte responsabilități.'
		}
	];
</script>

<article class="mx-auto max-w-4xl space-y-10 pb-12 pt-6 sm:pt-10">
	<header class="border-b border-border pb-8">
		<a class="inline-flex min-h-11 items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground" href="/about">
			<ArrowLeft class="size-4" aria-hidden="true" /> Despre platformă
		</a>
		<div class="mt-5 flex items-center gap-3">
			<ShieldCheck class="size-7 text-football-green" aria-hidden="true" />
			<p class="text-xs font-semibold uppercase tracking-[0.2em] text-football-green">Utilizare responsabilă</p>
		</div>
		<h1 class="mt-3 font-sport text-3xl font-extrabold text-foreground sm:text-4xl">Analiza nu elimină riscul</h1>
		<p class="mt-4 max-w-3xl text-base leading-7 text-muted-foreground">
			Betfront este un instrument de analiză și organizare. Nu garantează câștiguri și nu trebuie folosit ca motiv pentru depășirea limitelor personale.
		</p>
	</header>

	<section class="grid gap-4 md:grid-cols-3" aria-label="Principii de utilizare responsabilă">
		{#each principles as principle (principle.title)}
			<section class="border border-border bg-card p-5">
				<principle.icon class="size-5 text-football-green" aria-hidden="true" />
				<h2 class="mt-4 font-semibold text-foreground">{principle.title}</h2>
				<p class="mt-2 text-sm leading-6 text-muted-foreground">{principle.text}</p>
			</section>
		{/each}
	</section>

	<section class="border border-border bg-muted/30 p-5 sm:p-6" aria-labelledby="pause-heading">
		<h2 id="pause-heading" class="font-sport text-xl font-bold text-foreground">Când este timpul pentru o pauză</h2>
		<p class="mt-3 text-sm leading-6 text-muted-foreground">
			Dacă pierzi controlul asupra timpului sau banilor, oprește activitatea, folosește instrumentele de autoexcludere oferite de operatorul relevant și discută cu o persoană de încredere sau cu un serviciu specializat disponibil în jurisdicția ta.
		</p>
		<p class="mt-4 text-sm font-medium text-foreground">
			Accesul și participarea sunt destinate exclusiv adulților care îndeplinesc vârsta legală aplicabilă.
		</p>
	</section>
</article>

<PublicFooter />
