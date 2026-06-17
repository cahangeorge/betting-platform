<script lang="ts">
	import { Skeleton } from './ui/skeleton';
	import Card from './ui/Card.svelte';
</script>

<Card class="p-4">
	<div class="flex items-center justify-between mb-3">
		<div class="flex items-center space-x-2">
			<Skeleton class="h-4 w-16" />
			<Skeleton class="h-5 w-14 " />
		</div>
		<Skeleton class="h-3 w-24" />
	</div>

	<div class="space-y-3">
		<div class="flex items-center justify-between">
			<div class="flex items-center space-x-2">
				<Skeleton class="w-6 h-6 " />
				<Skeleton class="h-4 w-28" />
			</div>
			<Skeleton class="h-6 w-10" />
		</div>

		<div class="flex items-center justify-between">
			<div class="flex items-center space-x-2">
				<Skeleton class="w-6 h-6 " />
				<Skeleton class="h-4 w-24" />
			</div>
			<Skeleton class="h-6 w-10" />
		</div>
	</div>
</Card>
