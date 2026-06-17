<script lang="ts">
	import type { Snippet } from 'svelte';
	import { fade } from 'svelte/transition';
	import TabsRoot from './tabs/tabs-root.svelte';
	import TabsList from './tabs/tabs-list.svelte';
	import TabsTrigger from './tabs/tabs-trigger.svelte';
	import TabsContent from './tabs/tabs-content.svelte';

	let {
		tabs,
		activeTab = $bindable(),
		children
	}: {
		tabs: { id: string; label: string; count?: number }[];
		activeTab: string;
		children?: Snippet;
	} = $props();
</script>

<div class="w-full">
	<TabsRoot bind:value={activeTab}>
		<TabsList class="w-full justify-start  border-b bg-transparent p-0 h-auto">
			{#each tabs as tab (tab.id)}
				<TabsTrigger
					value={tab.id}
					class=" border-b-2 border-transparent px-4 py-3 text-sm font-medium data-[state=active]:border-primary data-[state=active]:shadow-none transition-colors duration-200"
				>
					{tab.label}
					{#if tab.count !== undefined}
						<span class="ml-2  bg-muted px-2 py-0.5 text-xs font-mono">
							{tab.count}
						</span>
					{/if}
				</TabsTrigger>
			{/each}
		</TabsList>
		{#if children}
			<TabsContent value={activeTab} class="mt-0">
				{#key activeTab}
					<div in:fade={{ duration: 200 }}>
						{@render children()}
					</div>
				{/key}
			</TabsContent>
		{/if}
	</TabsRoot>
</div>
