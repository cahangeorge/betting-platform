<script lang="ts">
	let {
		size = 'md',
		message = 'Loading...'
	}: {
		size?: 'sm' | 'md' | 'lg';
		message?: string;
	} = $props();

	const sizeClasses: Record<string, string> = {
		sm: 'w-5 h-5',
		md: 'w-10 h-10',
		lg: 'w-14 h-14'
	};
</script>

<div class="flex flex-col items-center justify-center space-y-3">
	<div class="relative {sizeClasses[size]}">
		<div class="absolute inset-0 border-2  border-muted border-t-football-green animate-spin"></div>
		<div class="absolute inset-1 border-2  border-transparent border-t-football-blue animate-spin" style="animation-direction: reverse; animation-duration: 0.8s;"></div>
	</div>
	{#if message}
		<p class="text-sm font-mono text-muted-foreground">{message}</p>
	{/if}
</div>
