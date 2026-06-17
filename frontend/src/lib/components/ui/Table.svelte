<script lang="ts">
	import { cn } from '$lib/utils';
	import TableRoot from './table/table.svelte';
	import TableHeader from './table/table-header.svelte';
	import TableBody from './table/table-body.svelte';
	import TableRow from './table/table-row.svelte';
	import TableHead from './table/table-head.svelte';
	import TableCell from './table/table-cell.svelte';

	let {
		columns,
		rows,
		loading = false,
		emptyMessage = 'No data available'
	}: {
		columns: { key: string; label: string; sortable?: boolean; class?: string }[];
		rows: Record<string, unknown>[];
		loading?: boolean;
		emptyMessage?: string;
	} = $props();
</script>

<TableRoot>
	<TableHeader>
		<TableRow>
			{#each columns as col (col.key)}
				<TableHead class={col.class}>{col.label}</TableHead>
			{/each}
		</TableRow>
	</TableHeader>
	<TableBody>
		{#if loading}
			<TableRow>
				<TableCell class="h-24 text-center" colspan={columns.length}>
					<div class="flex items-center justify-center space-x-2">
						<div class="h-5 w-5 animate-spin  border-2 border-border border-t-primary"></div>
						<span class="text-muted-foreground">Loading...</span>
					</div>
				</TableCell>
			</TableRow>
		{:else if rows.length === 0}
			<TableRow>
				<TableCell class="h-24 text-center text-muted-foreground" colspan={columns.length}>
					{emptyMessage}
				</TableCell>
			</TableRow>
		{:else}
			{#each rows as row, i (i)}
				<TableRow>
					{#each columns as col (col.key)}
						<TableCell class={col.class}>{row[col.key] as string}</TableCell>
					{/each}
				</TableRow>
			{/each}
		{/if}
	</TableBody>
</TableRoot>
