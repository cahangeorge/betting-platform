<script lang="ts">
	import { Sun, Moon } from 'lucide-svelte';

	let theme = $state<'light' | 'dark'>('dark');

	$effect(() => {
		const stored = localStorage.getItem('theme');
		if (stored === 'light' || stored === 'dark') {
			theme = stored;
		} else {
			theme = 'dark';
		}
		document.documentElement.classList.toggle('dark', theme === 'dark');
		document.documentElement.classList.toggle('light', theme === 'light');
	});

	function toggle() {
		theme = theme === 'dark' ? 'light' : 'dark';
		localStorage.setItem('theme', theme);
		document.documentElement.classList.toggle('dark', theme === 'dark');
		document.documentElement.classList.toggle('light', theme === 'light');
	}
</script>

<button
	onclick={toggle}
	class="inline-flex items-center justify-center h-9 w-9  border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground cursor-pointer"
	aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
>
	{#if theme === 'dark'}
		<Sun class="h-5 w-5" />
	{:else}
		<Moon class="h-5 w-5" />
	{/if}
</button>
