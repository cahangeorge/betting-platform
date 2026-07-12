<script lang="ts">
	import '../app.css';
	import { dev } from '$app/environment';
	import { navigating, page } from '$app/stores';
	import { onMount } from 'svelte';
	import { fade, slide } from 'svelte/transition';
	import BetSlipDrawer from '$lib/components/BetSlipDrawer.svelte';
	import BetslipFAB from '$lib/components/BetslipFAB.svelte';
	import BottomNav from '$lib/components/BottomNav.svelte';
	import CommandPalette from '$lib/components/CommandPalette.svelte';
	import Loading from '$lib/components/Loading.svelte';
	import Navbar from '$lib/components/Navbar.svelte';
	import PWAConnectivityBanner from '$lib/components/PWAConnectivityBanner.svelte';
	import PWAInstallPrompt from '$lib/components/PWAInstallPrompt.svelte';
	import PWAUpdateBanner from '$lib/components/PWAUpdateBanner.svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import { betslipHasLegs } from '$lib/stores/betslip';
	import { liveSocket } from '$lib/stores/liveSocket';

	let {
		children,
		data
	}: {
		children: import('svelte').Snippet;
		data: {
			user: { name: string; email: string } | null;
		};
	} = $props();

	let sidebarOpen = $state(false);
	let betslipOpen = $state(false);
	let commandPaletteOpen = $state(false);
	let isNavigating = $state(false);
	let prevUrl = $state('');

	const shelllessRoutes = ['/login', '/signup', '/about'];
	const useAppShell = $derived.by(
		() => !shelllessRoutes.some((route) => $page.url.pathname.startsWith(route))
	);

	function toggleSidebar() {
		sidebarOpen = !sidebarOpen;
	}

	$effect(() => {
		const unsub = navigating.subscribe((nav) => {
			isNavigating = !!nav;
			if (nav?.to && nav.to.url.pathname !== prevUrl) {
				sidebarOpen = false;
				betslipOpen = false;
				prevUrl = nav.to.url.pathname;
			}
		});
		return unsub;
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

<a href="#main-content" class="sr-only-focusable">Skip to main content</a>

<div class="min-h-screen bg-background">
	<Navbar
		user={data.user}
		onToggleSidebar={toggleSidebar}
		onOpenCommandPalette={() => (commandPaletteOpen = true)}
	/>

	<div class="pointer-events-none fixed inset-x-0 top-18 z-50 flex justify-center px-4">
		<div class="pointer-events-auto flex w-full max-w-2xl flex-col gap-2">
			<PWAUpdateBanner />
			<PWAInstallPrompt />
			<PWAConnectivityBanner />
		</div>
	</div>

	{#if useAppShell}
		<div class="hidden min-h-screen min-w-0 pt-16 lg:block">
			<Sidebar bind:open={sidebarOpen} user={data.user} />

			<main id="main-content" class="min-h-[calc(100vh-4rem)] min-w-0 pl-16 xl:pl-60">
				<div class="min-w-0 max-w-none p-5 lg:p-6 xl:p-8">
					{#if isNavigating}
						<div class="flex items-center justify-center py-20" transition:fade={{ duration: 150 }}>
							<Loading message="Loading..." />
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

		</div>

		<div class="hidden lg:block">
			{#if $betslipHasLegs}
				<BetslipFAB onclick={() => (betslipOpen = true)} />
			{/if}
			{#if betslipOpen}
				<div class="fixed inset-0 z-50" transition:fade={{ duration: 150 }}>
					<button class="absolute inset-0 bg-black/50 backdrop-blur-sm" onclick={() => (betslipOpen = false)} aria-label="Close bet slip"></button>
					<div class="absolute bottom-6 right-6 max-h-[calc(100vh-7rem)] w-[26rem] overflow-hidden border border-border bg-card" transition:slide={{ duration: 250, axis: 'y' }}>
						<div class="h-full overflow-y-auto scroll-thin"><BetSlipDrawer bind:open={betslipOpen} /></div>
					</div>
				</div>
			{/if}
		</div>

		<div class="pb-16 pt-16 lg:hidden">
			{#if sidebarOpen}
				<Sidebar bind:open={sidebarOpen} user={data.user} />
			{/if}

			<main id="main-content" class="min-h-[calc(100vh-4rem)] min-w-0">
				<div class="min-w-0 max-w-none p-4">
					{#if isNavigating}
						<div class="flex items-center justify-center py-20" transition:fade={{ duration: 150 }}>
							<Loading message="Loading..." />
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

			{#if $betslipHasLegs}
				<BetslipFAB onclick={() => (betslipOpen = true)} />
			{/if}

			{#if betslipOpen}
				<div class="fixed inset-0 z-50 lg:hidden" transition:fade={{ duration: 150 }}>
					<button
						class="absolute inset-0 bg-black/50 backdrop-blur-sm"
						onclick={() => (betslipOpen = false)}
						aria-label="Close bet slip"
					></button>
					<div
						class="absolute bottom-0 left-0 right-0 max-h-[85vh] overflow-hidden border-t border-border bg-card"
						style="padding-bottom: env(safe-area-inset-bottom, 0px);"
						transition:slide={{ duration: 250, axis: 'y' }}
					>
						<div class="h-full overflow-y-auto scroll-thin">
							<BetSlipDrawer bind:open={betslipOpen} />
						</div>
					</div>
				</div>
			{/if}

			<BottomNav onOpenNavigation={toggleSidebar} />
		</div>
	{:else}
		<main id="main-content" class="min-h-[calc(100vh-4rem)] pt-16">
			<div class="mx-auto w-full max-w-7xl p-4 lg:p-6">
				{#if isNavigating}
					<div class="flex items-center justify-center py-20" transition:fade={{ duration: 150 }}>
						<Loading message="Loading..." />
					</div>
				{:else}
					{#key $page.url.pathname}
						<div transition:fade={{ duration: 200, delay: 50 }}>
							{@render children()}
						</div>
					{/key}
				{/if}
			</div>
		</main>
	{/if}
</div>

<CommandPalette bind:open={commandPaletteOpen} />
