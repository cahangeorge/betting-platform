<script lang="ts">
	import '../app.css';
	import { dev } from '$app/environment';
	import { afterNavigate } from '$app/navigation';
	import { navigating, page } from '$app/stores';
	import { onMount } from 'svelte';
	import { fade, slide } from 'svelte/transition';
	import BetslipFAB from '$lib/components/BetslipFAB.svelte';
	import BottomNav from '$lib/components/BottomNav.svelte';
	import CommandPalette from '$lib/components/CommandPalette.svelte';
	import Loading from '$lib/components/Loading.svelte';
	import Navbar from '$lib/components/Navbar.svelte';
	import PWAConnectivityBanner from '$lib/components/PWAConnectivityBanner.svelte';
	import PWAInstallPrompt from '$lib/components/PWAInstallPrompt.svelte';
	import PWAUpdateBanner from '$lib/components/PWAUpdateBanner.svelte';
	import SeoHead from '$lib/components/SeoHead.svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import { betslipHasLegs } from '$lib/stores/betslip';
	import { liveSocket } from '$lib/stores/liveSocket';
	import type { User } from '$lib/types';

	let {
		children,
		data
	}: {
		children: import('svelte').Snippet;
		data: {
			user: User | null;
		};
	} = $props();

	let sidebarOpen = $state(false);
	let betslipOpen = $state(false);
	let commandPaletteOpen = $state(false);
	let isNavigating = $derived(Boolean($navigating));
	let betslipModule = $state<Promise<typeof import('$lib/components/BetSlipDrawer.svelte')> | null>(null);

	const shelllessRoutes = ['/login', '/signup', '/about', '/methodology', '/responsible-gambling', '/terms', '/privacy'];
	const useAppShell = $derived.by(
		() => !shelllessRoutes.some((route) => $page.url.pathname.startsWith(route))
	);

	function toggleSidebar() {
		sidebarOpen = !sidebarOpen;
	}

	function openBetslip() {
		if (!betslipModule) {
			betslipModule = import('$lib/components/BetSlipDrawer.svelte');
		}
		betslipOpen = true;
	}

	function openCommandPalette() {
		commandPaletteOpen = true;
	}

	function handleGlobalShortcut(event: KeyboardEvent) {
		const modifier = event.metaKey || event.ctrlKey;
		const shortcut = (modifier || event.altKey) && event.key.toLowerCase() === 'k';
		if (shortcut) {
			event.preventDefault();
			if (commandPaletteOpen) {
				commandPaletteOpen = false;
			} else {
				openCommandPalette();
			}
		}
	}

	afterNavigate(() => {
		sidebarOpen = false;
		betslipOpen = false;
	});

	onMount(() => {
		if (dev && 'serviceWorker' in navigator) {
			void (async () => {
				const registrations = await navigator.serviceWorker.getRegistrations();
				await Promise.all(registrations.map((registration) => registration.unregister()));

				if ('caches' in window) {
					const keys = await caches.keys();
					await Promise.all(keys.map((key) => caches.delete(key)));
				}
			})();
		}

		liveSocket.connect();
		return () => {
			liveSocket.disconnect();
		};
	});
</script>

<SeoHead />

<svelte:window onkeydown={handleGlobalShortcut} />

<a href="#main-content" class="sr-only-focusable">Sari la conținutul principal</a>

<div class="min-h-screen bg-background">
	<Navbar
		user={data.user}
		onToggleSidebar={toggleSidebar}
		onOpenCommandPalette={openCommandPalette}
		showWorkspaceMenu={useAppShell}
	/>

	<div class="pointer-events-none fixed inset-x-0 top-18 z-50 flex justify-center px-4">
		<div class="pointer-events-auto flex w-full max-w-2xl flex-col gap-2">
			<PWAUpdateBanner />
			<PWAInstallPrompt />
			<PWAConnectivityBanner />
		</div>
	</div>

	{#if useAppShell}
		<Sidebar bind:open={sidebarOpen} user={data.user} />
	{/if}

		<main
			id="main-content"
			tabindex="-1"
		class={useAppShell
			? 'mobile-shell-bottom-space min-h-[calc(100vh-4rem)] min-w-0 pt-16 lg:pl-16 xl:pl-60'
			: 'min-h-[calc(100vh-4rem)] pt-16'}
	>
		<div class={useAppShell ? 'min-w-0 max-w-none p-4 lg:p-6 xl:p-8' : 'mx-auto w-full max-w-7xl p-4 lg:p-6'}>
			{#if isNavigating}
				<div class="flex items-center justify-center py-20" transition:fade={{ duration: 150 }}>
					<Loading message="Se încarcă pagina..." />
				</div>
			{:else}
				{#key $page.url.pathname}
					<div class="min-w-0" transition:fade={{ duration: 200, delay: 50 }}>
						{@render children()}
					</div>
				{/key}
			{/if}
		</div>
	</main>

	{#if useAppShell}
		{#if $betslipHasLegs}
			<BetslipFAB onclick={openBetslip} />
		{/if}

		{#if betslipOpen}
			<div class="fixed inset-0 z-50" transition:fade={{ duration: 150 }}>
				<button
					class="absolute inset-0 bg-black/50 backdrop-blur-sm"
					onclick={() => (betslipOpen = false)}
					aria-label="Închide biletul de selecții"
				></button>
				<div
					class="absolute inset-x-0 bottom-0 max-h-[85vh] overflow-hidden border-t border-border bg-card pb-safe lg:inset-x-auto lg:bottom-6 lg:right-6 lg:max-h-[calc(100vh-7rem)] lg:w-[26rem] lg:border"
					transition:slide={{ duration: 250, axis: 'y' }}
				>
					<div class="h-full overflow-y-auto scroll-thin">
						{#if betslipModule}
							{#await betslipModule}
								<div class="flex min-h-40 items-center justify-center p-6" role="status" aria-live="polite">
									<Loading message="Se încarcă biletul de selecții..." />
								</div>
							{:then module}
								<module.default bind:open={betslipOpen} />
							{:catch}
								<div class="flex min-h-40 flex-col items-center justify-center gap-3 p-6 text-center" role="alert">
									<p class="text-sm text-[hsl(var(--status-danger-text))]">Biletul de selecții nu a putut fi încărcat.</p>
									<button class="touch-target border border-border px-4 text-sm font-medium" onclick={() => (betslipModule = import('$lib/components/BetSlipDrawer.svelte'))}>Reîncearcă</button>
								</div>
							{/await}
						{:else}
							<div class="flex min-h-40 items-center justify-center p-6" role="status" aria-live="polite">
								<Loading message="Se încarcă biletul de selecții..." />
							</div>
						{/if}
					</div>
				</div>
			</div>
		{/if}

		<BottomNav onOpenNavigation={toggleSidebar} />
	{/if}
</div>

{#if commandPaletteOpen}
	<CommandPalette onClose={() => (commandPaletteOpen = false)} />
{/if}
