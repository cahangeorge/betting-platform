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
	<div class="rounded-xl border border-amber-500/30 bg-amber-500/12 px-4 py-3 text-sm text-amber-100 shadow-lg backdrop-blur-md">
		<span class="font-semibold">Offline mode.</span>
		Cached pages remain available, but live odds, scraping, predictions, and bet placement may fail until the connection returns.
	</div>
{:else if showRecoveryNotice}
	<div class="rounded-xl border border-emerald-500/30 bg-emerald-500/12 px-4 py-3 text-sm text-emerald-100 shadow-lg backdrop-blur-md">
		<span class="font-semibold">Back online.</span>
		Betfront can refresh live feeds and sync queued requests again.
	</div>
{/if}
