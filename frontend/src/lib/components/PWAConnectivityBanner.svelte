<script lang="ts">
	import { onMount } from 'svelte';

	let isOnline = $state(true);
	let showRecoveryNotice = $state(false);
	let hideRecoveryTimer: ReturnType<typeof setTimeout> | undefined;

	onMount(() => {
		isOnline = navigator.onLine;

		const handleOnline = () => {
			isOnline = true;
			showRecoveryNotice = true;
			if (hideRecoveryTimer) {
				clearTimeout(hideRecoveryTimer);
			}
			hideRecoveryTimer = setTimeout(() => {
				showRecoveryNotice = false;
			}, 3500);
		};

		const handleOffline = () => {
			isOnline = false;
			showRecoveryNotice = false;
			if (hideRecoveryTimer) {
				clearTimeout(hideRecoveryTimer);
			}
		};

		window.addEventListener('online', handleOnline);
		window.addEventListener('offline', handleOffline);

		return () => {
			window.removeEventListener('online', handleOnline);
			window.removeEventListener('offline', handleOffline);
			if (hideRecoveryTimer) {
				clearTimeout(hideRecoveryTimer);
			}
		};
	});
</script>

{#if !isOnline}
	<div class="border border-amber-500/30 bg-amber-500/12 px-4 py-3 text-sm text-amber-100 shadow-lg backdrop-blur-md" role="status">
		<span class="font-semibold">Mod offline.</span>
		Este disponibilă doar pagina de reconectare. Datele live, colectarea, predicțiile și acțiunile nefinalizate nu sunt salvate sau trimise până revine conexiunea.
	</div>
{:else if showRecoveryNotice}
	<div class="border border-emerald-500/30 bg-emerald-500/12 px-4 py-3 text-sm text-emerald-100 shadow-lg backdrop-blur-md" role="status">
		<span class="font-semibold">Conexiune restabilită.</span>
		Reîncarcă pagina pentru a relua fluxurile live. Bet nu retrimite automat acțiunile nefinalizate.
	</div>
{/if}
