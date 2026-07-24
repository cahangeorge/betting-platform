<script lang="ts">
	import AuthForm from '$lib/components/AuthForm.svelte';
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
			<h1 class="font-sport text-2xl font-extrabold text-foreground">Creează un cont</h1>
			<p class="mt-2 text-muted-foreground">Păstrează datele, analizele și biletele în același flux trasabil.</p>
		</div>

		<div class="border border-border border-t-2 border-t-football-green bg-card p-5">
			<AuthForm mode="signup" {form} />
		</div>
	</div>
</div>

<PublicFooter />
