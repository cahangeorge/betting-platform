<script lang="ts">
	import { page } from '$app/stores';
	import { Home, BarChart3, Ticket, Download, User } from 'lucide-svelte';
	import { cn } from '$lib/utils';

	const primaryTabs = [
		{ href: '/', label: 'Dashboard', icon: Home },
		{ href: '/scrape', label: 'Scrape', icon: Download },
		{ href: '/predict', label: 'Predict', icon: BarChart3 },
		{ href: '/tickets', label: 'Tickets', icon: Ticket },
		{ href: '/account', label: 'Account', icon: User }
	];

	function isActive(href: string): boolean {
		if (href === '/') return $page.url.pathname === '/';
		return $page.url.pathname.startsWith(href);
	}
</script>

<nav
	class="fixed bottom-0 left-0 right-0 z-40 lg:hidden border-t border-border bg-background/80 backdrop-blur-xl"
	aria-label="Primary workflow navigation"
	style="padding-bottom: env(safe-area-inset-bottom, 0px);"
>
	<div class="flex items-center justify-around h-16">
		{#each primaryTabs as tab (tab.href)}
			<a
				href={tab.href}
				aria-label={tab.label}
				aria-current={isActive(tab.href) ? 'page' : undefined}
				class={cn(
					'flex flex-col items-center justify-center gap-0.5 w-full h-full transition-colors duration-200',
					isActive(tab.href)
						? 'text-football-green'
						: 'text-muted-foreground hover:text-foreground'
				)}
			>
				<tab.icon class="w-5 h-5" />
				<span class="text-[10px] font-medium">{tab.label}</span>
			</a>
		{/each}
	</div>
</nav>
