<script lang="ts">
	import { goto } from '$app/navigation';
	import AuthForm from '$lib/components/AuthForm.svelte';
	import Card from '$lib/components/ui/Card.svelte';

	function onSignupSuccess() {
		goto('/')
	}
</script>

<div class="min-h-[calc(100vh-4rem)] flex items-center justify-center">
	<div class="w-full max-w-md">
		<div class="text-center mb-8">
			<div
				class="w-16 h-16 flex items-center justify-center mx-auto mb-4 bg-muted border border-football-green "
			>
				<span class="font-extrabold text-2xl text-football-green font-sport">SI</span>
			</div>
			<h1 class="text-2xl font-extrabold font-sport text-foreground">Create account</h1>
			<p class="mt-2 text-muted-foreground">Start your sports intelligence journey</p>
		</div>

		<div class="bg-card  border border-border p-5 border-t-2 border-t-football-green">
			<AuthForm mode="signup" onSuccess={onSignupSuccess} />
		</div>
	</div>
</div>
