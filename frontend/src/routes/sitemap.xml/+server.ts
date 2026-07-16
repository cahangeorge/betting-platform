import type { RequestHandler } from './$types';
import { INDEXABLE_PAGE_PATHS, canonicalUrl } from '$lib/seo/site';

export const GET: RequestHandler = ({ url }) => {
	const entries = INDEXABLE_PAGE_PATHS.map(
		(pathname) => `  <url><loc>${escapeXml(canonicalUrl(url, pathname))}</loc></url>`
	).join('\n');
	const body = [
		'<?xml version="1.0" encoding="UTF-8"?>',
		'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
		entries,
		'</urlset>',
		''
	].join('\n');

	return new Response(body, {
		headers: {
			'Content-Type': 'application/xml; charset=utf-8',
			'Cache-Control': 'public, max-age=300, s-maxage=3600, stale-while-revalidate=86400'
		}
	});
};

function escapeXml(value: string): string {
	return value
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('"', '&quot;')
		.replaceAll("'", '&apos;');
}
