<script lang="ts">
	import { AlertTriangle } from 'lucide-svelte';
	import PublicFooter from '$lib/components/PublicFooter.svelte';
</script>

<article class="mx-auto max-w-4xl space-y-8 pb-4 pt-6 sm:pt-10">
	<header class="border-b border-border pb-8">
		<p class="text-xs font-semibold uppercase tracking-[0.2em] text-football-green">Document informativ</p>
		<h1 class="mt-3 font-sport text-3xl font-extrabold text-foreground sm:text-4xl">Notă de confidențialitate</h1>
		<p class="mt-4 max-w-3xl text-base leading-7 text-muted-foreground">
			Această pagină descrie categoriile de date observabile în produs. Detaliile juridice și operaționale trebuie confirmate înainte de lansare.
		</p>
	</header>

	<section class="border border-[hsl(var(--status-warning-border))] bg-[hsl(var(--status-warning-bg))] p-5" aria-labelledby="privacy-review-heading">
		<div class="flex items-start gap-3">
			<AlertTriangle class="mt-0.5 size-5 shrink-0 text-[hsl(var(--status-warning-text))]" aria-hidden="true" />
			<div>
				<h2 id="privacy-review-heading" class="font-semibold text-foreground">Necesită completare și revizuire juridică</h2>
				<p class="mt-2 text-sm leading-6 text-muted-foreground">
					Identitatea operatorului, contactul pentru confidențialitate, temeiurile, retenția, destinatarii și drepturile aplicabile nu sunt încă validate.
				</p>
			</div>
		</div>
	</section>

	<section class="space-y-5 text-sm leading-6 text-muted-foreground">
		<div>
			<h2 class="font-sport text-xl font-bold text-foreground">Date de cont</h2>
			<p class="mt-2">La creare sunt folosite numele, adresa de email și parola. Parola nu trebuie afișată sau returnată în interfață.</p>
		</div>
		<div>
			<h2 class="font-sport text-xl font-bold text-foreground">Date de utilizare</h2>
			<p class="mt-2">Platforma poate asocia utilizatorului seturi de date, rulări de analiză, selecții, bankrolluri, bilete, programări și stări operaționale necesare fluxului solicitat.</p>
		</div>
		<div>
			<h2 class="font-sport text-xl font-bold text-foreground">Autentificare și funcționare</h2>
			<p class="mt-2">Sunt folosite cookie-uri strict necesare pentru sesiunea autentificată. Această implementare nu introduce prin această pagină instrumente noi de publicitate sau analytics.</p>
		</div>
		<div>
			<h2 class="font-sport text-xl font-bold text-foreground">Controlul utilizatorului</h2>
			<p class="mt-2">Înainte de producție trebuie definite canale verificabile pentru acces, corectare, ștergere și celelalte drepturi aplicabile, împreună cu termenele de răspuns.</p>
		</div>
	</section>
</article>

<PublicFooter />
