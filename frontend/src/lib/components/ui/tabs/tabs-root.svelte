<script lang="ts">
	import { Tabs as TabsPrimitive } from "bits-ui";
	import { cn } from "$lib/utils.js";

	let {
		class: className,
		value = $bindable(),
		...restProps
	}: TabsPrimitive.RootProps = $props();
</script>

<TabsPrimitive.Root class={cn("", className)} bind:value {...restProps}>
	{@render restProps.children?.()}
</TabsPrimitive.Root>
