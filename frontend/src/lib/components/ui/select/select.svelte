<script lang="ts">
	import type { Snippet } from "svelte";
	import type { HTMLSelectAttributes } from "svelte/elements";
	import { cn } from "$lib/utils.js";

	let {
		class: className,
		children,
		value = $bindable(),
		...restProps
	}: HTMLSelectAttributes & { children?: Snippet } = $props();
</script>

<select
	class={cn(
		"flex h-10 w-full items-center justify-between  border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
		className
	)}
	bind:value
	{...restProps}
>
	{@render children?.()}
</select>
