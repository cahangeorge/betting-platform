<script lang="ts">
	import { enhance } from '$app/forms';
	import Card from '$lib/components/ui/Card.svelte';

	let { form, data }: import('./$types').PageProps = $props();
</script>

<div class="min-h-[calc(100vh-4rem)] flex items-center justify-center">
	<div class="w-full max-w-md">
		<div class="text-center mb-8">
			<div
				class="w-16 h-16 flex items-center justify-center mx-auto mb-4 bg-muted border border-football-green "
			>
				<span class="font-extrabold text-2xl text-football-green font-sport">SI</span>
			</div>
			<h1 class="text-2xl font-extrabold font-sport text-foreground">Welcome back</h1>
			<p class="mt-2 text-muted-foreground">Sign in to your account</p>
		</div>

		<div class="bg-card  border border-border p-5 border-t-2 border-t-football-green">
			<form method="POST" action="?/login" use:enhance class="space-y-5">
				{#if form?.error}
					<div class="p-3 text-sm bg-destructive/10 border border-destructive/30 text-destructive">
						{form.error}
					</div>
				{/if}

				<label class="text-sm font-medium leading-none" for="email">Email</label>
				<input
					class="flex h-10 w-full border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
					type="email" name="email" placeholder="you@example.com"
					value={form?.email ?? ''} required
				/>

				<label class="text-sm font-medium leading-none" for="password">Password</label>
				<input
					class="flex h-10 w-full border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
					type="password" name="password" placeholder="Enter your password" required
				/>

				<div class="flex items-center justify-between pt-2">
					<a href="/signup" class="text-sm text-football-green hover:text-football-green/80 transition-colors">
						No account yet? Sign up
					</a>
				</div>

				<button
					type="submit"
					class="inline-flex items-center justify-center whitespace-nowrap text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2 w-full"
				>
					Sign In
				</button>
			</form>
		</div>
	</div>
</div>