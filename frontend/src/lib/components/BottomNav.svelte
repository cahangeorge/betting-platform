<script lang="ts">
	import { page } from '$app/stores';
	import { Menu } from 'lucide-svelte';
	import { isNavigationActive, workspaceNavigation } from '$lib/navigation';
	import { cn } from '$lib/utils';

	let { onOpenNavigation }: { onOpenNavigation: () => void } = $props();
	const primaryTabs = workspaceNavigation.filter((item) => ['Home', 'Prepare', 'Analyze', 'Tickets'].includes(item.label));

	function isActive(href: string): boolean {
		return isNavigationActive($page.url.pathname, href);
	}
</script>

<nav class="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-background/95 backdrop-blur-xl lg:hidden" aria-label="Primary workspace navigation" style="padding-bottom: env(safe-area-inset-bottom, 0px);">
	<div class="flex h-16 items-center justify-around">
		{#each primaryTabs as tab (tab.href)}
			<a href={tab.href} aria-current={isActive(tab.href) ? 'page' : undefined} class={cn('flex h-full w-full flex-col items-center justify-center gap-1 text-[10px] font-medium transition-colors', isActive(tab.href) ? 'text-primary' : 'text-muted-foreground hover:text-foreground')}>
				<tab.icon class="h-5 w-5" />
				<span>{tab.label}</span>
			</a>
		{/each}
		<button type="button" class="flex h-full w-full flex-col items-center justify-center gap-1 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground" onclick={onOpenNavigation} aria-label="Open workspace navigation">
			<Menu class="h-5 w-5" />
			<span>More</span>
		</button>
	</div>
</nav>
