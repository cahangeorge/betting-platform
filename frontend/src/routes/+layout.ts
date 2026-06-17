import type { LayoutLoad } from './$types';

// Universal load — fallback for client-side navigation
// Server-side auth is handled by +layout.server.ts
export const load: LayoutLoad = async ({ data }) => {
	return {
		user: data?.user ?? null
	};
};
