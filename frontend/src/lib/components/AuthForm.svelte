<script lang="ts">
	import { enhance } from '$app/forms';
	import Button from '$lib/components/ui/Button.svelte';
	import Input from '$lib/components/ui/Input.svelte';

	type SignupForm = {
		error?: string;
		errors?: Partial<
			Record<'name' | 'email' | 'password' | 'confirmPassword' | 'legalAccepted', string>
		>;
		values?: { name?: string; email?: string; legalAccepted?: boolean };
	};

	let {
		mode = 'signup',
		form = null
	}: {
		mode?: 'login' | 'signup';
		form?: SignupForm | null;
	} = $props();

	let loading = $state(false);
</script>

<form
	method="POST"
	use:enhance={() => {
		loading = true;
		return async ({ update }) => {
			await update({ reset: false });
			loading = false;
		};
	}}
	class="space-y-5"
>
	{#if form?.error}
		<div class="border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">
			{form.error}
		</div>
	{/if}

	{#if mode === 'signup'}
		<Input
			label="Nume"
			name="name"
			placeholder="Numele complet"
			value={form?.values?.name ?? ''}
			error={form?.errors?.name}
			disabled={loading}
			required
			autocomplete="name"
		/>
	{/if}

	<Input
		label="Email"
		name="email"
		type="email"
		placeholder="nume@exemplu.ro"
		value={form?.values?.email ?? ''}
		error={form?.errors?.email}
		disabled={loading}
		required
		autocomplete="email"
	/>

	<Input
		label="Parolă"
		name="password"
		type="password"
		placeholder="Introdu parola"
		value=""
		error={form?.errors?.password}
		disabled={loading}
		required
		minlength={8}
		autocomplete={mode === 'signup' ? 'new-password' : 'current-password'}
	/>

	{#if mode === 'signup'}
		<Input
			label="Confirmă parola"
			name="confirmPassword"
			type="password"
			placeholder="Repetă parola"
			value=""
			error={form?.errors?.confirmPassword}
			disabled={loading}
			required
			minlength={8}
			autocomplete="new-password"
		/>

		<div class="space-y-2">
			<label class="flex min-h-11 items-start gap-3 text-sm leading-6 text-foreground">
				<input
					type="checkbox"
					name="legalAccepted"
					value="accepted"
					checked={form?.values?.legalAccepted ?? false}
					required
					class="mt-1 size-5 shrink-0 accent-football-green"
					aria-invalid={form?.errors?.legalAccepted ? 'true' : undefined}
					aria-describedby={form?.errors?.legalAccepted ? 'legal-acceptance-error' : undefined}
				/>
				<span>
					Confirm că am vârsta legală aplicabilă în jurisdicția mea și accept
					<a class="font-medium text-football-green underline underline-offset-2" href="/terms">termenii informativi</a>
					și
					<a class="font-medium text-football-green underline underline-offset-2" href="/privacy">nota de confidențialitate</a>.
				</span>
			</label>
			{#if form?.errors?.legalAccepted}
				<p id="legal-acceptance-error" class="text-sm font-medium text-[hsl(var(--status-danger-text))]">
					{form.errors.legalAccepted}
				</p>
			{/if}
		</div>
	{/if}

	<div class="flex items-center justify-between pt-2">
		{#if mode === 'login'}
			<a href="/signup" class="text-sm text-football-green transition-colors hover:text-football-green/80">
				Nu ai cont? Creează unul
			</a>
		{:else}
			<a href="/login" class="text-sm text-football-green transition-colors hover:text-football-green/80">
				Ai deja cont? Autentifică-te
			</a>
		{/if}
	</div>

	<Button type="submit" fullWidth disabled={loading}>
		{#if loading}
			<div class="mr-2 h-4 w-4 animate-spin border-2 border-primary-foreground border-t-transparent" aria-hidden="true"></div>
		{/if}
		{loading ? 'Se procesează...' : mode === 'login' ? 'Autentificare' : 'Creează contul'}
	</Button>
</form>
