import type { RequestHandler } from './$types';
import { canonicalUrl } from '$lib/seo/site';

export const GET: RequestHandler = ({ url }) => {
	const body = [
		'User-agent: *',
		'Allow: /',
		'Disallow: /api/',
		`Sitemap: ${canonicalUrl(url, '/sitemap.xml')}`,
		''
	].join('\n');

	return new Response(body, {
		headers: {
			'Content-Type': 'text/plain; charset=utf-8',
			'Cache-Control': 'public, max-age=300, s-maxage=3600, stale-while-revalidate=86400'
		}
	});
};
