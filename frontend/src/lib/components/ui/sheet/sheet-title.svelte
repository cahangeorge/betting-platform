<script lang="ts">
	import { Dialog as DialogPrimitive } from "bits-ui";
	import { cn } from "$lib/utils.js";

	let {
		class: className,
		...restProps
	}: DialogPrimitive.TitleProps = $props();
</script>

<DialogPrimitive.Title
	class={cn("text-lg font-semibold text-foreground", className)}
	{...restProps}
>
	{@render restProps.children?.()}
</DialogPrimitive.Title>
