<script lang="ts">
	import { AlertTriangle } from 'lucide-svelte';
	import PublicFooter from '$lib/components/PublicFooter.svelte';
</script>

<article class="mx-auto max-w-4xl space-y-8 pb-4 pt-6 sm:pt-10">
	<header class="border-b border-border pb-8">
		<p class="text-xs font-semibold uppercase tracking-[0.2em] text-football-green">Document informativ</p>
		<h1 class="mt-3 font-sport text-3xl font-extrabold text-foreground sm:text-4xl">Termeni de utilizare</h1>
		<p class="mt-4 max-w-3xl text-base leading-7 text-muted-foreground">
			Această versiune descrie limitele funcționale ale platformei și trebuie revizuită juridic înaintea unei lansări publice.
		</p>
	</header>

	<section class="border border-[hsl(var(--status-warning-border))] bg-[hsl(var(--status-warning-bg))] p-5" aria-labelledby="legal-review-heading">
		<div class="flex items-start gap-3">
			<AlertTriangle class="mt-0.5 size-5 shrink-0 text-[hsl(var(--status-warning-text))]" aria-hidden="true" />
			<div>
				<h2 id="legal-review-heading" class="font-semibold text-foreground">Necesită revizuire juridică</h2>
				<p class="mt-2 text-sm leading-6 text-muted-foreground">
					Operatorul legal, jurisdicția, datele de contact și versiunea contractuală trebuie confirmate înainte de producție.
				</p>
			</div>
		</div>
	</section>

	<section class="space-y-5 text-sm leading-6 text-muted-foreground">
		<div>
			<h2 class="font-sport text-xl font-bold text-foreground">Rolul platformei</h2>
			<p class="mt-2">Betfront organizează date, estimări statistice și bilete pentru analiză și revizuire. Nu oferă garanții de rezultat și nu transformă probabilitățile în certitudini.</p>
		</div>
		<div>
			<h2 class="font-sport text-xl font-bold text-foreground">Eligibilitate și responsabilitate</h2>
			<p class="mt-2">Poți crea un cont numai dacă îndeplinești vârsta legală și regulile aplicabile în jurisdicția ta. Ești responsabil pentru buget, limite personale, protejarea contului și orice acțiune realizată în afara platformei.</p>
		</div>
		<div>
			<h2 class="font-sport text-xl font-bold text-foreground">Date și surse externe</h2>
			<p class="mt-2">Datele și cotele pot fi incomplete, întârziate sau modificate de furnizori. Verifică sursa, momentul și starea afișată înainte de a folosi un rezultat.</p>
		</div>
		<div>
			<h2 class="font-sport text-xl font-bold text-foreground">Paper și acțiuni externe</h2>
			<p class="mt-2">Înregistrarea paper este o simulare. Platforma trebuie să diferențieze această simulare de orice acțiune efectuată la un operator extern.</p>
		</div>
	</section>
</article>

<PublicFooter />
