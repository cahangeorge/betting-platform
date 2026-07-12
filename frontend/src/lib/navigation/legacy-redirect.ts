import { redirect } from '@sveltejs/kit';

export function redirectLegacyRoute(url: URL, target: string, fixedParams: Record<string, string> = {}): never {
	const params = new URLSearchParams(url.searchParams);
	for (const [key, value] of Object.entries(fixedParams)) params.set(key, value);
	const query = params.toString();
	redirect(308, `${target}${query ? `?${query}` : ''}`);
}
