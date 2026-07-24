export const PUBLIC_PAGE_PATHS = new Set([
	'/about',
	'/login',
	'/signup',
	'/methodology',
	'/responsible-gambling',
	'/terms',
	'/privacy'
]);

export function isPublicPagePath(pathname: string): boolean {
	return PUBLIC_PAGE_PATHS.has(normalizePathname(pathname));
}

function normalizePathname(pathname: string): string {
	if (!pathname || pathname === '/') return '/';
	return `/${pathname.replace(/^\/+|\/+$/g, '')}`;
}
