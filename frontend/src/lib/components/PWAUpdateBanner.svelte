<script lang="ts">
	import { updated } from '$app/state';
	import { onMount } from 'svelte';
	import { betslipHasUnsavedDraft } from '$lib/stores/betslip';

	let waitingRegistration = $state<ServiceWorkerRegistration | null>(null);
	let dismissed = $state(false);
	let reloadAfterActivation = false;
	const hasVersionUpdate = $derived(updated.current);
	const showBanner = $derived((!!waitingRegistration || hasVersionUpdate) && !dismissed);

	async function inspectRegistration() {
		const registration = await navigator.serviceWorker.getRegistration();
		if (!registration) {
			return;
		}

		if (registration.waiting && navigator.serviceWorker.controller) {
			waitingRegistration = registration;
		}

		registration.addEventListener('updatefound', () => {
			const worker = registration.installing;
			if (!worker) {
				return;
			}

			worker.addEventListener('statechange', () => {
				if (worker.state === 'installed' && navigator.serviceWorker.controller) {
					waitingRegistration = registration;
					dismissed = false;
				}
			});
		});
	}

	async function applyUpdate() {
		const confirmed = window.confirm($betslipHasUnsavedDraft
			? 'Ai un bilet nefinalizat. Selecțiile sunt păstrate în sesiunea acestui browser, dar alte formulare deschise se pot pierde. Continui?'
			: 'Reîncărcarea poate pierde modificările din formularele nefinalizate. Continui?');
		if (!confirmed) {
			return;
		}

		if (waitingRegistration?.waiting) {
			reloadAfterActivation = true;
			waitingRegistration.waiting.postMessage({ type: 'SKIP_WAITING' });
			return;
		}

		const updateDetected = await updated.check();
		if (updateDetected || updated.current) {
			window.location.reload();
		}
	}

	onMount(() => {
		if (!('serviceWorker' in navigator)) {
			return;
		}

		void inspectRegistration();
		void updated.check().catch(() => false);

		const handleVisibilityChange = () => {
			if (document.visibilityState === 'visible') {
				void updated.check().catch(() => false);
				void inspectRegistration();
			}
		};

		const handleControllerChange = () => {
			if (!reloadAfterActivation) {
				return;
			}
			reloadAfterActivation = false;
			window.location.reload();
		};

		document.addEventListener('visibilitychange', handleVisibilityChange);
		navigator.serviceWorker.addEventListener('controllerchange', handleControllerChange);

		return () => {
			document.removeEventListener('visibilitychange', handleVisibilityChange);
			navigator.serviceWorker.removeEventListener('controllerchange', handleControllerChange);
		};
	});
</script>

{#if showBanner}
	<div class="border border-fuchsia-500/30 bg-fuchsia-500/12 px-4 py-3 text-sm text-fuchsia-50 shadow-lg backdrop-blur-md">
		<div class="flex items-start justify-between gap-3">
			<div>
				<div class="font-semibold">Actualizare disponibilă</div>
				<p class="mt-1 text-fuchsia-100/85">
					O versiune nouă Bet este pregătită.
					{#if $betslipHasUnsavedDraft}
						Biletul curent este păstrat în sesiunea browserului înainte de reîncărcare.
					{:else}
						Reîncarcă pentru a aplica rutele, vizualizările și resursele actualizate.
					{/if}
				</p>
			</div>
			<div class="flex shrink-0 items-center gap-2">
				<button
					type="button"
					class="min-h-11 border border-fuchsia-300/30 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-fuchsia-50 transition hover:bg-fuchsia-400/10"
					onclick={() => (dismissed = true)}
				>
					Închide
				</button>
				<button
					type="button"
					class="min-h-11 bg-fuchsia-300 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-950 transition hover:bg-fuchsia-200"
					onclick={applyUpdate}
				>
					Reîncarcă
				</button>
			</div>
		</div>
	</div>
{/if}
