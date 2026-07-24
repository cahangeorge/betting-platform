<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import Button from '$lib/components/ui/Button.svelte';

	const status = $derived(page.status);
	const message = $derived(
		status === 404
			? 'Pagina solicitată nu există sau nu mai este disponibilă.'
			: 'Spațiul de lucru nu a putut afișa această pagină. Datele deja salvate nu au fost modificate.'
	);

	function recover() {
		void goto('/', { replaceState: true, invalidateAll: true });
	}
</script>

<svelte:head><title>Recuperare aplicație | Bet</title></svelte:head>

<main class="mx-auto flex min-h-screen max-w-2xl items-center p-6">
	<section class="w-full border border-border bg-card p-6 sm:p-8" aria-labelledby="error-title">
		<p class="text-xs font-semibold uppercase tracking-[0.16em] text-football-gold">Recuperare aplicație · {status}</p>
		<h1 id="error-title" class="mt-2 text-2xl font-semibold text-foreground">Nu am putut deschide această etapă</h1>
		<p class="mt-3 text-sm leading-6 text-muted-foreground">{message}</p>
		<div class="mt-6 flex flex-wrap gap-3">
			<Button onclick={recover}>Revino la spațiul de lucru</Button>
			<Button variant="secondary" onclick={() => history.back()}>Înapoi</Button>
		</div>
	</section>
</main>
