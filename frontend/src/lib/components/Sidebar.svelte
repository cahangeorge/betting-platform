<script lang="ts">
	import { page } from '$app/stores';
	import { Info, User } from 'lucide-svelte';
	import {
		configurationNavigation,
		isNavigationActive,
		utilityNavigation,
		workspaceNavigation
	} from '$lib/navigation';
	import { cn } from '$lib/utils';
	import { ThemeToggle } from './ui/theme-toggle';
	import type { User as AuthenticatedUser } from '$lib/types';
	import {
		SheetContent,
		SheetRoot
	} from './ui/sheet';

	let {
		open = $bindable(false),
		user
	}: {
		open: boolean;
		user: AuthenticatedUser | null;
	} = $props();

	function isActive(href: string): boolean {
		return isNavigationActive($page.url.pathname, href);
	}

	function itemClass(href: string): string {
		return cn(
			'group flex items-center gap-3 border-l-2 px-3 py-2.5 text-sm font-medium transition-colors',
			isActive(href)
				? 'border-primary bg-primary/10 text-primary'
				: 'border-transparent text-muted-foreground hover:bg-muted hover:text-foreground'
		);
	}
</script>

{#if open}
	<SheetRoot bind:open={open}>
		<SheetContent side="left" class="w-[272px] border-border bg-card p-0">
			<div class="flex h-full flex-col">
				<div class="border-b border-border px-5 py-5">
					<p class="text-sm font-semibold text-foreground">Spațiu de decizie</p>
					<p class="mt-1 text-xs text-muted-foreground">Pregătește, analizează și revizuiește cu context.</p>
				</div>
				<nav class="flex-1 space-y-6 overflow-y-auto p-3" aria-label="Navigarea spațiului de lucru">
					<div>
						<p class="px-3 pb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Flux principal</p>
						{#each workspaceNavigation as item (item.href)}
							<a href={item.href} class={itemClass(item.href)} aria-current={isActive(item.href) ? 'page' : undefined} onclick={() => (open = false)}>
								<item.icon class="h-4 w-4 shrink-0" />
								<span>{item.label}</span>
							</a>
						{/each}
					</div>
					<div>
						<p class="px-3 pb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Instrumente</p>
						{#each utilityNavigation as item (item.href)}
							<a href={item.href} class={itemClass(item.href)} aria-current={isActive(item.href) ? 'page' : undefined} onclick={() => (open = false)}>
								<item.icon class="h-4 w-4 shrink-0" />
								<span>{item.label}</span>
							</a>
						{/each}
					</div>
					<div>
						<p class="px-3 pb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Configurații</p>
						{#each configurationNavigation as item (item.href)}
							<a href={item.href} class={itemClass(item.href)} aria-current={isActive(item.href) ? 'page' : undefined} onclick={() => (open = false)}>
								<item.icon class="h-4 w-4 shrink-0" />
								<span>{item.label}</span>
							</a>
						{/each}
					</div>
				</nav>
				<div class="border-t border-border p-4">
					<div class="flex items-center justify-between gap-3">
						<div class="min-w-0">
							<p class="truncate text-xs font-medium text-foreground">{user?.name ?? 'Spațiu demonstrativ'}</p>
							<p class="truncate text-xs text-muted-foreground">{user?.email ?? 'Autentifică-te pentru a salva lucrul'}</p>
						</div>
						<ThemeToggle />
					</div>
				</div>
			</div>
		</SheetContent>
	</SheetRoot>
{/if}

<aside class="fixed left-0 top-16 z-30 hidden h-[calc(100vh-4rem)] w-16 border-r border-border bg-card/90 backdrop-blur-xl lg:block xl:w-60" aria-label="Navigarea spațiului de lucru">
	<nav class="flex h-full flex-col justify-between p-2 xl:p-3">
		<div class="space-y-6 overflow-y-auto">
			<div>
				<p class="hidden px-3 pb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground xl:block">Flux principal</p>
				{#each workspaceNavigation as item (item.href)}
					<a href={item.href} class={itemClass(item.href)} aria-current={isActive(item.href) ? 'page' : undefined} title={item.label}>
						<item.icon class="h-4 w-4 shrink-0" />
						<span class="hidden xl:inline">{item.label}</span>
					</a>
				{/each}
			</div>
			<div>
				<p class="hidden px-3 pb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground xl:block">Instrumente</p>
				{#each utilityNavigation as item (item.href)}
					<a href={item.href} class={itemClass(item.href)} aria-current={isActive(item.href) ? 'page' : undefined} title={item.label}>
						<item.icon class="h-4 w-4 shrink-0" />
						<span class="hidden xl:inline">{item.label}</span>
					</a>
				{/each}
			</div>
			<div>
				<p class="hidden px-3 pb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground xl:block">Configurații</p>
				{#each configurationNavigation as item (item.href)}
					<a href={item.href} class={itemClass(item.href)} aria-current={isActive(item.href) ? 'page' : undefined} title={item.label}>
						<item.icon class="h-4 w-4 shrink-0" />
						<span class="hidden xl:inline">{item.label}</span>
					</a>
				{/each}
			</div>
		</div>
		<div class="space-y-3 border-t border-border px-1 pt-3 xl:px-2">
			<div class="hidden items-center gap-2 text-xs text-muted-foreground xl:flex"><Info class="h-3.5 w-3.5" /> Starea datelor live este afișată în fiecare secțiune.</div>
			<div class="flex items-center justify-center gap-2 xl:justify-between">
				<a href="/settings/account" class="hidden min-w-0 items-center gap-2 xl:flex"><User class="h-3.5 w-3.5 text-muted-foreground" /><span class="truncate text-xs text-muted-foreground">{user?.name ?? 'Vizitator'}</span></a>
				<ThemeToggle />
			</div>
		</div>
	</nav>
</aside>
