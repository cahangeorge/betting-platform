import {
	defineBaseMetaTags,
	definePageMetaTags,
	type JsonLdProps,
	type MetaTagsProps
} from 'svelte-meta-tags';
export { PUBLIC_PAGE_PATHS, isPublicPagePath } from './public-routes';

export const SITE_NAME = 'Betfront';
export const SITE_DESCRIPTION =
	'Platformă de analiză pentru pariuri sportive, cu date trasabile, modele statistice și fluxuri de revizuire înaintea oricărei decizii.';
export const SITE_LOCALE = 'ro_RO';
export const SOCIAL_IMAGE_PATH = '/social/betfront-platform.png';

export const INDEXABLE_PAGE_PATHS = ['/about', '/methodology', '/responsible-gambling'] as const;

export const PUBLIC_RESOURCE_PATHS = new Set(['/robots.txt', '/sitemap.xml']);

export function isIndexablePagePath(pathname: string): boolean {
	return INDEXABLE_PAGE_PATHS.includes(
		normalizePathname(pathname) as (typeof INDEXABLE_PAGE_PATHS)[number]
	);
}

export function isPublicResourcePath(pathname: string): boolean {
	return PUBLIC_RESOURCE_PATHS.has(normalizePathname(pathname));
}

export function canonicalUrl(url: URL, pathname = url.pathname): string {
	return new URL(normalizePathname(pathname), `${url.origin}/`).href;
}

export function createBaseMetaTags(url: URL) {
	const canonical = canonicalUrl(url);
	const socialImage = canonicalUrl(url, SOCIAL_IMAGE_PATH);

	return defineBaseMetaTags({
		title: 'Platformă de analiză pentru pariuri sportive',
		titleTemplate: `%s | ${SITE_NAME}`,
		description: SITE_DESCRIPTION,
		robots: 'noindex,follow',
		canonical,
		openGraph: {
			type: 'website',
			url: canonical,
			title: SITE_NAME,
			description: SITE_DESCRIPTION,
			locale: SITE_LOCALE,
			siteName: SITE_NAME,
			images: [
				{
					url: socialImage,
					secureUrl: socialImage,
					type: 'image/png',
					width: 1200,
					height: 630,
					alt: 'Betfront — platformă de analiză pentru pariuri sportive'
				}
			]
		},
		twitter: {
			cardType: 'summary_large_image',
			title: SITE_NAME,
			description: SITE_DESCRIPTION,
			image: socialImage,
			imageAlt: 'Betfront — platformă de analiză pentru pariuri sportive'
		}
	});
}

export function createPublicPageMetaTags(
	url: URL,
	options: { title: string; description: string; pathname?: string }
) {
	const canonical = canonicalUrl(url, options.pathname ?? url.pathname);
	const socialTitle = `${options.title} | ${SITE_NAME}`;

	return definePageMetaTags({
		title: options.title,
		description: options.description,
		robots: 'index,follow',
		additionalRobotsProps: {
			maxImagePreview: 'large',
			maxSnippet: -1,
			maxVideoPreview: -1
		},
		canonical,
		openGraph: {
			url: canonical,
			title: socialTitle,
			description: options.description
		},
		twitter: {
			title: socialTitle,
			description: options.description
		}
	});
}

export function createNoIndexPageMetaTags(
	url: URL,
	options: { title: string; description: string }
) {
	return definePageMetaTags({
		title: options.title,
		description: options.description,
		robots: 'noindex,follow',
		canonical: canonicalUrl(url)
	});
}

export function createWebPageSchema(
	url: URL,
	options: {
		type?: 'AboutPage' | 'WebPage';
		name: string;
		description: string;
		pathname?: string;
	}
): JsonLdProps['schema'] {
	const pageUrl = canonicalUrl(url, options.pathname ?? url.pathname);

	return {
		'@type': options.type ?? 'WebPage',
		'@id': `${pageUrl}#webpage`,
		url: pageUrl,
		name: options.name,
		description: options.description,
		inLanguage: 'ro-RO',
		isPartOf: {
			'@type': 'WebSite',
			'@id': `${url.origin}/#website`,
			url: `${url.origin}/`,
			name: SITE_NAME,
			inLanguage: 'ro-RO'
		}
	};
}

export type SeoPageData = {
	baseMetaTags?: Readonly<MetaTagsProps>;
	pageMetaTags?: Readonly<MetaTagsProps>;
	pageJsonLd?: JsonLdProps['schema'];
};

function normalizePathname(pathname: string): string {
	if (!pathname || pathname === '/') return '/';
	return `/${pathname.replace(/^\/+|\/+$/g, '')}`;
}
