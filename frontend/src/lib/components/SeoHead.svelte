<script lang="ts">
	import { page } from '$app/state';
	import { JsonLd, MetaTags, deepMerge, type MetaTagsProps } from 'svelte-meta-tags';
	import type { SeoPageData } from '$lib/seo/site';

	const seoData = $derived(page.data as SeoPageData);
	const metaTags = $derived(
		deepMerge(
			(seoData.baseMetaTags ?? {}) as MetaTagsProps,
			(seoData.pageMetaTags ?? {}) as MetaTagsProps
		)
	);
</script>

<MetaTags {...metaTags} />
<JsonLd schema={seoData.pageJsonLd} />
