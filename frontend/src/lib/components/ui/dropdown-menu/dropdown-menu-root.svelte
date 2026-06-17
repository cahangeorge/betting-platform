<script lang="ts">
	import { DropdownMenu as DropdownMenuPrimitive } from "bits-ui";

	let {
		...restProps
	}: DropdownMenuPrimitive.RootProps = $props();
</script>

<DropdownMenuPrimitive.Root {...restProps}>
	{#if restProps.children}
		{@render restProps.children()}
	{/if}
</DropdownMenuPrimitive.Root>
