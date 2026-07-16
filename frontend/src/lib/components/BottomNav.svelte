<script lang="ts">
	import { page } from '$app/stores';
	import { Menu } from 'lucide-svelte';
	import { isNavigationActive, workspaceNavigation } from '$lib/navigation';
	import { cn } from '$lib/utils';

	let { onOpenNavigation }: { onOpenNavigation: () => void } = $props();
	const primaryTabs = workspaceNavigation.filter((item) => item.href !== '/monitoring');

	function isActive(href: string): boolean {
		return isNavigationActive($page.url.pathname, href);
	}
</script>

<nav class="mobile-bottom-nav fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-background/95 backdrop-blur-xl lg:hidden" aria-label="Navigarea principală a spațiului de lucru">
	<div class="flex h-16 items-center justify-around">
		{#each primaryTabs as tab (tab.href)}
			<a href={tab.href} aria-current={isActive(tab.href) ? 'page' : undefined} aria-label={tab.label} class={cn('flex h-full min-w-0 flex-1 flex-col items-center justify-center gap-1 px-0.5 text-[10px] font-medium transition-colors sm:text-xs', isActive(tab.href) ? 'text-primary' : 'text-muted-foreground hover:text-foreground')}>
				<tab.icon class="h-5 w-5" aria-hidden="true" />
				<span class="max-w-full truncate">{tab.label}</span>
			</a>
		{/each}
		<button type="button" class="flex h-full min-w-0 flex-1 flex-col items-center justify-center gap-1 px-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground sm:text-xs" onclick={onOpenNavigation} aria-label="Deschide navigarea completă">
			<Menu class="h-5 w-5" aria-hidden="true" />
			<span>Mai mult</span>
		</button>
	</div>
</nav>
