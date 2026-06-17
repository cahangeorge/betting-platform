<script lang="ts">
	import { Tabs as TabsPrimitive } from "bits-ui";
	import { cn } from "$lib/utils.js";

	let {
		class: className,
		...restProps
	}: TabsPrimitive.ListProps = $props();
</script>

<TabsPrimitive.List
	class={cn(
		"inline-flex h-10 items-center justify-center  bg-muted p-1 text-muted-foreground",
		className
	)}
	{...restProps}
>
	{@render restProps.children?.()}
</TabsPrimitive.List>
