	<script lang="ts">
	import { enhance } from '$app/forms';
	import PublicFooter from '$lib/components/PublicFooter.svelte';

	let { form }: import('./$types').PageProps = $props();
</script>

<div class="flex min-h-[calc(100vh-4rem)] items-center justify-center py-6">
	<div class="w-full max-w-md">
		<div class="mb-8 text-center">
			<div
				class="mx-auto mb-4 flex h-16 w-16 items-center justify-center border border-football-green bg-muted"
			>
				<span class="font-sport text-2xl font-extrabold text-football-green">BF</span>
			</div>
			<h1 class="font-sport text-2xl font-extrabold text-foreground">Bine ai revenit</h1>
			<p class="mt-2 text-muted-foreground">Autentifică-te pentru a continua analiza.</p>
		</div>

		<div class="border border-border border-t-2 border-t-football-green bg-card p-5">
			<form method="POST" action="?/login" use:enhance class="space-y-5">
				{#if form?.error}
					<div class="border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
						{form.error}
					</div>
				{/if}

				<label class="text-sm font-medium leading-none" for="email">Email</label>
				<input
					id="email"
					class="flex min-h-11 w-full border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
					type="email" name="email" placeholder="nume@exemplu.ro"
					value={form?.email ?? ''} required
				/>

				<label class="text-sm font-medium leading-none" for="password">Parolă</label>
				<input
					id="password"
					class="flex min-h-11 w-full border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
					type="password" name="password" placeholder="Introdu parola" required
				/>

				<div class="flex items-center justify-between pt-2">
					<a href="/signup" class="text-sm text-football-green hover:text-football-green/80 transition-colors">
						Nu ai cont? Creează unul
					</a>
				</div>

				<button
					type="submit"
					class="inline-flex min-h-11 w-full items-center justify-center whitespace-nowrap bg-primary px-4 py-2 text-sm font-medium text-primary-foreground ring-offset-background transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
				>
					Autentificare
				</button>
			</form>
		</div>
	</div>
</div>

<PublicFooter />
