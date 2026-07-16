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
		Paginile din cache rămân disponibile, dar datele live, colectarea și predicțiile pot eșua până revine conexiunea.
	</div>
{:else if showRecoveryNotice}
	<div class="border border-emerald-500/30 bg-emerald-500/12 px-4 py-3 text-sm text-emerald-100 shadow-lg backdrop-blur-md" role="status">
		<span class="font-semibold">Conexiune restabilită.</span>
		Betfront poate actualiza din nou fluxurile live și cererile în așteptare.
	</div>
{/if}
