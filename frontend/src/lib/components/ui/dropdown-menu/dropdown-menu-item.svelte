<script lang="ts">
	import { DropdownMenu as DropdownMenuPrimitive } from "bits-ui";
	import { cn } from "$lib/utils.js";

	let {
		class: className,
		inset,
		...restProps
	}: DropdownMenuPrimitive.ItemProps & { inset?: boolean } = $props();
</script>

<DropdownMenuPrimitive.Item
	class={cn(
		"relative flex cursor-default select-none items-center  px-2 py-1.5 text-sm outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
		inset && "pl-8",
		className
	)}
	{...restProps}
>
	{@render restProps.children?.()}
</DropdownMenuPrimitive.Item>
