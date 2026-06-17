<script lang="ts">
	import { Dialog as DialogPrimitive } from "bits-ui";
	import { cn } from "$lib/utils.js";
	import type { Snippet } from "svelte";
	import { slide } from "svelte/transition";

	type Side = "top" | "bottom" | "left" | "right";

	let {
		class: className,
		side = "right",
		children,
		...restProps
	}: DialogPrimitive.ContentProps & { side?: Side; children?: Snippet } = $props();

	const sideTransitions: Record<Side, { transition: typeof slide; params: Record<string, unknown> }> = {
		right: { transition: slide, params: { direction: "left", duration: 300 } },
		left: { transition: slide, params: { direction: "right", duration: 300 } },
		top: { transition: slide, params: { direction: "down", duration: 300 } },
		bottom: { transition: slide, params: { direction: "up", duration: 300 } }
	};

	const sideClasses: Record<Side, string> = {
		right: "inset-y-0 right-0 h-full w-3/4 border-l data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right sm:max-w-sm",
		left: "inset-y-0 left-0 h-full w-3/4 border-r data-[state=open]:slide-in-from-left data-[state=closed]:slide-out-to-left sm:max-w-sm",
		top: "inset-x-0 top-0 border-b data-[state=open]:slide-in-from-top data-[state=closed]:slide-out-to-top",
		bottom: "inset-x-0 bottom-0 border-t data-[state=open]:slide-in-from-bottom data-[state=closed]:slide-out-to-bottom"
	};
</script>

<DialogPrimitive.Content
	class={cn(
		"fixed z-50 gap-4 bg-background p-6 shadow-lg transition ease-in-out data-[state=closed]:duration-300 data-[state=open]:duration-500 data-[state=open]:animate-in data-[state=closed]:animate-in data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
		sideClasses[side],
		className
	)}
	{...restProps}
>
	{@render children?.()}
</DialogPrimitive.Content>
