<script lang="ts">
	import { onMount } from 'svelte';

	type BeforeInstallPromptEvent = Event & {
		prompt: () => Promise<void>;
		userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>;
	};

	const DISMISS_KEY = 'betfront:pwa-install-dismissed';

	let deferredPrompt = $state<BeforeInstallPromptEvent | null>(null);
	let dismissed = $state(false);
	let isStandalone = $state(false);

	function dismissPrompt() {
		dismissed = true;
		localStorage.setItem(DISMISS_KEY, '1');
	}

	async function installApp() {
		if (!deferredPrompt) {
			return;
		}

		await deferredPrompt.prompt();
		const choice = await deferredPrompt.userChoice;
		deferredPrompt = null;

		if (choice.outcome === 'accepted') {
			localStorage.removeItem(DISMISS_KEY);
			dismissed = true;
			return;
		}

		dismissPrompt();
	}

	onMount(() => {
		isStandalone =
			window.matchMedia('(display-mode: standalone)').matches ||
			(window.navigator as Navigator & { standalone?: boolean }).standalone === true;
		dismissed = localStorage.getItem(DISMISS_KEY) === '1';

		const handleBeforeInstallPrompt = (event: Event) => {
			event.preventDefault();
			deferredPrompt = event as BeforeInstallPromptEvent;
		};

		const handleInstalled = () => {
			deferredPrompt = null;
			dismissed = true;
			localStorage.removeItem(DISMISS_KEY);
		};

		window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
		window.addEventListener('appinstalled', handleInstalled);

		return () => {
			window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
			window.removeEventListener('appinstalled', handleInstalled);
		};
	});
</script>

{#if deferredPrompt && !dismissed && !isStandalone}
	<div class="rounded-xl border border-sky-500/30 bg-sky-500/12 px-4 py-3 text-sm text-sky-50 shadow-lg backdrop-blur-md">
		<div class="flex items-start justify-between gap-3">
			<div>
				<div class="font-semibold">Install Betfront</div>
				<p class="mt-1 text-sky-100/85">
					Add the platform to your home screen for faster launch, standalone navigation, and cached route access.
				</p>
			</div>
			<div class="flex shrink-0 items-center gap-2">
				<button
					type="button"
					class="border border-sky-300/30 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-sky-50 transition hover:bg-sky-400/10"
					onclick={dismissPrompt}
				>
					Later
				</button>
				<button
					type="button"
					class="bg-sky-300 px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-950 transition hover:bg-sky-200"
					onclick={installApp}
				>
					Install
				</button>
			</div>
		</div>
	</div>
{/if}
