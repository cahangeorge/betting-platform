import type { LayoutLoad } from './$types';
import { createBaseMetaTags } from '$lib/seo/site';

// Universal load — fallback for client-side navigation
// Server-side auth is handled by +layout.server.ts
export const load: LayoutLoad = async ({ data, url }) => {
	return {
		user: data?.user ?? null,
		...createBaseMetaTags(url)
	};
};
