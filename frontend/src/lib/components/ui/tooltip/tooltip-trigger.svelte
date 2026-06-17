<script lang="ts">
	import { Tooltip as TooltipPrimitive } from "bits-ui";
	import { cn } from "$lib/utils.js";

	let {
		class: className,
		...restProps
	}: TooltipPrimitive.TriggerProps = $props();
</script>

<TooltipPrimitive.Trigger class={cn("", className)} {...restProps}>
	{@render restProps.children?.()}
</TooltipPrimitive.Trigger>
